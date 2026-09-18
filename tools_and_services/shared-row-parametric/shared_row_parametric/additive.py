"""Conversion between the additive (flat, one-row-per-segment) schema and
:class:`~shared_row_parametric.model.CrossSection`.

Ordering follows the convention used by this repository's own sample data:
per side, from the outside edge inward::

    [frontage] [through] [furniture] <kerb zone> [transit] [drive_1 .. drive_n]

with travel lanes numbered from the kerb inward, so ``Through_Lane_1`` is the
outermost lane on each side. That was verified against every multi-lane
segment in ``specification/Samples`` whose lane widths differ (10 of 10).

The kerb zone order is a *parameter*, because both arrangements occur in the
sample data: segments 5 and 7 place the bike lane inboard of parking, while
segment 9 places it behind parking.

Known deviation from ``Additive.md``: that table gives the left transit
columns the shapefile aliases ``RTran_Ln`` / ``RTran_Meta``, which collide
with the right side's. This module emits ``LTran_Ln`` / ``LTran_Meta``
instead; see :data:`LEFT_TRANSIT_ALIAS_NOTE`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from . import vocab
from .model import WIDTH_PRECISION, CrossSection, Slice

LEFT_TRANSIT_ALIAS_NOTE = (
    "Additive.md lists RTran_Ln/RTran_Meta as the shapefile aliases for both "
    "Left_Transit_Lane and Right_Transit_Lane; LTran_Ln/LTran_Meta are used "
    "for the left side here to keep the names unique."
)

#: Long field name -> 10-character shapefile-safe alias, per Additive.md.
ALIASES: Dict[str, str] = {
    "SharedStreetID": "SSID",
    "Center_Lane": "Center_Ln",
    "Center_Lane_Meta": "Cent_Meta",
    "End_Crosswalk_Width": "E_X_Wlk",
    "Begin_Crosswalk_Width": "B_X_Wlk",
    "End_Crosswalk_Meta": "E_X_W_Meta",
    "Begin_Crosswalk_Meta": "B_X_W_Meta",
    "Off_Street_Width": "Off_St_W",
    "Off_Street_Meta": "Off_St_M",
}
for _side, _p in (("Right", "R"), ("Left", "L")):
    ALIASES.update({
        "%s_Sidewalk_Frontage_Zone" % _side: "%sSW_Frnt_Z" % _p,
        "%s_Sidewalk_Through_Zone" % _side: "%sSW_Thru_Z" % _p,
        "%s_Sidewalk_Furniture_Zone" % _side: "%sSW_Furn_Z" % _p,
        "%s_Sidewalk_Furniture_Meta" % _side: "%sSFW_Furn_M" % _p,
        "%s_Bike_Lane" % _side: "%sBk_Ln" % _p,
        "%s_Bike_Buffer" % _side: "%sBk_Buff" % _p,
        "%s_Bike_Buffer_Meta" % _side: "%sB_Bu_Meta" % _p,
        "%s_Parking_Lane" % _side: "%s_Prk_Ln" % _p,
        "%s_Parking_Lane_Meta" % _side: "%s_Prk_Meta" % _p,
        "%s_Transit_Lane" % _side: "%sTran_Ln" % _p,
        "%s_Transit_Meta" % _side: "%sTran_Meta" % _p,
        "%s_Through_Lane_X" % _side: "%sThru_Ln_X" % _p,
    })
    for _i in (1, 2, 3, 4):
        ALIASES["%s_Through_Lane_%d" % (_side, _i)] = "%sThru_Ln_%d" % (_p, _i)

#: alias -> long name, for reading records written with shapefile names.
UNALIAS = {v: k for k, v in ALIASES.items()}

NUMBERED_LANES = (1, 2, 3, 4)

#: Kerb-zone arrangements, outside edge inward.
ARRANGEMENTS = {
    "bike_inside_parking": ("parking", "bike", "buffer"),
    "bike_behind_parking": ("bike", "buffer", "parking"),
}
DEFAULT_ARRANGEMENT = "bike_inside_parking"

#: Furniture-zone meta value -> slice type, when semantic mapping is on.
FURNITURE_TYPE = {
    "filter_strip": "filter_strip",
    "transit_shelter": "transit_shelter",
    "vegetated": "planting_strip",
    "vegetated_with_trees": "planting_strip",
    "vegetated_with_tree_curb_cuts": "planting_strip",
}

_FURNITURE_TYPES = ("planting_strip", "filter_strip", "transit_shelter")
_TRANSIT_TYPES = ("transit", "bus_lane")
_LANE_TYPES = ("drive_lane", "turn_lane", "limitless")


@dataclass
class ConversionReport:
    """What a conversion could not represent."""

    lost: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    #: Kerb-zone arrangement detected per side, to pass back to
    #: :func:`from_additive` for a faithful round trip.
    arrangement: Optional[str] = None

    @property
    def lossless(self) -> bool:
        return not self.lost

    def summary(self) -> str:
        if self.lossless and not self.notes:
            return "lossless"
        lines = []
        if self.lost:
            lines.append("dropped (no additive column): " + ", ".join(self.lost))
        if self.arrangement:
            lines.append("kerb arrangement: " + self.arrangement)
        lines.extend("note: " + n for n in self.notes)
        return "\n".join(lines)


#: Passthrough key holding ``*_Meta`` values whose zone width is zero. Real
#: data carries these (every segment in specification/Samples sets a furniture
#: meta while the furniture zone is 0.0), and dropping them loses information.
ORPHAN_KEY = "__srow_orphan_meta__"

#: ``*_Meta`` columns paired with the width column that must be non-zero for
#: the meta to have a slice to live on.
META_PAIRS = tuple(
    ("%s_%s_Meta" % (side, stem), "%s_%s" % (side, width_stem))
    for side in ("Left", "Right")
    for stem, width_stem in (
        ("Sidewalk_Furniture", "Sidewalk_Furniture_Zone"),
        ("Bike_Buffer", "Bike_Buffer"),
        ("Parking_Lane", "Parking_Lane"),
        ("Transit", "Transit_Lane"),
    )
)


def _get(record: Dict[str, Any], name: str, default=None):
    """Read a field by long name, falling back to its shapefile alias."""
    if name in record and record[name] is not None:
        return record[name]
    alias = ALIASES.get(name)
    if alias and alias in record and record[alias] is not None:
        return record[alias]
    return default


def _num(record: Dict[str, Any], name: str) -> float:
    value = _get(record, name, 0.0)
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _text(record: Dict[str, Any], name: str) -> Optional[str]:
    value = _get(record, name)
    if value is None:
        return None
    value = str(value).strip()
    return value or None


# ---------------------------------------------------------------------------
# additive record -> CrossSection
# ---------------------------------------------------------------------------

def _side_slices(record, side, arrangement, semantic_furniture) -> List[Slice]:
    """Build one side's slices, ordered from the outside edge inward."""
    direction = "reverse" if side == "Left" else "forward"
    out: List[Slice] = []

    def add(stype, width, **kw):
        if width and width > 0:
            out.append(Slice(type=stype, width=width, **kw))

    # --- sidewalk zones: frontage, through, furniture ---------------------
    add("sidewalk", _num(record, "%s_Sidewalk_Frontage_Zone" % side),
        height=vocab.CURB_HEIGHT_CM, meta={"zone": "frontage"})
    add("sidewalk", _num(record, "%s_Sidewalk_Through_Zone" % side),
        height=vocab.CURB_HEIGHT_CM, meta={"zone": "through"})

    furn_meta = _text(record, "%s_Sidewalk_Furniture_Meta" % side)
    furn_type = "sidewalk"
    if semantic_furniture and furn_meta:
        furn_type = FURNITURE_TYPE.get(furn_meta.lower(), "sidewalk")
    meta = {"zone": "furniture"}
    if furn_meta:
        meta["furniture"] = furn_meta
    add(furn_type, _num(record, "%s_Sidewalk_Furniture_Zone" % side),
        height=vocab.CURB_HEIGHT_CM, meta=meta)

    # --- kerb zone, in the requested arrangement --------------------------
    parts = ARRANGEMENTS.get(arrangement) or ARRANGEMENTS[DEFAULT_ARRANGEMENT]
    for part in parts:
        if part == "parking":
            pmeta = _text(record, "%s_Parking_Lane_Meta" % side)
            ptype = vocab.normalize_type(pmeta) if pmeta else "parking"
            if ptype not in vocab.SLICE_TYPES:
                ptype = "parking"
            add(ptype, _num(record, "%s_Parking_Lane" % side),
                meta={"parking_use": pmeta} if pmeta else None)
        elif part == "bike":
            add("bike_lane", _num(record, "%s_Bike_Lane" % side), direction=direction)
        elif part == "buffer":
            bmeta = _text(record, "%s_Bike_Buffer_Meta" % side)
            add("buffer", _num(record, "%s_Bike_Buffer" % side),
                material=bmeta if bmeta else None,
                meta={"separation": bmeta, "protects": "bike_lane"} if bmeta
                     else {"protects": "bike_lane"})

    # --- side-running transit, inboard of the kerb zone -------------------
    tmeta = _text(record, "%s_Transit_Meta" % side)
    ttype = "bus_lane" if (tmeta or "").lower() in ("bus", "bus_bike") else "transit"
    add(ttype, _num(record, "%s_Transit_Lane" % side), direction=direction,
        meta={"mode": tmeta} if tmeta else None)

    # --- travel lanes, kerb inward ----------------------------------------
    for i in NUMBERED_LANES:
        add("drive_lane", _num(record, "%s_Through_Lane_%d" % (side, i)),
            direction=direction, meta={"lane": i})
    add("drive_lane", _num(record, "%s_Through_Lane_X" % side),
        direction=direction, meta={"lane": "X"})
    return out


