"""Tests for the width allocation solver."""

import unittest

import support  # noqa: F401  (sets sys.path)

from shared_row_parametric.fit import SliceSpec, fit


def spec(stype, lo, pref, hi, **kw):
    return SliceSpec(stype, lo, pref, hi, **kw)


BASIC = [
    spec("sidewalk", 1.5, 2.4, 4.0, priority=10, required=True, flex=2.0,
         role="left_sidewalk", pair="sidewalk"),
    spec("parking", 2.1, 2.45, 2.6, priority=90, flex=0.5,
         role="left_parking", pair="parking"),
    spec("drive_lane", 2.7, 3.3, 3.6, priority=40, required=True, flex=0.6,
         role="left_drive", pair="drive", direction="reverse"),
    spec("drive_lane", 2.7, 3.3, 3.6, priority=40, required=True, flex=0.6,
         role="right_drive", pair="drive", direction="forward"),
    spec("parking", 2.1, 2.45, 2.6, priority=90, flex=0.5,
         role="right_parking", pair="parking"),
    spec("sidewalk", 1.5, 2.4, 4.0, priority=10, required=True, flex=2.0,
         role="right_sidewalk", pair="sidewalk"),
]
PREFERRED = sum(s.preferred_width for s in BASIC)   # 16.3
MAXIMUM = sum(s.max_width for s in BASIC)          # 20.4
MINIMUM_REQUIRED = sum(s.min_width for s in BASIC if s.required)  # 8.4


class TestFitBasics(unittest.TestCase):
    def test_no_target_uses_preferred(self):
        result = fit(BASIC, None)
        self.assertAlmostEqual(result.section.total_width, PREFERRED, places=2)
        self.assertEqual(result.report.status, "exact")

    def test_exact_target_is_exact(self):
        result = fit(BASIC, PREFERRED)
        self.assertEqual(result.report.status, "exact")
        self.assertEqual(result.report.dropped, [])

    def test_hits_target_width_across_a_wide_range(self):
        for target in [9.0, 11.5, 13.0, 14.75, 16.3, 18.0, 20.0, MAXIMUM]:
            with self.subTest(target=target):
                result = fit(BASIC, target)
                self.assertTrue(result.report.feasible)
                self.assertAlmostEqual(result.section.total_width, target, places=2)

    def test_never_goes_below_minimum_widths(self):
        result = fit(BASIC, 9.0)
        for s in result.section.slices:
            matching = [b for b in BASIC if b.type == s.type]
            self.assertGreaterEqual(
                s.width + 1e-6, min(b.min_width for b in matching),
                "%s fell below its minimum" % s.type)

    def test_never_exceeds_maximum_widths(self):
        result = fit(BASIC, MAXIMUM)
        for s in result.section.slices:
            matching = [b for b in BASIC if b.type == s.type]
            self.assertLessEqual(
                s.width - 1e-6, max(b.max_width for b in matching),
                "%s exceeded its maximum" % s.type)

    def test_required_slices_are_never_dropped(self):
        result = fit(BASIC, 8.4)
        kinds = [s.type for s in result.section.slices]
        self.assertEqual(kinds.count("sidewalk"), 2)
        self.assertEqual(kinds.count("drive_lane"), 2)

    def test_drops_most_expendable_first(self):
        result = fit(BASIC, 11.0)
        self.assertIn("parking", " ".join(result.report.dropped))
        self.assertNotIn("sidewalk", " ".join(result.report.dropped))

    def test_infeasible_below_required_minimums(self):
        result = fit(BASIC, 4.0)
        self.assertFalse(result.report.feasible)
        self.assertEqual(result.report.status, "infeasible")
        # It still reports the narrowest achievable section rather than lying.
        self.assertGreater(result.section.total_width, 4.0)

    def test_paired_slices_drop_together(self):
        # Regression: an earlier version dropped the left bike lane while
        # keeping the right one, producing a lopsided street.
        result = fit(BASIC, 11.0)
        kinds = [s.type for s in result.section.slices]
        self.assertIn(kinds.count("parking"), (0, 2),
                      "parking must be dropped on both sides or neither")

    def test_result_is_left_right_symmetric(self):
        for target in [9.0, 11.0, 13.0, 16.3, 20.0]:
            with self.subTest(target=target):
                widths = [s.width for s in fit(BASIC, target).section.slices]
                self.assertEqual(
                    [round(w, 2) for w in widths],
                    [round(w, 2) for w in reversed(widths)],
                    "asymmetric allocation at %.2f m" % target)

    def test_filler_absorbs_width_nothing_else_can_take(self):
        result = fit(BASIC, 30.0, filler="planting_strip")
        self.assertAlmostEqual(result.section.total_width, 30.0, places=2)
        self.assertTrue(any(s.type == "planting_strip"
                            for s in result.section.slices))

    def test_residual_reported_when_no_filler(self):
        # Beyond the sum of every maximum width there is nothing legal left
        # to grow into, so the shortfall is reported rather than hidden.
        result = fit(BASIC, MAXIMUM + 4.0)
        self.assertGreater(result.report.residual, 0)
        self.assertTrue(any("unallocated" in n for n in result.report.notes))

    def test_allow_drop_false_reports_infeasible(self):
        result = fit(BASIC, 9.0, allow_drop=False)
        self.assertEqual(result.report.status, "infeasible")
        self.assertEqual(result.report.dropped, [])

    def test_zero_flex_pins_a_width(self):
        pinned = [
            spec("median", 2.0, 3.0, 4.0, flex=0.0, role="median"),
            spec("drive_lane", 2.7, 3.3, 3.6, flex=1.0, role="drive"),
        ]
        result = fit(pinned, 5.7)
        widths = {s.type: s.width for s in result.section.slices}
        self.assertAlmostEqual(widths["median"], 3.0, places=2)

    def test_rejects_bad_bounds(self):
        with self.assertRaises(ValueError):
            SliceSpec("drive_lane", 3.0, 3.0, 2.0)
        with self.assertRaises(ValueError):
            SliceSpec("drive_lane", -1.0, 3.0, 4.0)
        with self.assertRaises(ValueError):
            fit(BASIC, -5.0)
        with self.assertRaises(ValueError):
            fit([], 10.0)

    def test_preferred_is_clamped_into_range(self):
        s = SliceSpec("drive_lane", 3.0, 1.0, 3.6)
        self.assertAlmostEqual(s.preferred_width, 3.0)

    def test_spec_from_dict_shorthand(self):
        s = SliceSpec.from_dict({"type": "median", "width": 2.5})
        self.assertEqual((s.min_width, s.preferred_width, s.max_width),
                         (2.5, 2.5, 2.5))


if __name__ == "__main__":
    unittest.main()
