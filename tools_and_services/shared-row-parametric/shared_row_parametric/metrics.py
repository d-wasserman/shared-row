"""Allocation metrics: how much of the right-of-way each mode actually gets.

This is the query layer the specification's introduction is reaching for --
"compare high-level right of way summaries across jurisdictions". Widths come
from the cross-section; areas need a segment length, which is computed from
the geometry when one is attached.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from . import vocab
from .model import WIDTH_PRECISION, CrossSection


@dataclass
class Allocation:
    """Width and area allocation for one cross-section."""

    total_width: float
    by_mode: Dict[str, float] = field(default_factory=dict)
    by_type: Dict[str, float] = field(default_factory=dict)
    length_m: Optional[float] = None

    @property
    def shares(self) -> Dict[str, float]:
        """Fraction of the total width per mode group."""
        if self.total_width <= 0:
            return {k: 0.0 for k in self.by_mode}
        return {k: round(v / self.total_width, 4) for k, v in self.by_mode.items()}

    @property
    def areas_m2(self) -> Optional[Dict[str, float]]:
        if self.length_m is None:
            return None
        return {k: round(v * self.length_m, 1) for k, v in self.by_mode.items()}

    @property
    def auto_share(self) -> float:
        return self.shares.get("automobile", 0.0)

    @property
    def sustainable_share(self) -> float:
        """Share allocated to walking, cycling, transit and green space."""
        return round(sum(self.shares.get(m, 0.0) for m in vocab.SUSTAINABLE_MODES), 4)

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "total_width_m": self.total_width,
            "length_m": None if self.length_m is None else round(self.length_m, 1),
            "width_by_mode_m": self.by_mode,
            "share_by_mode": self.shares,
            "width_by_type_m": self.by_type,
            "auto_share": self.auto_share,
            "sustainable_share": self.sustainable_share,
        }
        if self.areas_m2 is not None:
            out["area_by_mode_m2"] = self.areas_m2
        return out

    def table(self) -> str:
        rows = ["%-13s %8s %8s %10s" % ("mode", "width", "share", "area m2")]
        rows.append("-" * 41)
        areas = self.areas_m2 or {}
        for mode, width in sorted(self.by_mode.items(), key=lambda kv: -kv[1]):
            rows.append("%-13s %7.2fm %7.1f%% %10s" % (
                mode, width, self.shares[mode] * 100,
                ("%.0f" % areas[mode]) if mode in areas else "-",
            ))
        rows.append("-" * 41)
        rows.append("%-13s %7.2fm %7.1f%%" % ("total", self.total_width, 100.0))
        rows.append("")
        rows.append("auto %.1f%% / sustainable %.1f%%" % (
            self.auto_share * 100, self.sustainable_share * 100))
        return "\n".join(rows)


def allocation(section: CrossSection, *, length_m: Optional[float] = None) -> Allocation:
    """Summarise a cross-section's width allocation.

    ``length_m`` overrides the geodesic length derived from the geometry.
    """
    by_mode: Dict[str, float] = OrderedDict(
        (mode, 0.0) for mode in list(vocab.MODE_GROUPS) )
    by_type: Dict[str, float] = OrderedDict()
    for s in section.slices:
        by_mode[s.mode] = round(by_mode.get(s.mode, 0.0) + s.width, WIDTH_PRECISION)
        by_type[s.type] = round(by_type.get(s.type, 0.0) + s.width, WIDTH_PRECISION)
    by_mode = OrderedDict((k, v) for k, v in by_mode.items() if v > 0)
    if length_m is None:
        length_m = section.length_m
    return Allocation(
        total_width=section.total_width,
        by_mode=by_mode,
        by_type=by_type,
        length_m=length_m,
    )


@dataclass
class Comparison:
    """Difference between two cross-sections of the same segment."""

    before: Allocation
    after: Allocation

    @property
    def width_delta(self) -> float:
        return round(self.after.total_width - self.before.total_width, WIDTH_PRECISION)

    @property
    def mode_delta(self) -> Dict[str, float]:
        modes = set(self.before.by_mode) | set(self.after.by_mode)
        return {
            m: round(self.after.by_mode.get(m, 0.0) - self.before.by_mode.get(m, 0.0),
                     WIDTH_PRECISION)
            for m in sorted(modes)
        }

    @property
    def share_delta(self) -> Dict[str, float]:
        b, a = self.before.shares, self.after.shares
        modes = set(b) | set(a)
        return {m: round(a.get(m, 0.0) - b.get(m, 0.0), 4) for m in sorted(modes)}

    def table(self) -> str:
        rows = ["%-13s %9s %9s %9s" % ("mode", "before", "after", "delta")]
        rows.append("-" * 43)
        for mode, delta in sorted(self.mode_delta.items(), key=lambda kv: -abs(kv[1])):
            rows.append("%-13s %8.2fm %8.2fm %+8.2fm" % (
                mode,
                self.before.by_mode.get(mode, 0.0),
                self.after.by_mode.get(mode, 0.0),
                delta,
            ))
        rows.append("-" * 43)
        rows.append("%-13s %8.2fm %8.2fm %+8.2fm" % (
            "total", self.before.total_width, self.after.total_width, self.width_delta))
        rows.append("")
        rows.append("auto share  %.1f%% -> %.1f%%  (%+.1f pts)" % (
            self.before.auto_share * 100, self.after.auto_share * 100,
            (self.after.auto_share - self.before.auto_share) * 100))
        return "\n".join(rows)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "width_delta_m": self.width_delta,
            "width_preserved": abs(self.width_delta) < 0.005,
            "mode_delta_m": self.mode_delta,
            "share_delta": self.share_delta,
            "before": self.before.to_dict(),
            "after": self.after.to_dict(),
        }


def compare(before: CrossSection, after: CrossSection, **kwargs) -> Comparison:
    return Comparison(allocation(before, **kwargs), allocation(after, **kwargs))


def network_summary(sections: List[CrossSection]) -> Dict[str, Any]:
    """Aggregate allocation across many segments, weighted by segment length.

    Length-weighting matters: a 400 m arterial should not count the same as a
    40 m alley. Segments without geometry fall back to unit weight, and the
    result says how many did.
    """
    if not sections:
        return {"segments": 0}
    total_len = 0.0
    no_geom = 0
    mode_area: Dict[str, float] = {}
    weighted_width = 0.0
    for section in sections:
        length = section.length_m
        if length is None:
            length = 1.0
            no_geom += 1
        total_len += length
        weighted_width += section.total_width * length
        for s in section.slices:
            mode_area[s.mode] = mode_area.get(s.mode, 0.0) + s.width * length
    total_area = sum(mode_area.values())
    return {
        "segments": len(sections),
        "segments_without_geometry": no_geom,
        "total_length_m": round(total_len, 1),
        "mean_row_width_m": round(weighted_width / total_len, 2) if total_len else 0.0,
        "area_by_mode_m2": {k: round(v, 1) for k, v in sorted(mode_area.items())},
        "share_by_mode": {
            k: round(v / total_area, 4) for k, v in sorted(mode_area.items())
        } if total_area else {},
        "length_weighted": True,
    }
