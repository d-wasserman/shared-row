"""Reading and writing the three shared-row representations.

Which representation a GeoJSON file holds is detectable from its properties,
so the tools can accept any of them without being told.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Sequence, Tuple

from . import additive as additive_mod
from . import crosswalk as crosswalk_mod
from .model import CrossSection, feature_collection

SLICE, ADDITIVE, CROSSWALK = "slice", "additive", "crosswalk"


def detect(collection: Dict[str, Any]) -> str:
    """Identify a FeatureCollection's representation."""
    features = collection.get("features") or []
    if not features:
        raise ValueError("no features to inspect")
    props = features[0].get("properties") or {}
    if "slices" in props:
        return SLICE
    if "rowindex" in props and "type" in props:
        return CROSSWALK
    known = set(additive_mod.ALIASES) | set(additive_mod.UNALIAS)
    if known & set(props):
        return ADDITIVE
    raise ValueError(
        "cannot tell which shared-row representation this is; properties are: %s"
        % ", ".join(sorted(props)[:12])
    )


def load(path: str, *, representation: str = "auto", **kwargs) -> Tuple[List[CrossSection], str]:
    """Load cross-sections from a GeoJSON file.

    Returns ``(sections, representation)``.
    """
    with open(path, "r", encoding="utf-8") as fh:
        collection = json.load(fh)
    if collection.get("type") == "Feature":
        collection = {"type": "FeatureCollection", "features": [collection]}
    rep = detect(collection) if representation == "auto" else representation
    if rep == SLICE:
        sections = [CrossSection.from_slice_feature(f) for f in collection["features"]]
    elif rep == ADDITIVE:
        sections = [additive_mod.from_additive_feature(f, **kwargs)
                    for f in collection["features"]]
    elif rep == CROSSWALK:
        sections = crosswalk_mod.from_feature_collection(collection)
    else:
        raise ValueError("unknown representation %r" % rep)
    return sections, rep


def dump(
    sections: Sequence[CrossSection],
    representation: str,
    *,
    stringify_slices: bool = True,
    shapefile_names: bool = False,
) -> Dict[str, Any]:
    """Serialise cross-sections into a FeatureCollection."""
    if representation == SLICE:
        return feature_collection(sections, stringify_slices=stringify_slices)
    if representation == CROSSWALK:
        return crosswalk_mod.to_feature_collection(sections)
    if representation == ADDITIVE:
        features = []
        for section in sections:
            feature, _ = additive_mod.to_additive_feature(
                section, shapefile_names=shapefile_names)
            features.append(feature)
        return {"type": "FeatureCollection", "features": features}
    raise ValueError("unknown representation %r" % representation)
