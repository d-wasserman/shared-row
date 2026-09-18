"""Round-trip tests, including against the specification's own sample data."""

import unittest

import support
from support import (ADDITIVE_SAMPLE, CROSSWALK_SAMPLE, SLICE_SAMPLE,
                     have_samples, load_json)

from shared_row_parametric import additive as A
from shared_row_parametric import crosswalk as X
from shared_row_parametric import io as I
from shared_row_parametric import templates as T
from shared_row_parametric.model import CrossSection, Slice

NEEDS_SAMPLES = unittest.skipUnless(
    have_samples(), "specification/Samples not found")


def width_of(record):
    """Total width implied by an additive record's width columns."""
    return round(sum(
        v for k, v in record.items()
        if isinstance(v, float) and k in A.ALIASES and "Crosswalk" not in k
    ), 2)


class TestTemplateRoundTrip(unittest.TestCase):
    def test_every_template_survives_additive(self):
        for name in T.library():
            with self.subTest(template=name):
                section = T.get(name).fit(None).section
                record, report = A.to_additive(section)
                back = A.from_additive(
                    record,
                    arrangement=report.arrangement or A.DEFAULT_ARRANGEMENT)
                self.assertAlmostEqual(
                    back.total_width, section.total_width, places=2,
                    msg="width changed for %s" % name)

    def test_slice_sequence_preserved_except_for_known_gap(self):
        # rural_shoulder has a path on each side and the additive schema has
        # one Off_Street_Width column, so the two paths sum into one.
        lossy = {"rural_shoulder"}
        for name in T.library():
            with self.subTest(template=name):
                section = T.get(name).fit(None).section
                record, report = A.to_additive(section)
                back = A.from_additive(
                    record,
                    arrangement=report.arrangement or A.DEFAULT_ARRANGEMENT)
                before = [(s.type, s.width) for s in section.slices]
                after = [(s.type, s.width) for s in back.slices]
                if name in lossy:
                    self.assertNotEqual(before, after)
                    self.assertTrue(any("Off_Street_Width" in n
                                        for n in report.notes))
                else:
                    self.assertEqual(before, after)

    def test_crosswalk_round_trip_is_exact(self):
        for name in T.library():
            with self.subTest(template=name):
                section = T.get(name).fit(21.0).section
                self.assertEqual(X.from_rows(X.to_rows(section)).slices,
                                 section.slices)

    def test_slice_geojson_round_trip_is_exact(self):
        section = T.get("urban_arterial").fit(30.0, sharedstreetid="abc").section
        for stringify in (True, False):
            with self.subTest(stringify=stringify):
                feature = section.to_slice_feature(stringify_slices=stringify)
                back = CrossSection.from_slice_feature(feature)
                self.assertEqual(back.slices, section.slices)
                self.assertEqual(back.sharedstreetid, "abc")

    def test_kerb_arrangement_is_detected_and_reversible(self):
        section = T.get("protected_bikeway_street").fit(24.0).section
        record, report = A.to_additive(section)
        self.assertEqual(report.arrangement, "bike_behind_parking")
        back = A.from_additive(record, arrangement=report.arrangement)
        self.assertEqual([s.type for s in back.slices],
                         [s.type for s in section.slices])

    def test_unknown_arrangement_rejected(self):
        with self.assertRaises(ValueError):
            A.from_additive({}, arrangement="sideways")


