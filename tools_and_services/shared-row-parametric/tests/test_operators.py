"""Tests for reallocation operators and allocation metrics."""

import unittest

import support

from shared_row_parametric import metrics as M
from shared_row_parametric import operators as O
from shared_row_parametric import templates as T
from shared_row_parametric.model import CrossSection, Slice

ARTERIAL = T.get("urban_arterial").fit(30.0)


class TestWidthPreservation(unittest.TestCase):
    """The property lines do not move, so the total must not either."""

    def setUp(self):
        self.section = ARTERIAL.section

    def test_transfer_preserves_total(self):
        before = self.section.total_width
        moved = O.transfer(self.section, 4, 0, 1.0)
        self.assertAlmostEqual(moved.total_width, before, places=2)

    def test_transfer_rejects_more_than_available(self):
        with self.assertRaises(ValueError):
            O.transfer(self.section, 3, 0, 99.0)

    def test_transfer_out_of_range(self):
        with self.assertRaises(IndexError):
            O.transfer(self.section, 0, 99, 1.0)

    def test_negative_transfer_reverses_direction(self):
        forward = O.transfer(self.section, 4, 0, 0.5)
        backward = O.transfer(self.section, 0, 4, -0.5)
        self.assertEqual([s.width for s in forward.slices],
                         [s.width for s in backward.slices])

    def test_road_diet_preserves_total(self):
        for protected in (False, True):
            for keep in (1, 2):
                with self.subTest(protected=protected, keep=keep):
                    after, report = O.road_diet(
                        self.section, keep_lanes=keep, protected=protected)
                    self.assertAlmostEqual(
                        after.total_width, self.section.total_width, places=2)
                    self.assertTrue(report["width_preserved"])

    def test_road_diet_removes_lanes_from_the_inside(self):
        after, _ = O.road_diet(self.section, keep_lanes=1)
        lanes = [s for s in after.slices if s.type == "drive_lane"]
        self.assertEqual(len(lanes), 2)

    def test_road_diet_on_a_single_lane_street_is_a_no_op(self):
        section = T.get("local_residential").fit(16.0).section
        after, report = O.road_diet(section, keep_lanes=1)
        self.assertEqual(after.slices, section.slices)
        self.assertIn("note", report)

    def test_road_diet_does_not_stack_two_buffers(self):
        # Regression: the diet used to insert a second buffer beside the
        # existing one instead of widening it.
        after, _ = O.road_diet(self.section, keep_lanes=1, buffer_width=1.0,
                               protected=True)
        for i in range(len(after.slices) - 1):
            self.assertFalse(
                after.slices[i].type == "buffer"
                and after.slices[i + 1].type == "buffer",
                "adjacent duplicate buffers")

    def test_road_diet_shifts_share_away_from_cars(self):
        after, _ = O.road_diet(self.section, keep_lanes=1)
        comparison = M.compare(self.section, after)
        self.assertLess(comparison.after.auto_share,
                        comparison.before.auto_share)
        self.assertTrue(comparison.to_dict()["width_preserved"])

    def test_set_travel_lanes_reports_freed_width(self):
        after, freed = O.set_travel_lanes(self.section, 1)
        self.assertGreater(freed, 0)
        self.assertAlmostEqual(
            after.total_width + freed, self.section.total_width, places=2)

    def test_set_travel_lanes_can_give_width_away(self):
        after, freed = O.set_travel_lanes(self.section, 1, give_to="sidewalk")
        self.assertEqual(freed, 0.0)
        self.assertAlmostEqual(after.total_width, self.section.total_width,
                               places=2)

    def test_set_travel_lanes_rejects_negative(self):
        with self.assertRaises(ValueError):
            O.set_travel_lanes(self.section, -1)

    def test_widen_takes_from_traffic(self):
        after, report = O.widen(self.section, "sidewalk", 4.0)
        self.assertAlmostEqual(after.total_width, self.section.total_width,
                               places=2)
        for s in after.slices:
            if s.type == "sidewalk":
                self.assertAlmostEqual(s.width, 4.0, places=2)
        self.assertGreater(report["moved_m"], 0)

    def test_scale_to_hits_the_target(self):
        for target in (12.0, 24.0, 40.0):
            with self.subTest(target=target):
                self.assertAlmostEqual(
                    O.scale_to(self.section, target).total_width, target,
                    places=2)

    def test_scale_to_rejects_empty(self):
        with self.assertRaises(ValueError):
            O.scale_to(CrossSection(slices=[]), 10.0)

    def test_remove_and_insert_round_trip(self):
        removed = O.remove(self.section, 0, give_to=1)
        self.assertAlmostEqual(removed.total_width, self.section.total_width,
                               places=2)
        grown = O.insert(self.section, Slice("parklet", 2.0), 1, take_from=5)
        self.assertAlmostEqual(grown.total_width, self.section.total_width,
                               places=2)

    def test_coalesce_merges_only_compatible_neighbours(self):
        section = CrossSection(slices=[
            Slice("sidewalk", 1.0), Slice("sidewalk", 1.4),
            Slice("drive_lane", 3.0, direction="forward"),
            Slice("drive_lane", 3.0, direction="reverse"),
        ])
        merged = O.coalesce(section)
        self.assertEqual(len(merged.slices), 3)
        self.assertAlmostEqual(merged.total_width, section.total_width, places=2)


