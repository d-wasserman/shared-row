"""Street archetype templates: the "system of defaults" the specification asks for.

A :class:`Template` is an ordered, left-to-right list of :class:`SliceSpec`
entries plus a filler type. Templates are normally written as a *half section*
and mirrored, which matches both the physical symmetry of most streets and the
mirrored ``Left_*`` / ``Right_*`` column structure of the additive schema.

The shipped library lives in ``templates.json`` next to this module so it can
be edited without touching code, per the specification's goal of defaults that
"can be further edited and enhanced". Load your own with
:func:`load_library`.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, replace
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from . import vocab
from .fit import FitResult, SliceSpec, fit

BUILTIN_LIBRARY = os.path.join(os.path.dirname(__file__), "templates.json")

#: Direction assigned to each side when a half section is mirrored. Per the
#: specification, right-oriented lanes run toward the geometry end point
#: (forward) and left-oriented lanes toward the start point (reverse).
LEFT_DIRECTION = "reverse"
RIGHT_DIRECTION = "forward"

#: Slice types that carry no travel direction of their own.
UNDIRECTED = (
    "sidewalk", "median", "buffer", "planting_strip", "filter_strip",
    "parking", "transit_shelter", "parklet", "canal", "flex_zone",
    "bike_parking", "bike_share", "dockless_parking", "construction_zone",
    "tow_away_zone", "commercial_activity", "transit_stop",
)


@dataclass(frozen=True)
class Template:
    """A parametric cross-section: slice specs in left-to-right order."""

    name: str
    description: str = ""
    specs: Tuple[SliceSpec, ...] = ()
    #: Type absorbing width that nothing else can take (None = report residual).
    filler: Optional[str] = None
    filler_index: Optional[int] = None
    #: Advisory right-of-way range this template is meant for, in metres.
    row_range: Optional[Tuple[float, float]] = None
    tags: Tuple[str, ...] = ()

    @property
    def preferred_width(self) -> float:
        return round(sum(s.preferred_width for s in self.specs), 2)

    @property
    def min_width(self) -> float:
        return round(sum(s.min_width for s in self.specs if s.required), 2)

    @property
    def max_width(self) -> float:
        return round(sum(s.max_width for s in self.specs), 2)

    def fit(self, row_width: Optional[float] = None, **kwargs) -> FitResult:
        """Allocate ``row_width`` across this template's slices."""
        kwargs.setdefault("filler", self.filler)
        kwargs.setdefault("filler_index", self.filler_index)
        return fit(self.specs, row_width, **kwargs)

    # -- editing --------------------------------------------------------------

    def with_spec(self, role: str, **changes) -> "Template":
        """Return a copy with one role's spec altered.

        >>> t.with_spec("left_bike", min_width=2.0, preferred_width=2.4)
        """
        found = False
        specs = []
        for s in self.specs:
            if s.role == role:
                specs.append(replace(s, **changes))
                found = True
            else:
                specs.append(s)
        if not found:
            raise KeyError("no slice with role %r in template %r" % (role, self.name))
        return replace(self, specs=tuple(specs))

    def without_role(self, *roles: str) -> "Template":
        wanted = set(roles)
        return replace(self, specs=tuple(s for s in self.specs if s.role not in wanted))

    def roles(self) -> Tuple[str, ...]:
        return tuple(s.role or s.type for s in self.specs)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "filler": self.filler,
            "row_range": list(self.row_range) if self.row_range else None,
            "tags": list(self.tags),
            "slices": [
                {
                    k: v for k, v in {
                        "type": s.type,
                        "role": s.role,
                        "pair": s.pair,
                        "min_width": s.min_width,
                        "preferred_width": s.preferred_width,
                        "max_width": s.max_width,
                        "priority": s.priority,
                        "required": s.required,
                        "flex": s.flex,
                        "direction": s.direction,
                        "height": s.height,
                        "material": s.material,
                        "meta": s.meta,
                    }.items() if v is not None
                }
                for s in self.specs
            ],
        }


