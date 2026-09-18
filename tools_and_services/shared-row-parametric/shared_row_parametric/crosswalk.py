"""Conversion between the crosswalk schema and cross-sections.

The crosswalk representation is one row per slice, keyed by
``SharedStreetID`` + ``rowindex`` (see specification/MarkdownTables/Crosswalk.md).
It is the editable pivot between the flat additive table and the nested slice
representation: a plain GIS or SQL table that still carries an ordered list.
"""

from __future__ import annotations

import json
from collections import OrderedDict
from typing import Any, Dict, Iterable, List, Optional, Sequence

from .model import CrossSection, Slice

COLUMNS = (
    "SharedStreetID", "rowindex", "type", "width", "height",
    "direction", "material", "meta",
)


def to_rows(section: CrossSection) -> List[Dict[str, Any]]:
    """Explode a cross-section into crosswalk rows, ordered left to right."""
    rows = []
    for i, s in enumerate(section.slices):
        rows.append({
            "SharedStreetID": section.sharedstreetid,
            "rowindex": i,
            "type": s.type,
            "width": s.width,
            "height": s.height,
            "direction": s.direction,
            "material": s.material,
            "meta": json.dumps(s.meta) if s.meta else None,
        })
    return rows


def from_rows(
    rows: Iterable[Dict[str, Any]],
    *,
    geometry: Optional[Dict[str, Any]] = None,
    sharedstreetid: Optional[str] = None,
) -> CrossSection:
    """Rebuild one cross-section from its crosswalk rows.

    Rows are sorted by ``rowindex``; a missing index keeps input order.
    """
    rows = list(rows)
    indexed = [r for r in rows if r.get("rowindex") is not None]
    if len(indexed) == len(rows):
        rows.sort(key=lambda r: int(r["rowindex"]))
    ssid = sharedstreetid
    if ssid is None:
        for r in rows:
            value = r.get("SharedStreetID", r.get("sharedstreetid"))
            if value is not None:
                ssid = str(value)
                break
    return CrossSection(
        slices=tuple(Slice.from_dict(r) for r in rows),
        sharedstreetid=ssid,
        geometry=geometry,
    )


def to_feature_collection(sections: Sequence[CrossSection]) -> Dict[str, Any]:
    """One feature per slice, each repeating its segment's geometry."""
    features = []
    for section in sections:
        for row in to_rows(section):
            features.append({
                "type": "Feature",
                "geometry": section.geometry,
                "properties": row,
            })
    return {"type": "FeatureCollection", "features": features}


def from_feature_collection(collection: Dict[str, Any]) -> List[CrossSection]:
    """Group crosswalk features back into cross-sections.

    Grouping is by ``SharedStreetID``; features whose id is null or repeated
    across different geometries are grouped by geometry as well, so sample
    data with unpopulated ids still round-trips.
    """
    groups: "OrderedDict[Any, Dict[str, Any]]" = OrderedDict()
    for feature in collection.get("features", []):
        props = dict(feature.get("properties") or {})
        geometry = feature.get("geometry")
        ssid = props.get("SharedStreetID", props.get("sharedstreetid"))
        geom_key = json.dumps(geometry, sort_keys=True) if geometry else None
        key = (str(ssid) if ssid is not None else None, geom_key)
        entry = groups.setdefault(key, {"rows": [], "geometry": geometry})
        entry["rows"].append(props)
    return [
        from_rows(e["rows"], geometry=e["geometry"],
                  sharedstreetid=key[0])
        for key, e in groups.items()
    ]