def from_additive(
    record: Dict[str, Any],
    *,
    geometry: Optional[Dict[str, Any]] = None,
    arrangement: str = DEFAULT_ARRANGEMENT,
    semantic_furniture: bool = True,
    keep_passthrough: bool = True,
) -> CrossSection:
    """Build a cross-section from one additive record.

    ``arrangement`` selects the kerb-zone order (see :data:`ARRANGEMENTS`).
    ``semantic_furniture`` maps a vegetated furniture zone onto
    ``planting_strip`` rather than a second ``sidewalk`` slice; set it False
    to reproduce the encoding in this repository's sample data.
    """
    if arrangement not in ARRANGEMENTS:
        raise ValueError(
            "unknown arrangement %r; expected one of %s"
            % (arrangement, ", ".join(sorted(ARRANGEMENTS)))
        )
    left = _side_slices(record, "Left", arrangement, semantic_furniture)
    right = _side_slices(record, "Right", arrangement, semantic_furniture)

    centre: List[Slice] = []
    centre_width = _num(record, "Center_Lane")
    if centre_width > 0:
        cmeta = (_text(record, "Center_Lane_Meta") or "median").lower()
        ctype = vocab.CENTER_META_TO_TYPE.get(cmeta)
        if ctype is None:
            # Accept a slice type written into the field by to_additive().
            normalized = vocab.normalize_type(cmeta)
            ctype = normalized if normalized in vocab.SLICE_TYPES else "median"
        meta: Dict[str, Any] = {"center_lane_meta": cmeta}
        if cmeta == "median_turn_lane":
            meta["remainder_allocation"] = "median"
        centre.append(Slice(
            type=ctype, width=centre_width,
            height=vocab.CURB_HEIGHT_CM if ctype == "median" else 0.0,
            direction="bidirectional", meta=meta,
        ))

    off_street = _num(record, "Off_Street_Width")
    off_prefix: List[Slice] = []
    if off_street > 0:
        off_prefix.append(Slice(
            type="path", width=off_street,
            material=_text(record, "Off_Street_Meta") or "asphalt",
            meta={"off_street": True, "shared_use": True},
        ))

    passthrough: Dict[str, Any] = {}
    if keep_passthrough:
        known = set(ALIASES) | set(UNALIAS)
        passthrough = {k: v for k, v in record.items() if k not in known}
        orphans = {}
        for meta_col, width_col in META_PAIRS:
            if _text(record, meta_col) and _num(record, width_col) <= 0:
                orphans[meta_col] = _text(record, meta_col)
        if orphans:
            passthrough[ORPHAN_KEY] = orphans

    ssid = _text(record, "SharedStreetID")
    # left side reads outside-in; the right side is appended outside-in reversed
    return CrossSection(
        slices=tuple(off_prefix) + tuple(left) + tuple(centre) + tuple(reversed(right)),
        sharedstreetid=ssid,
        geometry=geometry,
        passthrough=passthrough,
    )


