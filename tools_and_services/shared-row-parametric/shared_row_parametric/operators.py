"""Reallocation operators: edit a cross-section while holding the kerb lines.

Every operator returns a new :class:`CrossSection`. The width-preserving ones
keep the total right-of-way constant, which is the whole point of a
reallocation study: the property lines do not move, so any width a travel lane
gives up has to reappear somewhere else in the same section.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Dict, List, Optional, Sequence, Tuple

from . import vocab
from .model import TOL, WIDTH_PRECISION, CrossSection, Slice

DRIVEABLE = ("drive_lane", "turn_lane")


# --- decomposition ----------------------------------------------------------

def decompose(section: CrossSection):
    """Split into ``(left_outside_in, centre, right_outside_in)``."""
    left, centre, right = section.split_sides()
    return list(left), centre, list(reversed(right))


def recompose(left, centre, right, template: CrossSection) -> CrossSection:
    """Rebuild a section from sides ordered outside-in."""
    slices = list(left) + ([centre] if centre is not None else []) + list(reversed(right))
    return template.with_slices(slices)


# --- primitives -------------------------------------------------------------

def transfer(section: CrossSection, source: int, target: int, width: float) -> CrossSection:
    """Move ``width`` metres from slice ``source`` to slice ``target``.

    The total width is unchanged. Raises if the source is too narrow.
    """
    slices = list(section.slices)
    if not (0 <= source < len(slices)) or not (0 <= target < len(slices)):
        raise IndexError("slice index out of range")
    width = round(float(width), WIDTH_PRECISION)
    if width < 0:
        return transfer(section, target, source, -width)
    if slices[source].width + TOL < width:
        raise ValueError(
            "cannot take %.2f m from %s, which is only %.2f m wide"
            % (width, slices[source].type, slices[source].width)
        )
    slices[source] = slices[source].with_width(slices[source].width - width)
    slices[target] = slices[target].with_width(slices[target].width + width)
    return section.with_slices(s for s in slices if s.width > TOL)


def insert(
    section: CrossSection,
    new_slice: Slice,
    index: int,
    *,
    take_from: Optional[int] = None,
) -> CrossSection:
    """Insert ``new_slice`` at ``index``.

    With ``take_from`` the new slice's width is taken out of that slice, so
    the total is preserved; otherwise the section gets wider.
    """
    slices = list(section.slices)
    index = max(0, min(index, len(slices)))
    if take_from is not None:
        donor = slices[take_from]
        if donor.width + TOL < new_slice.width:
            raise ValueError(
                "cannot take %.2f m from %s, which is only %.2f m wide"
                % (new_slice.width, donor.type, donor.width)
            )
        slices[take_from] = donor.with_width(donor.width - new_slice.width)
    slices.insert(index, new_slice)
    return section.with_slices(s for s in slices if s.width > TOL)


def remove(
    section: CrossSection,
    index: int,
    *,
    give_to: Optional[int] = None,
) -> CrossSection:
    """Remove the slice at ``index``.

    With ``give_to`` its width moves to that slice (index in the *original*
    numbering), preserving the total; otherwise the section gets narrower.
    """
    slices = list(section.slices)
    freed = slices[index].width
    if give_to is not None:
        if give_to == index:
            raise ValueError("give_to must differ from the removed index")
        slices[give_to] = slices[give_to].with_width(slices[give_to].width + freed)
    del slices[index]
    return section.with_slices(s for s in slices if s.width > TOL)


def scale_to(section: CrossSection, row_width: float) -> CrossSection:
    """Scale every slice proportionally to hit ``row_width``.

    A blunt instrument -- it will happily produce a 2.1 m travel lane. Prefer
    refitting a template when minimum widths matter.
    """
    total = section.total_width
    if total <= TOL:
        raise ValueError("cannot scale a zero-width section")
    factor = float(row_width) / total
    scaled = [s.with_width(s.width * factor) for s in section.slices]
    drift = round(float(row_width) - sum(s.width for s in scaled), WIDTH_PRECISION)
    if abs(drift) > TOL and scaled:
        widest = max(range(len(scaled)), key=lambda i: scaled[i].width)
        scaled[widest] = scaled[widest].with_width(scaled[widest].width + drift)
    return section.with_slices(s for s in scaled if s.width > TOL)


# --- composed operators -----------------------------------------------------

def _kerb_index(side: Sequence[Slice], *, protected: bool) -> int:
    """Where a new cycle track goes in a side ordered outside-in.

    Unprotected tracks sit inboard of parking; protected ones sit outboard of
    it, so parked cars separate riders from moving traffic.
    """
    parking = [i for i, s in enumerate(side) if s.type in vocab.CURB_ZONE]
    walk = [i for i, s in enumerate(side)
            if s.type in ("sidewalk", "planting_strip", "filter_strip", "transit_shelter")]
    if parking:
        return parking[0] if protected else parking[-1] + 1
    if walk:
        return walk[-1] + 1
    return 0


def set_travel_lanes(
    section: CrossSection,
    per_direction: int,
    *,
    give_to: Optional[str] = None,
) -> Tuple[CrossSection, float]:
    """Set the number of general travel lanes per direction.

    Lanes are removed from the inside out, so the kerbside lane survives --
    the convention this specification's own data uses, where
    ``Through_Lane_1`` is the outermost lane. Returns the new section and the
    width freed (negative if lanes were added). Freed width is given to a
    slice of type ``give_to`` when one exists on that side.
    """
    if per_direction < 0:
        raise ValueError("per_direction must be >= 0")
    left, centre, right = decompose(section)
    freed = 0.0
    new_sides = []
    for side in (left, right):
        lanes = [i for i, s in enumerate(side) if s.type == "drive_lane"]
        side = list(side)
        while len(lanes) > per_direction:
            idx = lanes.pop()          # innermost lane
            freed += side[idx].width
            del side[idx]
            lanes = [i for i, s in enumerate(side) if s.type == "drive_lane"]
        if lanes and len(lanes) < per_direction:
            width = side[lanes[-1]].width
            for _ in range(per_direction - len(lanes)):
                side.insert(lanes[-1] + 1, replace(side[lanes[-1]], width=width))
                freed -= width
                lanes = [i for i, s in enumerate(side) if s.type == "drive_lane"]
        new_sides.append(side)

    result = recompose(new_sides[0], centre, new_sides[1], section)
    if give_to and freed > TOL:
        result = _spend_on_type(result, give_to, freed)
        freed = 0.0
    return result, round(freed, WIDTH_PRECISION)


def _spend_on_type(section: CrossSection, slice_type: str, amount: float) -> CrossSection:
    """Split ``amount`` evenly across existing slices of ``slice_type``.

    If none exist the width goes to the outermost slice on each side, which
    is the walkway in every template here.
    """
    stype = vocab.normalize_type(slice_type)
    targets = list(section.of_type(stype))
    if not targets:
        targets = [0, len(section.slices) - 1]
    share = amount / len(targets)
    slices = list(section.slices)
    for i in targets:
        slices[i] = slices[i].with_width(slices[i].width + share)
    out = section.with_slices(slices)
    drift = round(section.total_width + amount - out.total_width, WIDTH_PRECISION)
    if abs(drift) > TOL:
        slices = list(out.slices)
        slices[targets[0]] = slices[targets[0]].with_width(
            slices[targets[0]].width + drift)
        out = out.with_slices(slices)
    return out


def road_diet(
    section: CrossSection,
    *,
    keep_lanes: int = 1,
    bike_width: float = 1.8,
    buffer_width: float = 0.6,
    protected: bool = False,
    remainder_to: str = "sidewalk",
) -> Tuple[CrossSection, Dict[str, Any]]:
    """Reallocate travel lanes to cycle tracks, holding the total width.

    Removes travel lanes from the inside out until ``keep_lanes`` remain per
    direction, then spends the freed width on a cycle track and buffer on each
    side, widening or adding as needed. Anything left over goes to
    ``remainder_to``. Returns ``(section, report)``.
    """
    before = section.total_width
    section, freed = set_travel_lanes(section, keep_lanes)
    # Every return path reports the same keys, so callers can rely on them.
    report: Dict[str, Any] = {
        "freed_m": round(freed, WIDTH_PRECISION),
        "added": [],
        "widened": [],
        "remainder_m": 0.0,
        "width_before": before,
        "width_after": section.total_width,
        "width_preserved": abs(before - section.total_width) < 0.005,
    }
    if freed <= TOL:
        report["note"] = "no travel lanes to remove; section unchanged"
        return section, report

    left, centre, right = decompose(section)
    per_side = freed / 2.0
    new_sides = []
    for label, side in (("left", left), ("right", right)):
        side = list(side)
        budget = per_side
        existing = [i for i, s in enumerate(side) if s.type == "bike_lane"]
        direction = "reverse" if label == "left" else "forward"
        if existing:
            i = existing[0]
            grow = min(budget, max(0.0, bike_width - side[i].width))
            if grow > TOL:
                side[i] = side[i].with_width(side[i].width + grow)
                budget -= grow
                report["widened"].append("%s bike_lane +%.2fm" % (label, grow))
        else:
            width = min(bike_width, budget)
            at = _kerb_index(side, protected=protected)
            side.insert(at, Slice(
                type="bike_lane", width=width, direction=direction,
                meta={"protected": bool(protected), "source": "road_diet"},
            ))
            budget -= width
            report["added"].append("%s bike_lane %.2fm" % (label, width))
        if budget > TOL and buffer_width > 0:
            bike = [i for i, s in enumerate(side) if s.type == "bike_lane"]
            # Widen a buffer that already flanks the cycle track rather than
            # stacking a second one beside it.
            neighbour = None
            if bike:
                for j in (bike[0] + 1, bike[0] - 1):
                    if 0 <= j < len(side) and side[j].type == "buffer":
                        neighbour = j
                        break
            if neighbour is not None:
                grow = min(budget, max(0.0, buffer_width - side[neighbour].width))
                if grow > TOL:
                    side[neighbour] = side[neighbour].with_width(
                        side[neighbour].width + grow)
                    budget -= grow
                    report["widened"].append("%s buffer +%.2fm" % (label, grow))
            else:
                width = min(buffer_width, budget)
                at = bike[0] + 1 if bike else _kerb_index(side, protected=protected)
                side.insert(at, Slice(
                    type="buffer", width=width,
                    material="concrete" if protected else "paint",
                    meta={"separation": "curb" if protected else "paint",
                          "protects": "bike_lane", "source": "road_diet"},
                ))
                budget -= width
                report["added"].append("%s buffer %.2fm" % (label, width))
        report["remainder_m"] = round(report["remainder_m"] + budget, WIDTH_PRECISION)
        new_sides.append(side)

    result = recompose(new_sides[0], centre, new_sides[1], section)
    if report["remainder_m"] > TOL:
        result = _spend_on_type(result, remainder_to, report["remainder_m"])
        report["spent_remainder_on"] = remainder_to
    report["width_before"] = before
    report["width_after"] = result.total_width
    report["width_preserved"] = abs(before - result.total_width) < 0.005
    return result, report


def widen(
    section: CrossSection,
    slice_type: str,
    target_width: float,
    *,
    take_from: Sequence[str] = DRIVEABLE,
) -> Tuple[CrossSection, Dict[str, Any]]:
    """Widen every slice of ``slice_type`` to ``target_width``.

    The width is taken from the widest available ``take_from`` slice each
    time, so the total is preserved. Reports any shortfall rather than
    silently widening the street.
    """
    donors_types = {vocab.normalize_type(t) for t in take_from}
    report: Dict[str, Any] = {"moved_m": 0.0, "shortfall_m": 0.0, "moves": []}
    stype = vocab.normalize_type(slice_type)
    for _ in range(64):
        slices = section.slices
        needy = [i for i, s in enumerate(slices)
                 if s.type == stype and s.width + TOL < target_width]
        if not needy:
            break
        i = needy[0]
        need = round(target_width - slices[i].width, WIDTH_PRECISION)
        donors = [j for j, s in enumerate(slices) if s.type in donors_types]
        if not donors:
            report["shortfall_m"] = round(report["shortfall_m"] + need, WIDTH_PRECISION)
            break
        j = max(donors, key=lambda k: slices[k].width)
        take = min(need, slices[j].width)
        if take <= TOL:
            report["shortfall_m"] = round(report["shortfall_m"] + need, WIDTH_PRECISION)
            break
        section = transfer(section, j, i, take)
        report["moved_m"] = round(report["moved_m"] + take, WIDTH_PRECISION)
        report["moves"].append("%s -> %s %.2fm" % (slices[j].type, stype, take))
    return section, report


def coalesce(section: CrossSection, *, match_meta: bool = False) -> CrossSection:
    """Merge adjacent slices of the same type into one.

    Editing operators can leave two abutting slices of the same type, which
    is valid but describes the street less clearly than a single wider slice.
    Direction, height and material must agree; metadata is compared only when
    ``match_meta`` is set, and the first slice's metadata wins otherwise.
    """
    merged: List[Slice] = []
    for s in section.slices:
        if merged:
            prev = merged[-1]
            same = (
                prev.type == s.type
                and prev.direction == s.direction
                and abs(prev.height - s.height) < TOL
                and prev.material == s.material
                and (not match_meta or (prev.meta or {}) == (s.meta or {}))
            )
            if same:
                merged[-1] = prev.with_width(prev.width + s.width)
                continue
        merged.append(s)
    return section.with_slices(merged)
