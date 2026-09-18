# shared-row-parametric

A parametric layer over the [shared-row specification](../../specification): describe
a street by a handful of parameters — right-of-way width, an archetype, which
modes matter — and get a specification-compliant cross-section out, in any of
the three shared-row representations.

This implements two objectives the specification sets out but leaves to
implementers: **a system of defaults that can be further edited and enhanced**
(objective 2) and **tools that work across platforms** (objective 4).

No dependencies. Python 3.8+, standard library only, so it also runs in the Python that
ships with ArcGIS Pro.

```
python3 -m shared_row_parametric templates
python3 -m shared_row_parametric generate main_street 22 --format ascii
python3 -m shared_row_parametric metrics ../../specification/Samples/Additive/additive_test_sample.geojson
```

## Why a parametric layer

The specification defines *how to write down* a cross-section. It does not say
how to **produce** one, and that is where the work actually is:

- A planner knows the right-of-way is 22 m and wants a main street in it. What
  widths does each element get?
- Existing data is an OSM-derived centreline file. What is a reasonable default
  cross-section to start editing from?
- A corridor has four travel lanes. What does removing two do to the space
  given to each mode, holding the kerb lines fixed?

All three are width-allocation problems over the specification's own
vocabulary. That is what this does.

## The model

A **`SliceSpec`** is a slice type plus the width range it may occupy:

| field | meaning |
|---|---|
| `min_width` | narrowest width at which this element is still worth building |
| `preferred_width` | what it gets when there is room |
| `max_width` | widening past this is waste |
| `priority` | higher is dropped first when space runs out |
| `required` | never dropped |
| `flex` | relative share of any shrink or growth (`0` pins the width) |
| `pair` | slices sharing a key are dropped together |

A **`Template`** is an ordered list of those, normally authored as a *half
section* and mirrored — which matches both the physical symmetry of most
streets and the mirrored `Left_*` / `Right_*` columns of the additive schema.

`min_width` is the load-bearing idea. Set it to `0` and a 22 m template
squeezed into 18 m will hand you a 0.26 m frontage zone, which is arithmetic,
not urban design. Set it to `0.6` and the allocator drops the frontage zone
instead — the answer a planner actually wants.

### Allocation

Deterministic and explainable, not an opaque optimiser — a planner has to be
able to say *why* the sidewalk came out at 1.8 m, so every adjustment is
recorded:

1. Start every slice at its preferred width.
2. **Over budget**: shrink toward minimums, distributing the deficit in
   proportion to `flex` (water-filling, so a slice that bottoms out passes the
   remainder to its neighbours). Still over? Drop slices by descending
   priority, never a `required` one, re-shrinking after each drop.
3. **Under budget**: grow toward maximums the same way, then hand any leftover
   to the template's filler slice.
4. Round to the centimetre and push the rounding residue into a centre slice,
   so the total matches the request exactly and the two sides stay symmetric.

```
$ python3 -m shared_row_parametric generate urban_arterial 26.5 --report
requested 26.50 m -> allocated 26.50 m (shrunk)
  left_sidewalk          2.40 -> 2.06 m
  left_bike_buffer       0.60 -> 0.43 m
  median                 3.00 -> 2.76 m
  ...
```

Infeasible requests say so and report the narrowest section achievable rather
than silently returning something that does not fit.

## Reallocation

Operators edit a section while **holding the total width constant** — the
property lines do not move, so any width a travel lane gives up has to
reappear somewhere else in the same section. `transfer` is the primitive;
`road_diet`, `set_travel_lanes`, `widen` and `coalesce` build on it.

```
$ python3 -m shared_row_parametric diet segment.geojson --protected --keep-lanes 1
mode             before     after     delta
-------------------------------------------
automobile       17.97m     8.67m    -9.30m
pedestrian        4.00m    10.70m    +6.70m
bicycle           3.40m     4.20m    +0.80m
-------------------------------------------
total            25.37m    25.37m    +0.00m

auto share  70.8% -> 34.2%  (-36.7 pts)
```

Travel lanes are removed from the inside out, so the kerbside lane survives.
That follows the specification's own convention, verified below.

## Metrics

Width and area allocation by mode, per segment or across a network
(length-weighted, because a 400 m arterial should not count the same as a 40 m
alley). Run over the 38 sample segments in this repository:

```
$ python3 -m shared_row_parametric metrics ../../specification/Samples/Additive/additive_test_sample.geojson
network: 38 segments, 6738 m total length, mean ROW 18.11 m

mode               area m2    share
-----------------------------------
automobile           77329    63.4%
pedestrian           26953    22.1%
bicycle               7664     6.3%
green                 6189     5.1%
other                 3885     3.2%
```

