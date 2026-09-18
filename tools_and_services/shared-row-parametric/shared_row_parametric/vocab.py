"""Controlled vocabularies transcribed from the shared-row specification.

Sources (in this repository):
  specification/MarkdownTables/Slice.md     -> slice types, meta tags
  specification/MarkdownTables/Additive.md  -> ``*_Meta`` enumerations
  specification/MarkdownTables/Crosswalk.md -> crosswalk columns

Everything here is data, not policy: the specification is explicit that new
and emerging lane types are permitted, so the validator treats an unknown
type as a warning rather than an error.
"""

# --- Slice types, grouped as the Slice Types table groups them ----------------

AUTOMOTIVE_DEDICATED = ("drive_lane", "turn_lane")

NON_AUTOMOTIVE_DEDICATED = (
    "sidewalk",
    "bike_lane",
    "bus_lane",
    "transit",
    "path",
)

MIXED_LANES = ("limitless",)

CURB_ZONE = (
    "flex_zone",
    "parking",
    "parklet",
    "commercial_loading",
    "passenger_loading",
    "transit_stop",
    "commercial_activity",
    "bike_parking",
    "bike_share",
    "dockless_parking",
    "construction_zone",
    "tow_away_zone",
)

MISCELLANEOUS = (
    "median",
    "buffer",
    "temporary",
    "transit_shelter",
    "planting_strip",
    "filter_strip",
    "canal",
)

SLICE_TYPES = (
    AUTOMOTIVE_DEDICATED
    + NON_AUTOMOTIVE_DEDICATED
    + MIXED_LANES
    + CURB_ZONE
    + MISCELLANEOUS
)

SLICE_TYPE_GROUPS = {
    "automotive_dedicated": AUTOMOTIVE_DEDICATED,
    "non_automotive_dedicated": NON_AUTOMOTIVE_DEDICATED,
    "mixed_lanes": MIXED_LANES,
    "curb_zone": CURB_ZONE,
    "miscellaneous": MISCELLANEOUS,
}

#: Types seen in this repository's sample GeoJSON that are not in the
#: specification tables. Accepted on read, normalised on write. ``auto_parking``
#: appears 26 times in specification/Samples/Schema_Crosswalk.
TYPE_ALIASES = {
    "auto_parking": "parking",
    "commericial_loading": "commercial_loading",  # misspelled in Additive.md
    "walkway": "sidewalk",
    "drive": "drive_lane",
    "bike": "bike_lane",
}

DIRECTIONS = ("forward", "reverse", "bidirectional")

# --- Mode groups, for allocation metrics -------------------------------------
#
# A slice belongs to exactly one mode group. ``green`` is separated out from
# ``other`` because vegetated allocation is usually reported on its own.

MODE_GROUPS = {
    "pedestrian": ("sidewalk", "path", "parklet", "commercial_activity"),
    "bicycle": ("bike_lane", "bike_parking", "bike_share", "dockless_parking"),
    "transit": ("bus_lane", "transit", "transit_stop", "transit_shelter"),
    "automobile": (
        "drive_lane",
        "turn_lane",
        "parking",
        "limitless",
        "passenger_loading",
        "commercial_loading",
        "tow_away_zone",
        "flex_zone",
    ),
    "green": ("planting_strip", "filter_strip", "canal"),
    "other": ("median", "buffer", "temporary", "construction_zone"),
}

_MODE_OF = {t: g for g, types in MODE_GROUPS.items() for t in types}

#: Mode groups counted as "sustainable" / non-auto allocation.
SUSTAINABLE_MODES = ("pedestrian", "bicycle", "transit", "green")


def normalize_type(slice_type):
    """Map a known alias onto its specification-compliant type name."""
    if slice_type is None:
        return None
    key = str(slice_type).strip().lower()
    return TYPE_ALIASES.get(key, key)


def mode_group(slice_type):
    """Return the mode group for a slice type, or ``'other'`` if unknown."""
    return _MODE_OF.get(normalize_type(slice_type), "other")


def is_known_type(slice_type):
    return normalize_type(slice_type) in SLICE_TYPES


# --- Additive ``*_Meta`` enumerations ----------------------------------------

SIDEWALK_FURNITURE_META = (
    "vegetated",
    "vegetated_with_trees",
    "vegetated_with_tree_curb_cuts",
    "filter_strip",
    "transit_shelter",
    "complex",
)

BIKE_BUFFER_META = (
    "paint", "post", "curb", "planter", "separator", "vegetated",
    "vegetated_with_trees", "vegetated_with_tree_curb_cuts",
    "stone", "brick", "bollard", "other",
)

PARKING_LANE_META = (
    "parking", "passenger_loading", "commercial_loading", "parklet",
    "bike_share", "dockless_parking", "bike_parking", "tow_away_zone",
    "commercial_activity", "transit_stop", "construction_zone", "flex_zone",
)

TRANSIT_META = ("bus", "hov", "rail", "bus_bike")

CENTER_LANE_META = ("median", "turn_lane", "boulevard", "barrier", "median_turn_lane")

CROSSWALK_META = ("continental", "transverse", "ladder", "zebra", "textured", "other")

OFF_STREET_META = ("asphalt", "gravel", "dirt", "stone", "brick")

#: ``Center_Lane_Meta`` value -> slice type used in a sliced representation.
CENTER_META_TO_TYPE = {
    "median": "median",
    "turn_lane": "turn_lane",
    "median_turn_lane": "turn_lane",
    "boulevard": "median",
    "barrier": "median",
}

#: Default paving material by slice type, used when a template or source
#: record leaves material unset. The specification notes materials "can assume
#: default values".
DEFAULT_MATERIALS = {
    "sidewalk": "concrete",
    "median": "concrete",
    "planting_strip": "vegetation",
    "filter_strip": "vegetation",
    "transit_shelter": "concrete",
    "parklet": "wood",
    "path": "asphalt",
    "canal": "water",
}
DEFAULT_MATERIAL_FALLBACK = "asphalt"

#: Typical curb height in centimetres (6 in), the value used throughout the
#: repository's own sample data.
CURB_HEIGHT_CM = 15.24


def default_material(slice_type):
    return DEFAULT_MATERIALS.get(normalize_type(slice_type), DEFAULT_MATERIAL_FALLBACK)