@NEEDS_SAMPLES
class TestAgainstSampleData(unittest.TestCase):
    """The repository's 38 San Francisco segments."""

    @classmethod
    def setUpClass(cls):
        cls.additive = load_json(ADDITIVE_SAMPLE)

    def test_additive_sample_round_trips_field_for_field(self):
        mismatched = []
        for feature in self.additive["features"]:
            section = A.from_additive_feature(feature, semantic_furniture=False)
            record, _ = A.to_additive(section)
            original = feature["properties"]
            for key, new in record.items():
                if key not in A.ALIASES or key == "SharedStreetID":
                    continue
                old = original.get(key)
                if isinstance(new, float):
                    if abs(float(old or 0.0) - new) > 0.005:
                        mismatched.append((original.get("OBJECTID"), key, old, new))
                elif (old or None) != (new or None):
                    mismatched.append((original.get("OBJECTID"), key, old, new))
        self.assertEqual(mismatched, [], "additive fields changed on round trip")

    def test_crosswalk_sample_preserves_width_into_additive(self):
        sections, rep = I.load(CROSSWALK_SAMPLE)
        self.assertEqual(rep, I.CROSSWALK)
        self.assertEqual(len(sections), 38)
        for section in sections:
            record, _ = A.to_additive(section)
            self.assertAlmostEqual(
                width_of(record), section.total_width, places=2,
                msg="width lost for %s" % section.sharedstreetid)

    def test_median_turn_lane_folds_into_one_centre_column(self):
        # Segment 38 stores a median_turn_lane as a turn lane pocket plus the
        # median remainder in two adjacent slices. Both belong to Center_Lane.
        sections, _ = I.load(CROSSWALK_SAMPLE)
        split = [s for s in sections
                 if any(x.type == "median" and x.width == 0.34 for x in s.slices)]
        self.assertTrue(split, "expected the pre-split centre segment")
        record, report = A.to_additive(split[0])
        self.assertAlmostEqual(record["Center_Lane"], 3.4, places=2)
        self.assertEqual(record["Center_Lane_Meta"], "median_turn_lane")

    def test_slice_sample_loads(self):
        sections, rep = I.load(SLICE_SAMPLE)
        self.assertEqual(rep, I.SLICE)
        self.assertEqual(len(sections), 38)
        self.assertEqual(sum(len(s.slices) for s in sections), 315)

    def test_sample_aliases_are_normalised(self):
        sections, _ = I.load(CROSSWALK_SAMPLE)
        types = {s.type for section in sections for s in section.slices}
        self.assertIn("parking", types)
        self.assertNotIn("auto_parking", types,
                         "auto_parking should normalise to parking")

    def test_representation_autodetect(self):
        for path, expected in ((ADDITIVE_SAMPLE, I.ADDITIVE),
                               (SLICE_SAMPLE, I.SLICE),
                               (CROSSWALK_SAMPLE, I.CROSSWALK)):
            with self.subTest(path=path):
                self.assertEqual(I.detect(load_json(path)), expected)


class TestSideSplitting(unittest.TestCase):
    """Regression tests for how a section is divided into left and right."""

    def test_asymmetric_lane_counts_do_not_swap_sides(self):
        # One lane one way, two the other. Splitting at the width midpoint
        # used to move a forward lane onto the left side.
        section = CrossSection(slices=[
            Slice("sidewalk", 2.0, height=15.24, meta={"zone": "through"}),
            Slice("drive_lane", 3.1, direction="reverse"),
            Slice("drive_lane", 3.1, direction="forward"),
            Slice("drive_lane", 3.1, direction="forward"),
            Slice("sidewalk", 2.0, height=15.24, meta={"zone": "through"}),
        ])
        record, _ = A.to_additive(section)
        self.assertAlmostEqual(record["Left_Through_Lane_1"], 3.1, places=2)
        self.assertAlmostEqual(record["Left_Through_Lane_2"], 0.0, places=2)
        self.assertAlmostEqual(record["Right_Through_Lane_1"], 3.1, places=2)
        self.assertAlmostEqual(record["Right_Through_Lane_2"], 3.1, places=2)

    def test_lane_one_is_the_kerb_lane(self):
        # Verified against every multi-lane sample segment whose lane widths
        # differ: Through_Lane_1 is the outermost lane on each side.
        section = A.from_additive({
            "Left_Sidewalk_Through_Zone": 2.0,
            "Left_Through_Lane_1": 3.5,
            "Left_Through_Lane_2": 3.0,
            "Right_Through_Lane_1": 3.5,
            "Right_Through_Lane_2": 3.0,
            "Right_Sidewalk_Through_Zone": 2.0,
        })
        widths = [s.width for s in section.slices]
        self.assertEqual(widths, [2.0, 3.5, 3.0, 3.0, 3.5, 2.0])

    def test_centre_running_transit_is_found(self):
        section = T.get("transit_boulevard").fit(None).section
        index = section.center_index()
        self.assertIsNotNone(index)
        self.assertEqual(section.slices[index].type, "transit")

    def test_kerbside_bus_lane_is_not_treated_as_centre(self):
        section = CrossSection(slices=[
            Slice("sidewalk", 2.0, meta={"zone": "through"}),
            Slice("bus_lane", 3.2, direction="reverse"),
            Slice("drive_lane", 3.2, direction="reverse"),
            Slice("drive_lane", 3.2, direction="forward"),
            Slice("drive_lane", 3.2, direction="forward"),
            Slice("sidewalk", 2.0, meta={"zone": "through"}),
        ])
        self.assertIsNone(section.center_index())


if __name__ == "__main__":
    unittest.main()