# ---------------------------------------------------------------------------
# CrossSection -> additive record
# ---------------------------------------------------------------------------

def _blank_record() -> Dict[str, Any]:
    rec: Dict[str, Any] = {"SharedStreetID": None}
    for side in ("Left", "Right"):
        rec["%s_Sidewalk_Frontage_Zone" % side] = 0.0
        rec["%s_Sidewalk_Through_Zone" % side] = 0.0
        rec["%s_Sidewalk_Furniture_Zone" % side] = 0.0
        rec["%s_Sidewalk_Furniture_Meta" % side] = None
        rec["%s_Bike_Lane" % side] = 0.0
        rec["%s_Bike_Buffer" % side] = 0.0
        rec["%s_Bike_Buffer_Meta" % side] = None
        rec["%s_Parking_Lane" % side] = 0.0
        rec["%s_Parking_Lane_Meta" % side] = None
        rec["%s_Transit_Lane" % side] = 0.0
        rec["%s_Transit_Meta" % side] = None
        for i in NUMBERED_LANES:
            rec["%s_Through_Lane_%d" % (side, i)] = 0.0
        rec["%s_Through_Lane_X" % side] = 0.0
    rec["Center_Lane"] = 0.0
    rec["Center_Lane_Meta"] = None
    return rec


def _sidewalk_zone_order(count: int) -> Tuple[str, ...]:
    """Which sidewalk zones ``count`` bare sidewalk slices represent.

    Matches the sample data, where two sidewalk slices are the through and
    furniture zones (segments 7 and 9) and one is the through zone.
    """
    if count <= 1:
        return ("through",)
    if count == 2:
        return ("through", "furniture")
    return ("frontage", "through", "furniture")