def mirror_specs(
    half: Sequence[Dict[str, Any] | SliceSpec],
    centre: Optional[Dict[str, Any] | SliceSpec] = None,
) -> Tuple[SliceSpec, ...]:
    """Build a full section from a half section given kerb-to-centre.

    ``half`` is ordered from the outside edge inward. The result is
    ``left (outside -> in) + centre + right (in -> outside)``, with roles
    prefixed ``left_`` / ``right_``, a shared ``pair`` key per mirrored slice,
    and travel directions assigned per side.
    """
    def coerce(item) -> SliceSpec:
        return item if isinstance(item, SliceSpec) else SliceSpec.from_dict(item)

    half_specs = [coerce(h) for h in half]
    left: List[SliceSpec] = []
    right: List[SliceSpec] = []
    for i, spec in enumerate(half_specs):
        base_role = spec.role or "%s_%d" % (spec.type, i + 1)
        pair = spec.pair or base_role
        directed = spec.type not in UNDIRECTED
        left.append(replace(
            spec,
            role="left_%s" % base_role,
            pair=pair,
            direction=LEFT_DIRECTION if directed else spec.direction,
        ))
        right.append(replace(
            spec,
            role="right_%s" % base_role,
            pair=pair,
            direction=RIGHT_DIRECTION if directed else spec.direction,
        ))
    specs = list(left)
    if centre is not None:
        c = coerce(centre)
        specs.append(replace(c, role=c.role or "centre", pair=c.pair or "centre"))
    specs.extend(reversed(right))
    return tuple(specs)


def template_from_dict(data: Dict[str, Any]) -> Template:
    """Build a template from its JSON form.

    Two shapes are accepted: ``slices`` for an explicit full section, or
    ``half`` (+ optional ``centre``) for a mirrored half section.
    """
    name = data["name"]
    if "half" in data:
        specs = mirror_specs(data["half"], data.get("centre"))
    elif "slices" in data:
        specs = tuple(SliceSpec.from_dict(s) for s in data["slices"])
    else:
        raise ValueError("template %r needs either 'half' or 'slices'" % name)
    row_range = data.get("row_range")
    return Template(
        name=name,
        description=data.get("description", ""),
        specs=specs,
        filler=data.get("filler"),
        filler_index=data.get("filler_index"),
        row_range=tuple(row_range) if row_range else None,
        tags=tuple(data.get("tags", ())),
    )


def load_library(path: Optional[str] = None) -> Dict[str, Template]:
    """Load a template library from JSON. Defaults to the shipped library."""
    path = path or BUILTIN_LIBRARY
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    entries = data["templates"] if isinstance(data, dict) else data
    library: Dict[str, Template] = {}
    for entry in entries:
        tpl = template_from_dict(entry)
        library[tpl.name] = tpl
    return library


_CACHE: Dict[str, Dict[str, Template]] = {}


def library(path: Optional[str] = None) -> Dict[str, Template]:
    key = path or BUILTIN_LIBRARY
    if key not in _CACHE:
        _CACHE[key] = load_library(path)
    return _CACHE[key]


def get(name: str, path: Optional[str] = None) -> Template:
    lib = library(path)
    if name not in lib:
        raise KeyError(
            "unknown template %r; available: %s" % (name, ", ".join(sorted(lib)))
        )
    return lib[name]


def suggest(row_width: float, path: Optional[str] = None) -> List[Template]:
    """Templates whose advisory range contains ``row_width``, widest first.

    Templates without a declared range are included last, since they are
    usable at any width but are not evidence of a good match.
    """
    ranged, unranged = [], []
    for tpl in library(path).values():
        if tpl.row_range and tpl.row_range[0] <= row_width <= tpl.row_range[1]:
            ranged.append(tpl)
        elif not tpl.row_range:
            unranged.append(tpl)
    ranged.sort(key=lambda t: t.preferred_width, reverse=True)
    return ranged + unranged