## Conversions

All three representations, in both directions, with auto-detection of which one
a file holds:

```
python3 -m shared_row_parametric convert in.geojson --format crosswalk
python3 -m shared_row_parametric convert in.geojson --format additive --shapefile-names
python3 -m shared_row_parametric validate in.geojson
python3 -m shared_row_parametric render in.geojson --out section.svg
```

Every one of this repository's 38 sample segments round-trips
additive → section → additive **field for field**, and crosswalk → additive
preserves width on all 38. Those are tests, not claims: `tests/test_roundtrip.py`.

### Conventions established from the sample data

The markdown tables do not state the left-to-right ordering, so it was derived
from the repository's own sample GeoJSON and is asserted in the tests:

```
left edge -> sidewalk zones -> kerb zone -> [transit] -> drive_1 .. drive_n
          -> CENTRE -> drive_n .. drive_1 -> [transit] -> kerb zone -> sidewalk zones -> right edge
```

- **Travel lanes are numbered from the kerb inward**, so `Through_Lane_1` is
  the *outermost* lane on each side. Verified by geometry-joining the additive
  and crosswalk samples across all 10 multi-lane segments whose lane widths
  differ: 10 of 10 agree.
- **The kerb-zone order is a parameter, not a constant.** Both arrangements
  occur in the sample data — segments 5 and 7 put the bike lane inboard of
  parking, segment 9 puts it behind parking — so `--arrangement` selects
  between `bike_inside_parking` and `bike_behind_parking`, and `to_additive`
  detects which one a section uses and reports it back.
- **Sides are split by travel direction**, not by the width midpoint. The
  specification defines left-oriented lanes as running toward the start point
  (`reverse`) and right-oriented toward the end point (`forward`). Splitting
  geometrically instead swaps the sides of any asymmetric street — one lane one
  way and two the other comes back reversed.

## Known limitations and deviations

Stated plainly, because a conversion that quietly loses data is worse than one
that refuses:

- **`Left_Transit_Lane` alias.** `Additive.md` gives the left transit columns
  the shapefile aliases `RTran_Ln` / `RTran_Meta`, which collide with the right
  side's. This emits `LTran_Ln` / `LTran_Meta` and says so in the conversion
  report.
- **A side path has no additive column.** `path` slices are stored in
  `Off_Street_Width`, which is not per-side, so two paths sum into one column
  and come back as one. Width is preserved, position is not, and the report
  says so. This is the one template (`rural_shoulder`) that does not round-trip
  slice-for-slice.
- **Centre-running transit cannot be expressed.** `Center_Lane_Meta` is
  enumerated `median; turn_lane; boulevard; barrier; median_turn_lane`, so a
  centre transitway or shared space has no valid value. The slice type is
  written into that field instead — recoverable, and flagged as outside the
  enumeration.
- **`median_turn_lane` is one slice here, two in the sample data.** The sample
  generator pre-splits segment 38's centre into `turn_lane 3.06 | median 0.34`.
  This keeps it as a single `turn_lane` carrying
  `meta.remainder_allocation = "median"`, which is what the Slice Types table
  prescribes. Reading the pre-split form folds both back into one
  `Center_Lane`, so no width is lost either way.
- **`auto_parking` is normalised to `parking`.** The sample data uses
  `auto_parking` 26 times; the specification tables say `parking`. Aliases are
  accepted on read and normalised on write.
- **The default widths are illustrative.** They are plausible values drawn
  from widths common in practice, *not* figures adopted from any standard.
  Every jurisdiction has its own design criteria — copy
  `shared_row_parametric/templates.json`, edit the numbers, and pass
  `--template-file`. Nothing in the code hard-codes a width.

## Library use

```python
from shared_row_parametric import templates, metrics, operators

result = templates.get("main_street").fit(22.0, sharedstreetid="abc123")
print(result.report.summary())

after, report = operators.road_diet(result.section, keep_lanes=1, protected=True)
print(metrics.compare(result.section, after).table())

feature = after.to_slice_feature()          # Slice GeoJSON
```

Editing a template in place, rather than writing a new library file:

```python
wider = (templates.get("urban_arterial")
         .with_spec("left_bike", min_width=2.1, preferred_width=2.4)
         .with_spec("right_bike", min_width=2.1, preferred_width=2.4))
```

## Tests

```
cd tests && python3 -m unittest discover -s . -p 'test_*.py'
```

107 tests, no dependencies. They cover the allocator's bounds and symmetry,
round-trips against the repository's real sample data, width preservation
across every operator, the validator, both renderers and every CLI subcommand.
The sample-data tests skip cleanly if `specification/Samples` is absent.

## Licence

Apache 2.0, matching the software licence of the parent repository.