def _fill_side(rec, side, slices: Sequence[Slice], report: ConversionReport) -> None:
    """Write one side's slices (ordered outside-in) into the record."""
    prefix = "%s_" % side
    lane_no = 0

    bare_sidewalks = [s for s in slices
                      if s.type == "sidewalk" and not (s.meta or {}).get("zone")]
    fallback_zones = iter(_sidewalk_zone_order(len(bare_sidewalks)))

    for s in slices:
        meta = s.meta or {}
        stype = s.type

        if stype == "sidewalk":
            zone = meta.get("zone") or next(fallback_zones, "furniture")
            key = "%sSidewalk_%s_Zone" % (prefix, zone.capitalize())
            rec[key] = round(rec.get(key, 0.0) + s.width, WIDTH_PRECISION)
            if zone == "furniture" and meta.get("furniture"):
                rec["%sSidewalk_Furniture_Meta" % prefix] = meta["furniture"]
            continue

        if stype in _FURNITURE_TYPES:
            key = "%sSidewalk_Furniture_Zone" % prefix
            rec[key] = round(rec.get(key, 0.0) + s.width, WIDTH_PRECISION)
            rec["%sSidewalk_Furniture_Meta" % prefix] = (
                meta.get("furniture")
                or ("transit_shelter" if stype == "transit_shelter"
                    else "filter_strip" if stype == "filter_strip"
                    else "vegetated")
            )
            continue

        if stype == "bike_lane":
            rec["%sBike_Lane" % prefix] = round(
                rec["%sBike_Lane" % prefix] + s.width, WIDTH_PRECISION)
            continue

        if stype == "buffer":
            rec["%sBike_Buffer" % prefix] = round(
                rec["%sBike_Buffer" % prefix] + s.width, WIDTH_PRECISION)
            sep = meta.get("separation") or s.material
            if sep:
                rec["%sBike_Buffer_Meta" % prefix] = sep
            continue

        if stype in vocab.CURB_ZONE:
            rec["%sParking_Lane" % prefix] = round(
                rec["%sParking_Lane" % prefix] + s.width, WIDTH_PRECISION)
            rec["%sParking_Lane_Meta" % prefix] = meta.get("parking_use") or stype
            continue

        if stype in _TRANSIT_TYPES:
            rec["%sTransit_Lane" % prefix] = round(
                rec["%sTransit_Lane" % prefix] + s.width, WIDTH_PRECISION)
            rec["%sTransit_Meta" % prefix] = (
                meta.get("mode") or ("bus" if stype == "bus_lane" else "rail"))
            continue

        if stype in _LANE_TYPES:
            if stype != "drive_lane":
                report.notes.append(
                    "%s slice on the %s side stored as a through lane; the "
                    "additive schema only has a centre column for it"
                    % (stype, side.lower())
                )
            # Lanes are renumbered from the kerb inward by position, so a
            # stale ``meta["lane"]`` from a previous conversion is ignored.
            lane_no += 1
            if lane_no <= 4:
                rec["%sThrough_Lane_%d" % (prefix, lane_no)] = s.width
            else:
                rec["%sThrough_Lane_X" % prefix] = round(
                    rec["%sThrough_Lane_X" % prefix] + s.width, WIDTH_PRECISION)
            continue

        if stype == "path":
            # The additive schema has no per-side path column, but it does
            # have Off_Street_*, whose meta enumeration is paving materials.
            rec["Off_Street_Width"] = round(
                (rec.get("Off_Street_Width") or 0.0) + s.width, WIDTH_PRECISION)
            rec["Off_Street_Meta"] = s.material or "asphalt"
            report.notes.append(
                "%s path %.2fm stored in Off_Street_Width, which is not "
                "per-side: two paths sum into one column" % (side.lower(), s.width)
            )
            continue

        report.lost.append("%s %s %.2fm" % (side.lower(), stype, s.width))


