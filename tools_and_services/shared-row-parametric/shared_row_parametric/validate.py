"""Validation against the shared-row specification.

The specification deliberately allows new and emerging slice types, so an
unrecognised type is a warning rather than an error. Errors are reserved for
things that are structurally wrong: a missing required field, a negative
width, a direction outside the enumeration.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence

from . import additive as additive_mod
from . import vocab
from .model import TOL, CrossSection

ERROR, WARNING, INFO = "error", "warning", "info"
_RANK = {ERROR: 0, WARNING: 1, INFO: 2}


@dataclass(frozen=True)
class Issue:
    level: str
    code: str
    message: str
    where: str = ""

    def __str__(self) -> str:
        loc = " [%s]" % self.where if self.where else ""
        return "%-7s %-24s %s%s" % (self.level, self.code, self.message, loc)


class Result:
    def __init__(self, issues: Sequence[Issue] = ()):
        self.issues: List[Issue] = sorted(
            issues, key=lambda i: (_RANK.get(i.level, 9), i.code))

    def __bool__(self) -> bool:
        return not self.errors

    def __len__(self) -> int:
        return len(self.issues)

    @property
    def errors(self) -> List[Issue]:
        return [i for i in self.issues if i.level == ERROR]

    @property
    def warnings(self) -> List[Issue]:
        return [i for i in self.issues if i.level == WARNING]

    def report(self, *, min_level: str = INFO) -> str:
        cutoff = _RANK[min_level]
        lines = [str(i) for i in self.issues if _RANK.get(i.level, 9) <= cutoff]
        if not lines:
            return "valid: no issues"
        lines.append("")
        lines.append("%d error(s), %d warning(s), %d total"
                     % (len(self.errors), len(self.warnings), len(self.issues)))
        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "valid": bool(self),
            "errors": len(self.errors),
            "warnings": len(self.warnings),
            "issues": [
                {"level": i.level, "code": i.code, "message": i.message,
                 "where": i.where}
                for i in self.issues
            ],
        }


def validate_section(section: CrossSection, *, where: str = "") -> Result:
    """Check one cross-section."""
    issues: List[Issue] = []

    def at(i: Optional[int] = None) -> str:
        if where and i is not None:
            return "%s slice %d" % (where, i)
        if i is not None:
            return "slice %d" % i
        return where

    if not section.slices:
        issues.append(Issue(ERROR, "empty-section", "no slices", at()))
        return Result(issues)

    if section.sharedstreetid in (None, ""):
        issues.append(Issue(
            WARNING, "missing-sharedstreetid",
            "SharedStreetID is required by the specification but is unset",
            at()))

    for i, s in enumerate(section.slices):
        if not vocab.is_known_type(s.type):
            issues.append(Issue(
                WARNING, "unknown-slice-type",
                "%r is not in the Slice Types table; the specification "
                "permits new types, so confirm this is intentional" % s.type,
                at(i)))
        if s.type in vocab.TYPE_ALIASES:
            issues.append(Issue(
                INFO, "aliased-type",
                "%r normalises to %r" % (s.type, vocab.normalize_type(s.type)),
                at(i)))
        if s.width is None or s.width < 0:
            issues.append(Issue(ERROR, "negative-width",
                                "width %r is not >= 0" % (s.width,), at(i)))
        elif s.width <= TOL:
            issues.append(Issue(WARNING, "zero-width",
                                "%s slice has zero width" % s.type, at(i)))
        if s.direction not in vocab.DIRECTIONS:
            issues.append(Issue(
                ERROR, "bad-direction",
                "direction %r is not one of %s"
                % (s.direction, ", ".join(vocab.DIRECTIONS)), at(i)))
        if not isinstance(s.height, (int, float)):
            issues.append(Issue(ERROR, "bad-height",
                                "height %r is not numeric" % (s.height,), at(i)))
        if s.meta is not None and not isinstance(s.meta, dict):
            issues.append(Issue(ERROR, "bad-meta",
                                "meta must be a JSON object", at(i)))

    # --- structural sanity ------------------------------------------------
    walkable = ("sidewalk", "path")
    if not any(s.type in walkable for s in section.slices):
        issues.append(Issue(
            WARNING, "no-pedestrian-slice",
            "no sidewalk or path: the specification describes the ROW from "
            "sidewalk edge to sidewalk edge", at()))
    else:
        ends = (section.slices[0].type, section.slices[-1].type)
        for pos, stype in zip(("first", "last"), ends):
            if stype in ("drive_lane", "turn_lane"):
                issues.append(Issue(
                    WARNING, "traffic-at-edge",
                    "the %s slice is a %s, so the section does not reach the "
                    "sidewalk edge" % (pos, stype), at()))

    centre_types = [s.type for s in section.slices if s.type in ("median", "turn_lane")]
    if len(centre_types) > 1:
        issues.append(Issue(
            INFO, "multiple-centre-slices",
            "%d median/turn_lane slices; the additive schema has one "
            "Center_Lane column" % len(centre_types), at()))

    for i in range(len(section.slices) - 1):
        a, b = section.slices[i], section.slices[i + 1]
        # Distinct sidewalk zones (frontage / through / furniture) are meant
        # to be separate slices, so they are not a merge candidate.
        zones = {(a.meta or {}).get("zone"), (b.meta or {}).get("zone")}
        if (a.type == b.type and a.direction == b.direction
                and abs(a.height - b.height) < TOL
                and not (len(zones) > 1 and None not in zones)):
            issues.append(Issue(
                INFO, "adjacent-duplicate",
                "slices %d and %d are both %s and could be merged"
                % (i, i + 1, a.type), at(i)))

    if section.total_width <= TOL:
        issues.append(Issue(ERROR, "zero-total-width",
                            "the section has no width", at()))
    return Result(issues)


REQUIRED_ADDITIVE = (
    "SharedStreetID",
    "Right_Sidewalk_Through_Zone", "Right_Sidewalk_Furniture_Zone",
    "Right_Through_Lane_1", "Right_Bike_Lane", "Right_Bike_Buffer",
    "Right_Parking_Lane", "Right_Transit_Lane",
    "Left_Sidewalk_Through_Zone", "Left_Sidewalk_Furniture_Zone",
    "Left_Through_Lane_1", "Left_Bike_Lane", "Left_Bike_Buffer",
    "Left_Parking_Lane", "Left_Transit_Lane",
    "Center_Lane",
)


def validate_additive(record: Dict[str, Any], *, where: str = "") -> Result:
    """Check an additive record for the specification's required fields."""
    issues: List[Issue] = []
    present = set(record)
    for name in REQUIRED_ADDITIVE:
        alias = additive_mod.ALIASES.get(name)
        if name not in present and (alias or "") not in present:
            issues.append(Issue(
                ERROR, "missing-required-field",
                "%s (alias %s) is required by Additive.md" % (name, alias),
                where))

    for name in ("Left_Transit_Lane", "Left_Transit_Meta"):
        if name in present:
            issues.append(Issue(INFO, "left-transit-alias",
                                additive_mod.LEFT_TRANSIT_ALIAS_NOTE, where))
            break

    enum_checks = (
        ("Left_Sidewalk_Furniture_Meta", vocab.SIDEWALK_FURNITURE_META),
        ("Right_Sidewalk_Furniture_Meta", vocab.SIDEWALK_FURNITURE_META),
        ("Left_Bike_Buffer_Meta", vocab.BIKE_BUFFER_META),
        ("Right_Bike_Buffer_Meta", vocab.BIKE_BUFFER_META),
        ("Left_Parking_Lane_Meta", vocab.PARKING_LANE_META),
        ("Right_Parking_Lane_Meta", vocab.PARKING_LANE_META),
        ("Left_Transit_Meta", vocab.TRANSIT_META),
        ("Right_Transit_Meta", vocab.TRANSIT_META),
        ("Center_Lane_Meta", vocab.CENTER_LANE_META),
        ("Begin_Crosswalk_Meta", vocab.CROSSWALK_META),
        ("End_Crosswalk_Meta", vocab.CROSSWALK_META),
        ("Off_Street_Meta", vocab.OFF_STREET_META),
    )
    for name, allowed in enum_checks:
        value = additive_mod._text(record, name)
        if value and value.lower() not in allowed:
            issues.append(Issue(
                WARNING, "meta-outside-enumeration",
                "%s = %r is not in the specification's list (%s)"
                % (name, value, ", ".join(allowed[:4]) + ", ..."),
                where))

    for name in REQUIRED_ADDITIVE:
        if name.endswith(("_Zone", "_Lane", "_1")) or name == "Center_Lane":
            value = additive_mod._get(record, name)
            if value is None:
                continue
            try:
                if float(value) < 0:
                    issues.append(Issue(ERROR, "negative-width",
                                        "%s = %r" % (name, value), where))
            except (TypeError, ValueError):
                issues.append(Issue(ERROR, "non-numeric-width",
                                    "%s = %r is not a number" % (name, value), where))
    return Result(issues)