class TestMetrics(unittest.TestCase):
    def setUp(self):
        self.section = ARTERIAL.section

    def test_shares_sum_to_one(self):
        shares = M.allocation(self.section).shares
        self.assertAlmostEqual(sum(shares.values()), 1.0, places=3)

    def test_widths_sum_to_total(self):
        allocation = M.allocation(self.section)
        self.assertAlmostEqual(sum(allocation.by_mode.values()),
                               allocation.total_width, places=2)
        self.assertAlmostEqual(sum(allocation.by_type.values()),
                               allocation.total_width, places=2)

    def test_areas_need_a_length(self):
        self.assertIsNone(M.allocation(self.section).areas_m2)
        areas = M.allocation(self.section, length_m=100.0).areas_m2
        self.assertAlmostEqual(sum(areas.values()),
                               self.section.total_width * 100.0, places=0)

    def test_geodesic_length_from_geometry(self):
        section = CrossSection(
            slices=[Slice("drive_lane", 3.0)],
            geometry={"type": "LineString",
                      "coordinates": [[-122.42, 37.79], [-122.42, 37.80]]},
        )
        # One hundredth of a degree of latitude is about 1.11 km.
        self.assertAlmostEqual(section.length_m, 1112.0, delta=5.0)

    def test_network_summary_is_length_weighted(self):
        short = CrossSection(
            slices=[Slice("drive_lane", 10.0)],
            geometry={"type": "LineString",
                      "coordinates": [[0.0, 0.0], [0.0, 0.0001]]})
        long = CrossSection(
            slices=[Slice("sidewalk", 10.0)],
            geometry={"type": "LineString",
                      "coordinates": [[0.0, 0.0], [0.0, 0.01]]})
        summary = M.network_summary([short, long])
        self.assertEqual(summary["segments"], 2)
        # The long pedestrian segment must dominate the short traffic one.
        self.assertGreater(summary["share_by_mode"]["pedestrian"],
                           summary["share_by_mode"]["automobile"])

    def test_network_summary_flags_missing_geometry(self):
        summary = M.network_summary([self.section])
        self.assertEqual(summary["segments_without_geometry"], 1)

    def test_empty_network(self):
        self.assertEqual(M.network_summary([])["segments"], 0)

    def test_tables_render(self):
        self.assertIn("total", M.allocation(self.section, length_m=50).table())
        after, _ = O.road_diet(self.section, keep_lanes=1)
        self.assertIn("auto share", M.compare(self.section, after).table())


if __name__ == "__main__":
    unittest.main()
