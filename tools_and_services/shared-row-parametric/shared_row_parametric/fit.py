"""Width allocation: fit a parametric template into a given right-of-way.

The allocator is deliberately deterministic and explainable rather than an
opaque optimiser. A planner needs to be able to say *why* the sidewalk came
out at 1.8 m, so every adjustment is recorded in the returned report.

Algorithm
---------
1. Start every slice at its preferred width.
2. Over-allocated: shrink toward minimum widths, distributing the deficit in
   proportion to each slice's ``flex`` weight (water-filling, so a slice that
   hits its minimum passes the remainder to its neighbours). If still over
   budget, drop slices one at a time in descending ``priority`` order, never
   dropping a ``required`` slice, re-running the shrink after each drop.
3. Under-allocated: grow toward maximum widths by the same weighted
   water-filling, then hand any leftover to the template's filler slice.
4. Round to the centimetre and push the rounding residue into the most
   flexible slice, so the section's total matches the requested width exactly.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Dict, List, Optional, Sequence, Tuple

from . import vocab
from .model import TOL, WIDTH_PRECISION, CrossSection, Slice

MAX_PASSES = 500


@dataclass(frozen=True)
class SliceSpec:
    """A parametric slice: a type plus the width range it may occupy."""

    type: str
    min_width: float
    preferred_width: float
    max_width: float
    #: Higher priority is dropped first. Required slices are never dropped.
    priority: int = 50
    required: bool = False
    #: Relative share of any shrink or growth. 0 pins the slice at preferred.
    flex: float = 1.0
    direction: str = "bidirectional"
    height: float = 0.0
    material: Optional[str] = None
    meta: Optional[Dict[str, Any]] = None
    #: Free-form label used by templates to find slices again ("left_bike").
    role: Optional[str] = None
    #: Slices sharing a pair key are dropped together, so a mirrored template
    #: never loses one side's bike lane while keeping the other's.
    pair: Optional[str] = None

    def __post_init__(self):
        object.__setattr__(self, "type", vocab.normalize_type(self.type))
        lo, pref, hi = float(self.min_width), float(self.preferred_width), float(self.max_width)
        if lo < 0:
            raise ValueError("%s: min_width must be >= 0" % self.type)
        if hi < lo:
            raise ValueError("%s: max_width %.2f < min_width %.2f" % (self.type, hi, lo))
        # Clamp rather than reject: template authors edit these by hand.
        pref = min(max(pref, lo), hi)
        object.__setattr__(self, "min_width", lo)
        object.__setattr__(self, "preferred_width", pref)
        object.__setattr__(self, "max_width", hi)
        object.__setattr__(self, "flex", max(0.0, float(self.flex)))

    def to_slice(self, width: float) -> Slice:
        return Slice(
            type=self.type,
            width=width,
            height=self.height,
            direction=self.direction,
            material=self.material,
            meta=dict(self.meta) if self.meta else None,
        )

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SliceSpec":
        """Build from a template JSON object.

        ``width`` is shorthand for a fixed-width slice; ``min``/``preferred``/
        ``max`` may each be omitted and default sensibly.
        """
        data = dict(data)
        if "width" in data:
            w = float(data.pop("width"))
            data.setdefault("preferred_width", w)
            data.setdefault("min_width", w)
            data.setdefault("max_width", w)
        pref = data.get("preferred_width")
        if pref is None:
            pref = data.get("min_width", data.get("max_width", 0.0))
        pref = float(pref)
        return cls(
            type=data["type"],
            min_width=float(data.get("min_width", pref)),
            preferred_width=pref,
            max_width=float(data.get("max_width", pref)),
            priority=int(data.get("priority", 50)),
            required=bool(data.get("required", False)),
            flex=float(data.get("flex", 1.0)),
            direction=data.get("direction", "bidirectional"),
            height=float(data.get("height", 0.0)),
            material=data.get("material"),
            meta=data.get("meta"),
            role=data.get("role"),
            pair=data.get("pair"),
        )


@dataclass
class FitReport:
    """What the allocator did, and whether the result is usable."""

    requested_width: float
    resulting_width: float
    status: str = "exact"          # exact | shrunk | grown | infeasible
    dropped: List[str] = field(default_factory=list)
    adjustments: List[Tuple[str, float, float]] = field(default_factory=list)
    residual: float = 0.0          # width left unallocated (or missing, if < 0)
    notes: List[str] = field(default_factory=list)

    @property
    def feasible(self) -> bool:
        return self.status != "infeasible"

    def summary(self) -> str:
        lines = [
            "requested %.2f m -> allocated %.2f m (%s)"
            % (self.requested_width, self.resulting_width, self.status)
        ]
        if self.dropped:
            lines.append("  dropped: " + ", ".join(self.dropped))
        for name, frm, to in self.adjustments:
            lines.append("  %-22s %.2f -> %.2f m" % (name, frm, to))
        if abs(self.residual) > TOL:
            lines.append("  residual: %+.2f m" % self.residual)
        lines.extend("  note: " + n for n in self.notes)
        return "\n".join(lines)


@dataclass(frozen=True)
class FitResult:
    section: CrossSection
    report: FitReport


def _waterfill(widths, bounds, weights, amount, sign):
    """Move ``amount`` of width toward ``bounds``, weighted by ``weights``.

    ``sign`` is -1 to shrink toward minimums or +1 to grow toward maximums.
    Returns ``(new_widths, unallocated)``.
    """
    widths = list(widths)
    remaining = float(amount)
    for _ in range(MAX_PASSES):
        if remaining <= TOL:
            break
        active = [
            i for i in range(len(widths))
            if weights[i] > 0 and (bounds[i] - widths[i]) * sign > TOL
        ]
        if not active:
            break
        total_weight = sum(weights[i] for i in active)
        moved = 0.0
        for i in active:
            want = remaining * weights[i] / total_weight
            headroom = abs(bounds[i] - widths[i])
            take = min(want, headroom)
            widths[i] += sign * take
            moved += take
        remaining -= moved
        if moved <= TOL:
            break
    return widths, max(0.0, remaining)


def fit(
    specs: Sequence[SliceSpec],
    row_width: Optional[float],
    *,
    allow_drop: bool = True,
    filler: Optional[str] = None,
    filler_index: Optional[int] = None,
    sharedstreetid: Optional[str] = None,
    geometry: Optional[Dict[str, Any]] = None,
) -> FitResult:
    """Allocate ``row_width`` metres across ``specs``.

    With ``row_width`` None every slice takes its preferred width.
    """
    specs = list(specs)
    if not specs:
        raise ValueError("fit() needs at least one SliceSpec")

    live: List[SliceSpec] = list(specs)
    widths = [s.preferred_width for s in live]

    if row_width is None:
        report = FitReport(
            requested_width=round(sum(widths), WIDTH_PRECISION),
            resulting_width=round(sum(widths), WIDTH_PRECISION),
            status="exact",
            notes=["no target width given; used preferred widths"],
        )
        return FitResult(_build(live, widths, sharedstreetid, geometry), report)

    row_width = float(row_width)
    if row_width < 0:
        raise ValueError("row_width must be >= 0")
    report = FitReport(requested_width=round(row_width, WIDTH_PRECISION), resulting_width=0.0)
    dropped: List[SliceSpec] = []

    # --- over budget: shrink, then drop -------------------------------------
    for _ in range(len(specs) + 1):
        deficit = sum(widths) - row_width
        if deficit <= TOL:
            break
        widths, unresolved = _waterfill(
            widths, [s.min_width for s in live], [s.flex for s in live], deficit, -1
        )
        if unresolved <= TOL:
            report.status = "shrunk"
            break
        if not allow_drop:
            report.status = "infeasible"
            report.notes.append(
                "%.2f m over budget at minimum widths and dropping is disabled"
                % unresolved
            )
            break
        victims = _pick_victims(live)
        if not victims:
            report.status = "infeasible"
            report.notes.append(
                "%.2f m over budget with only required slices left" % unresolved
            )
            break
        for idx in sorted(victims, reverse=True):
            dropped.append(live[idx])
            del live[idx]
            del widths[idx]
        report.status = "shrunk"

    # --- under budget: grow, then fill --------------------------------------
    surplus = row_width - sum(widths)
    if surplus > TOL:
        widths, leftover = _waterfill(
            widths, [s.max_width for s in live], [s.flex for s in live], surplus, +1
        )
        if leftover > TOL:
            if filler:
                live, widths = _insert_filler(live, widths, filler, filler_index, leftover)
                leftover = 0.0
            else:
                report.notes.append(
                    "%.2f m unallocated: every slice is at its maximum width" % leftover
                )
        report.residual = round(leftover, WIDTH_PRECISION)
        if report.status == "exact" and abs(sum(widths) - row_width) > TOL:
            report.status = "grown"
        elif report.status == "exact" and surplus > TOL:
            report.status = "grown"

    # --- round to the centimetre, then reconcile ----------------------------
    widths = [round(w, WIDTH_PRECISION) for w in widths]
    if report.feasible and abs(report.residual) <= TOL:
        drift = round(row_width - sum(widths), WIDTH_PRECISION)
        if abs(drift) > TOL:
            widths = _absorb_drift(live, widths, drift)

    for spec, width in zip(live, widths):
        if abs(width - spec.preferred_width) > 0.005:
            report.adjustments.append(
                (spec.role or spec.type, spec.preferred_width, width)
            )
    report.dropped = [s.role or s.type for s in dropped]
    section = _build(live, widths, sharedstreetid, geometry)
    report.resulting_width = section.total_width
    if report.status in ("exact", "shrunk", "grown"):
        if abs(report.resulting_width - row_width) <= 0.005 and not report.dropped \
                and not report.adjustments:
            report.status = "exact"
    return FitResult(section, report)


def _pick_victims(live: Sequence[SliceSpec]) -> List[int]:
    """Indices of the next slice group to drop.

    The most expendable non-required slice is chosen by descending priority,
    tie-broken on the narrowest minimum so the cheapest goes first. If that
    slice declares a ``pair``, every live slice sharing the key goes with it.
    """
    candidates = [(i, s) for i, s in enumerate(live) if not s.required]
    if not candidates:
        return []
    idx, victim = max(candidates, key=lambda t: (t[1].priority, -t[1].min_width, -t[0]))
    if victim.pair:
        return [i for i, s in enumerate(live) if s.pair == victim.pair and not s.required]
    return [idx]


def _insert_filler(live, widths, filler_type, filler_index, amount):
    """Add a slice of ``filler_type`` absorbing ``amount`` metres."""
    live = list(live)
    widths = list(widths)
    spec = SliceSpec(
        type=filler_type,
        min_width=0.0,
        preferred_width=amount,
        max_width=amount,
        flex=0.0,
        role="filler",
        meta={"source": "fit_filler"},
    )
    idx = len(live) // 2 if filler_index is None else max(0, min(filler_index, len(live)))
    live.insert(idx, spec)
    widths.insert(idx, amount)
    return live, widths


#: Types that sit between the two sides, so absorbing drift there does not
#: make one kerb-to-centre side wider than the other.
_CENTRE_TYPES = ("median", "turn_lane", "buffer", "planting_strip")


def _absorb_drift(live, widths, drift):
    """Push sub-centimetre rounding drift into one slice.

    A centre slice is preferred so the left and right sides stay symmetric;
    otherwise the most flexible slice takes it.
    """
    widths = list(widths)
    mid = (len(live) - 1) / 2.0
    order = sorted(
        range(len(live)),
        key=lambda i: (
            live[i].type in _CENTRE_TYPES and abs(i - mid) <= 1.0,
            live[i].flex,
            widths[i],
        ),
        reverse=True,
    )
    for i in order:
        candidate = round(widths[i] + drift, WIDTH_PRECISION)
        if candidate >= 0:
            widths[i] = candidate
            return widths
    widths[order[0]] = round(max(0.0, widths[order[0]] + drift), WIDTH_PRECISION)
    return widths


def _build(specs, widths, sharedstreetid, geometry) -> CrossSection:
    slices = [
        spec.to_slice(width)
        for spec, width in zip(specs, widths)
        if width > TOL
    ]
    return CrossSection(slices=slices, sharedstreetid=sharedstreetid, geometry=geometry)