def validate_crosswalk_rows(rows: Sequence[Dict[str, Any]], *, where: str = "") -> Result:
    """Check crosswalk rows for a single segment."""
    issues: List[Issue] = []
    indices = []
    for r in rows:
        idx = r.get("rowindex")
        if idx is None:
            issues.append(Issue(ERROR, "missing-rowindex",
                                "rowindex is required by Crosswalk.md", where))
            continue
        try:
            indices.append(int(idx))
        except (TypeError, ValueError):
            issues.append(Issue(ERROR, "bad-rowindex",
                                "rowindex %r is not an integer" % (idx,), where))
    if indices:
        if len(set(indices)) != len(indices):
            issues.append(Issue(ERROR, "duplicate-rowindex",
                                "rowindex values repeat within one segment", where))
        expected = list(range(min(indices), min(indices) + len(indices)))
        if sorted(indices) != expected:
            issues.append(Issue(WARNING, "rowindex-gap",
                                "rowindex values are not consecutive: %s"
                                % sorted(indices), where))
    for r in rows:
        meta = r.get("meta")
        if isinstance(meta, str) and meta.strip():
            try:
                json.loads(meta)
            except ValueError:
                issues.append(Issue(WARNING, "meta-not-json",
                                    "meta %r is not valid JSON" % (meta[:40],), where))
    return Result(issues)


def validate_many(sections: Iterable[CrossSection]) -> Result:
    issues: List[Issue] = []
    for n, section in enumerate(sections):
        label = section.sharedstreetid or "feature %d" % n
        issues.extend(validate_section(section, where=label).issues)
    return Result(issues)
