"""Immutable data model for a shared-row cross-section."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field, replace
from typing import Any, Dict, Iterable, Optional, Sequence, Tuple

from . import vocab

#: Widths are metres, heights centimetres; round to the centimetre.
WIDTH_PRECISION = 2
TOL = 1e-6


@dataclass(frozen=True)
class Slice:
    """One left-to-right slice of right-of-way.

    Mirrors the ``slices`` sub-attributes in specification/MarkdownTables/Slice.md:
    width in metres, height in centimetres relative to the road surface.
    """

    type: str
    width: float
    height: float = 0.0
    direction: str = "bidirectional"
    material: Optional[str] = None
    meta: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        object.__setattr__(self, "type", vocab.normalize_type(self.type))
        object.__setattr__(self, "width", round(float(self.width), WIDTH_PRECISION))
        object.__setattr__(self, "height", float(self.height))
        if self.material is None:
            object.__setattr__(self, "material", vocab.default_material(self.type))

    @property
    def mode(self) -> str:
        return vocab.mode_group(self.type)

    def with_width(self, width: float) -> "Slice":
        return replace(self, width=width)

    def to_dict(self, *, meta_as_json_string: bool = False) -> Dict[str, Any]:
        """Serialise to the specification's slice object."""
        meta = self.meta
        if meta_as_json_string and isinstance(meta, dict):
            meta = json.dumps(meta)
        return {
            "type": self.type,
            "width": self.width,
            "height": self.height,
            "direction": self.direction,
            "material": self.material,
            "meta": meta if meta else None,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Slice":
        meta = data.get("meta")
        # The repository's sample GeoJSON stores meta as a JSON *string* nested
        # inside an already string-encoded ``slices`` value. Accept either.
        if isinstance(meta, str) and meta.strip():
            try:
                meta = json.loads(meta)
            except (ValueError, TypeError):
                meta = {"note": meta}
        if not isinstance(meta, dict):
            meta = None
        return cls(
            type=data["type"],
            width=data.get("width") or 0.0,
            height=data.get("height") or 0.0,
            direction=data.get("direction") or "bidirectional",
            material=data.get("material"),
            meta=meta,
        )


@dataclass(frozen=True)
class CrossSection:
    """An ordered left-to-right sequence of slices for one street segment.

    "Left" and "right" are from the perspective of an observer looking from the
    geometry's start point toward its end point, per the specification.
    """

    slices: Tuple[Slice, ...] = ()
    sharedstreetid: Optional[str] = None
    geometry: Optional[Dict[str, Any]] = None
    #: Source fields carried through a conversion untouched (OSM ids, etc).
    passthrough: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        object.__setattr__(self, "slices", tuple(self.slices))

    # -- geometry -------------------------------------------------------------

    @property
    def total_width(self) -> float:
        return round(sum(s.width for s in self.slices), WIDTH_PRECISION)

    @property
    def length_m(self) -> Optional[float]:
        """Geodesic length of the segment in metres, if geometry is present."""
        if not self.geometry:
            return None
        coords = self.geometry.get("coordinates") or []
        if len(coords) < 2:
            return None
        total = 0.0
        for (lon1, lat1), (lon2, lat2) in zip(coords, coords[1:]):
            total += _haversine_m(lon1, lat1, lon2, lat2)
        return total

    # -- queries --------------------------------------------------------------

    def of_type(self, *types: str) -> Tuple[int, ...]:
        wanted = {vocab.normalize_type(t) for t in types}
        return tuple(i for i, s in enumerate(self.slices) if s.type in wanted)

    def width_of_type(self, *types: str) -> float:
        return round(sum(self.slices[i].width for i in self.of_type(*types)), WIDTH_PRECISION)

    #: Types that are unambiguously central when present.
    CENTRE_TYPES = ("median", "turn_lane")
    #: Types that are central only when they actually sit near the middle --
    #: a kerbside bus lane must not be mistaken for a centre transitway.
    CENTRE_IF_BALANCED = ("transit", "bus_lane", "limitless")

    def center_index(self, *, balance_tolerance: float = 0.15) -> Optional[int]:
        """Index of the centre slice, or None if the section has no centre.

        Medians and centre turn lanes always qualify. A transitway, bus lane
        or shared space qualifies only if the widths either side of it are
        balanced to within ``balance_tolerance`` of the total width, so that
        a kerbside bus lane is not treated as a centre running one.
        """
        candidates = list(self.of_type(*self.CENTRE_TYPES))
        if not candidates:
            slack = max(balance_tolerance * self.total_width, 0.5)
            for i in self.of_type(*self.CENTRE_IF_BALANCED):
                left = sum(x.width for x in self.slices[:i])
                right = sum(x.width for x in self.slices[i + 1:])
                if abs(left - right) <= slack:
                    candidates.append(i)
        if not candidates:
            return None
        # The centre is the candidate whose flanking widths are most balanced.
        best, best_delta = None, None
        for i in candidates:
            left = sum(s.width for s in self.slices[:i])
            right = sum(s.width for s in self.slices[i + 1:])
            delta = abs(left - right)
            if best_delta is None or delta < best_delta:
                best, best_delta = i, delta
        return best

    def center_span(self) -> Optional[Tuple[int, int]]:
        """Half-open index range of the contiguous centre run.

        A ``median_turn_lane`` is often stored as a turn lane pocket plus the
        median remainder in two adjacent slices -- the encoding this
        repository's own sample data uses for segment 38. Both belong to the
        single ``Center_Lane`` column, so they have to be found together or
        the median's width is lost on the way to the additive schema.
        """
        ci = self.center_index()
        if ci is None:
            return None
        if self.slices[ci].type not in self.CENTRE_TYPES:
            return ci, ci + 1
        lo = ci
        while lo > 0 and self.slices[lo - 1].type in self.CENTRE_TYPES:
            lo -= 1
        hi = ci + 1
        while hi < len(self.slices) and self.slices[hi].type in self.CENTRE_TYPES:
            hi += 1
        return lo, hi

    def split_centre_span(self):
        """Like :meth:`split_sides`, but the centre is every centre slice.

        Returns ``(left, centre_slices, right)`` with ``centre_slices`` a
        tuple, possibly empty.
        """
        span = self.center_span()
        if span is None:
            left, centre, right = self.split_sides()
            return left, ((centre,) if centre is not None else ()), right
        lo, hi = span
        return self.slices[:lo], self.slices[lo:hi], self.slices[hi:]

    def split_sides(self) -> Tuple[Tuple[Slice, ...], Optional[Slice], Tuple[Slice, ...]]:
        """Return ``(left, centre, right)``.

        A centre slice splits the section directly. Otherwise the split uses
        travel direction, which the specification defines for exactly this
        purpose: left-oriented lanes run toward the start point (``reverse``)
        and right-oriented lanes toward the end point (``forward``). The
        boundary is placed in the gap between the two runs, at whichever
        index balances the sides best.

        Splitting at the width midpoint instead would mis-assign lanes on any
        asymmetric section -- a street with one lane one way and two the
        other would come back with its sides swapped.
        """
        ci = self.center_index()
        if ci is not None:
            return self.slices[:ci], self.slices[ci], self.slices[ci + 1:]

        lo, hi = self._direction_gap()
        if lo is None:
            lo, hi = 0, len(self.slices)
        best, best_delta = lo, None
        for b in range(lo, hi + 1):
            left = sum(s.width for s in self.slices[:b])
            right = sum(s.width for s in self.slices[b:])
            delta = abs(left - right)
            if best_delta is None or delta < best_delta:
                best, best_delta = b, delta
        return self.slices[:best], None, self.slices[best:]

    def _direction_gap(self):
        """Index range where the left/right boundary may legally fall.

        Returns ``(low, high)`` bracketing the undirected slices between the
        last reverse-running slice and the first forward-running one, or
        ``(None, None)`` if the directions are interleaved and so unusable.
        """
        reverse = [i for i, s in enumerate(self.slices) if s.direction == "reverse"]
        forward = [i for i, s in enumerate(self.slices) if s.direction == "forward"]
        if not reverse or not forward:
            return None, None
        if max(reverse) > min(forward):
            return None, None  # interleaved; fall back to a free choice
        return max(reverse) + 1, min(forward)

    # -- transformation helpers ----------------------------------------------

    def with_slices(self, slices: Iterable[Slice]) -> "CrossSection":
        return replace(self, slices=tuple(slices))

    def mirrored(self) -> "CrossSection":
        """Reverse the section, flipping per-slice travel direction."""
        flip = {"forward": "reverse", "reverse": "forward"}
        return self.with_slices(
            replace(s, direction=flip.get(s.direction, s.direction))
            for s in reversed(self.slices)
        )

    # -- serialisation --------------------------------------------------------

    def to_slice_feature(self, *, stringify_slices: bool = True) -> Dict[str, Any]:
        """Build a GeoJSON Feature in the Slice representation.

        ``stringify_slices`` reproduces the encoding used by this repository's
        own sample data, where ``slices`` is a JSON *string* inside
        ``properties``. Set it False to emit a real nested JSON array.
        """
        payload = [s.to_dict(meta_as_json_string=stringify_slices) for s in self.slices]
        props: Dict[str, Any] = dict(self.passthrough)
        props["sharedstreetid"] = self.sharedstreetid
        props["slices"] = json.dumps(payload) if stringify_slices else payload
        return {"type": "Feature", "geometry": self.geometry, "properties": props}

    @classmethod
    def from_slice_feature(cls, feature: Dict[str, Any]) -> "CrossSection":
        props = dict(feature.get("properties") or {})
        raw = props.pop("slices", None)
        if isinstance(raw, str):
            raw = json.loads(raw) if raw.strip() else []
        raw = raw or []
        ssid = props.pop("sharedstreetid", None) or props.pop("SharedStreetID", None)
        return cls(
            slices=tuple(Slice.from_dict(s) for s in raw),
            sharedstreetid=None if ssid is None else str(ssid),
            geometry=feature.get("geometry"),
            passthrough=props,
        )

    def describe(self) -> str:
        parts = ["%s %.2f" % (s.type, s.width) for s in self.slices]
        return " | ".join(parts) + "  = %.2f m" % self.total_width


def _haversine_m(lon1, lat1, lon2, lat2) -> float:
    r = 6371008.8  # IUGG mean earth radius, metres
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def feature_collection(sections: Sequence[CrossSection], **kwargs) -> Dict[str, Any]:
    return {
        "type": "FeatureCollection",
        "features": [s.to_slice_feature(**kwargs) for s in sections],
    }