def to_additive(
    section: CrossSection,
    *,
    shapefile_names: bool = False,
    include_passthrough: bool = True,
) -> Tuple[Dict[str, Any], ConversionReport]:
    """Flatten a cross-section into an additive record.

    Returns ``(record, report)``. The report lists slices that have no
    additive column, since the flat schema cannot represent every slice type.
    """
    report = ConversionReport()
    rec = _blank_record()
    rec["SharedStreetID"] = section.sharedstreetid

    left, centre_slices, right = section.split_centre_span()
    centre = _combine_centre(centre_slices, report)
    report.arrangement = _detect_arrangement(left, tuple(reversed(right)))
    _fill_side(rec, "Left", left, report)
    # the right side is stored outside-in, so walk it from the outer edge
    _fill_side(rec, "Right", tuple(reversed(right)), report)

    if centre is not None:
        rec["Center_Lane"] = centre.width
        cmeta = (centre.meta or {}).get("center_lane_meta")
        if cmeta:
            rec["Center_Lane_Meta"] = cmeta
        elif centre.type in ("median", "turn_lane"):
            rec["Center_Lane_Meta"] = centre.type
        else:
            # Center_Lane_Meta is enumerated median;turn_lane;boulevard;
            # barrier;median_turn_lane, so a centre transitway or shared
            # space has no valid value. The slice type is written instead so
            # the width and the meaning both survive a round trip.
            rec["Center_Lane_Meta"] = centre.type
            report.notes.append(
                "centre %s written to Center_Lane_Meta, which is outside the "
                "specification's enumeration for that field" % centre.type
            )
    elif not any(s.type in ("median", "turn_lane") for s in section.slices):
        rec["Center_Lane"] = 0.0
        rec["Center_Lane_Meta"] = None

    if include_passthrough:
        orphans = {}
        for k, v in (section.passthrough or {}).items():
            if k == ORPHAN_KEY:
                orphans = v or {}
                continue
            rec.setdefault(k, v)
        # Restore metas whose zone has zero width, which no slice can carry.
        for col, value in orphans.items():
            if not rec.get(col):
                rec[col] = value

    if shapefile_names:
        rec = {ALIASES.get(k, k): v for k, v in rec.items()}
        report.notes.append(LEFT_TRANSIT_ALIAS_NOTE)
    return rec, report


def _combine_centre(
    centre_slices: Sequence[Slice], report: ConversionReport
) -> Optional[Slice]:
    """Fold a contiguous centre run into the single Center_Lane slice.

    A turn lane beside a median becomes one ``median_turn_lane`` entry, which
    is the specification's value for exactly that arrangement.
    """
    if not centre_slices:
        return None
    if len(centre_slices) == 1:
        return centre_slices[0]
    total = round(sum(s.width for s in centre_slices), WIDTH_PRECISION)
    types = {s.type for s in centre_slices}
    if types == {"turn_lane", "median"}:
        cmeta, ctype = "median_turn_lane", "turn_lane"
    elif types == {"turn_lane"}:
        cmeta, ctype = "turn_lane", "turn_lane"
    else:
        cmeta, ctype = "median", "median"
    report.notes.append(
        "%d centre slices (%s) folded into Center_Lane = %.2f m as %r"
        % (len(centre_slices), ", ".join(sorted(types)), total, cmeta)
    )
    meta = dict(centre_slices[0].meta or {})
    meta["center_lane_meta"] = cmeta
    meta["centre_components"] = [
        {"type": s.type, "width": s.width} for s in centre_slices
    ]
    return Slice(
        type=ctype, width=total,
        height=max(s.height for s in centre_slices),
        direction="bidirectional",
        material=centre_slices[0].material,
        meta=meta,
    )


def _detect_arrangement(*sides: Sequence[Slice]) -> Optional[str]:
    """Infer the kerb-zone order from slices ordered outside-in.

    Returns None when a side has no bike lane or no parking, since the order
    is then unobservable.
    """
    seen = set()
    for side in sides:
        types = [s.type for s in side]
        if "bike_lane" not in types or not any(t in vocab.CURB_ZONE for t in types):
            continue
        bike = types.index("bike_lane")
        park = min(i for i, t in enumerate(types) if t in vocab.CURB_ZONE)
        seen.add("bike_behind_parking" if bike < park else "bike_inside_parking")
    if len(seen) == 1:
        return seen.pop()
    return None


def from_additive_feature(feature: Dict[str, Any], **kwargs) -> CrossSection:
    return from_additive(
        dict(feature.get("properties") or {}),
        geometry=feature.get("geometry"),
        **kwargs
    )


def to_additive_feature(section: CrossSection, **kwargs):
    rec, report = to_additive(section, **kwargs)
    feature = {"type": "Feature", "geometry": section.geometry, "properties": rec}
    return feature, report
