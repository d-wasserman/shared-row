"""Tests for validation, rendering, templates and the command line."""

import json
import os
import tempfile
import unittest
import xml.dom.minidom as minidom

import support
from support import ADDITIVE_SAMPLE, SLICE_SAMPLE, have_samples

from shared_row_parametric import cli
from shared_row_parametric import render as R
from shared_row_parametric import templates as T
from shared_row_parametric import validate as V
from shared_row_parametric import vocab
from shared_row_parametric.model import CrossSection, Slice

NEEDS_SAMPLES = unittest.skipUnless(
    have_samples(), "specification/Samples not found")


class TestVocabulary(unittest.TestCase):
    def test_slice_types_are_unique(self):
        self.assertEqual(len(vocab.SLICE_TYPES), len(set(vocab.SLICE_TYPES)))

    def test_every_type_has_exactly_one_mode(self):
        seen = {}
        for mode, types in vocab.MODE_GROUPS.items():
            for t in types:
                self.assertNotIn(t, seen,
                                 "%s is in both %s and %s" % (t, seen.get(t), mode))
                seen[t] = mode
        for t in vocab.SLICE_TYPES:
            self.assertIn(t, seen, "%s has no mode group" % t)

    def test_aliases_resolve_to_real_types(self):
        for alias, target in vocab.TYPE_ALIASES.items():
            self.assertIn(target, vocab.SLICE_TYPES,
                          "%s maps to unknown %s" % (alias, target))

    def test_normalise_is_idempotent(self):
        for t in vocab.SLICE_TYPES:
            self.assertEqual(vocab.normalize_type(t), t)


class TestTemplates(unittest.TestCase):
    def test_library_loads(self):
        self.assertGreater(len(T.library()), 3)

    def test_every_template_has_a_pedestrian_slice(self):
        walkable = ("sidewalk", "path")
        for name, tpl in T.library().items():
            with self.subTest(template=name):
                types = [s.type for s in tpl.specs]
                self.assertTrue(any(t in walkable for t in types),
                                "%s has nowhere to walk" % name)

    def test_every_template_fits_its_declared_range(self):
        for name, tpl in T.library().items():
            if not tpl.row_range:
                continue
            for width in tpl.row_range:
                with self.subTest(template=name, width=width):
                    result = tpl.fit(width)
                    self.assertTrue(
                        result.report.feasible,
                        "%s does not fit at %.1f m, its own declared bound"
                        % (name, width))
                    self.assertAlmostEqual(result.section.total_width, width,
                                           places=2)

    def test_template_slice_types_are_in_the_specification(self):
        for name, tpl in T.library().items():
            for s in tpl.specs:
                with self.subTest(template=name, type=s.type):
                    self.assertTrue(vocab.is_known_type(s.type))

    def test_mirroring_assigns_sides_and_directions(self):
        tpl = T.get("urban_arterial")
        roles = tpl.roles()
        self.assertTrue(roles[0].startswith("left_"))
        self.assertTrue(roles[-1].startswith("right_"))
        lanes = [s for s in tpl.specs if s.type == "drive_lane"]
        self.assertEqual({s.direction for s in lanes}, {"forward", "reverse"})

    def test_mirrored_pairs_share_a_pair_key(self):
        for name, tpl in T.library().items():
            with self.subTest(template=name):
                for spec in tpl.specs:
                    if spec.role and spec.role.startswith("left_"):
                        twin = spec.role.replace("left_", "right_", 1)
                        others = [s for s in tpl.specs if s.role == twin]
                        self.assertEqual(len(others), 1)
                        self.assertEqual(others[0].pair, spec.pair)

    def test_with_spec_edits_a_role(self):
        tpl = T.get("urban_arterial").with_spec("left_bike", min_width=2.4,
                                                preferred_width=2.4)
        spec = [s for s in tpl.specs if s.role == "left_bike"][0]
        self.assertAlmostEqual(spec.min_width, 2.4)
        # The shared library must not be mutated by an edit.
        self.assertAlmostEqual(
            [s for s in T.get("urban_arterial").specs
             if s.role == "left_bike"][0].min_width, 1.5)

    def test_with_spec_unknown_role(self):
        with self.assertRaises(KeyError):
            T.get("urban_arterial").with_spec("nope")

    def test_unknown_template(self):
        with self.assertRaises(KeyError):
            T.get("no_such_template")

    def test_suggest_matches_width(self):
        names = [t.name for t in T.suggest(12.0)]
        self.assertIn("local_residential", names)
        self.assertNotIn("transit_boulevard", names)

    def test_template_survives_a_json_round_trip(self):
        tpl = T.get("main_street")
        rebuilt = T.template_from_dict(tpl.to_dict())
        self.assertEqual(len(rebuilt.specs), len(tpl.specs))
        self.assertAlmostEqual(rebuilt.preferred_width, tpl.preferred_width,
                               places=2)

    def test_custom_library_file(self):
        payload = {"templates": [{
            "name": "tiny",
            "description": "one lane each way",
            "half": [{"type": "sidewalk", "width": 1.5, "required": True},
                     {"type": "drive_lane", "width": 3.0, "required": True}],
        }]}
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
            json.dump(payload, fh)
            path = fh.name
        try:
            tpl = T.get("tiny", path)
            self.assertAlmostEqual(tpl.preferred_width, 9.0, places=2)
        finally:
            os.unlink(path)

    def test_template_needs_half_or_slices(self):
        with self.assertRaises(ValueError):
            T.template_from_dict({"name": "broken"})


class TestValidation(unittest.TestCase):
    def test_a_generated_section_is_valid(self):
        for name in T.library():
            with self.subTest(template=name):
                section = T.get(name).fit(None, sharedstreetid="x").section
                self.assertTrue(V.validate_section(section),
                                V.validate_section(section).report())

    def test_bad_direction_is_an_error(self):
        section = CrossSection(slices=[Slice("drive_lane", 3.0, direction="sideways")],
                               sharedstreetid="x")
        result = V.validate_section(section)
        self.assertFalse(result)
        self.assertIn("bad-direction", [i.code for i in result.errors])

    def test_negative_width_is_an_error(self):
        section = CrossSection(slices=[Slice("drive_lane", -1.0)], sharedstreetid="x")
        self.assertIn("negative-width",
                      [i.code for i in V.validate_section(section).errors])

    def test_empty_section_is_an_error(self):
        self.assertFalse(V.validate_section(CrossSection(slices=[])))

    def test_unknown_type_is_only_a_warning(self):
        section = CrossSection(slices=[
            Slice("sidewalk", 2.0), Slice("hyperloop", 3.0), Slice("sidewalk", 2.0),
        ], sharedstreetid="x")
        result = V.validate_section(section)
        self.assertTrue(result, "the specification permits new slice types")
        self.assertIn("unknown-slice-type", [i.code for i in result.warnings])

    def test_missing_sharedstreetid_is_a_warning(self):
        section = CrossSection(slices=[Slice("sidewalk", 2.0)])
        self.assertIn("missing-sharedstreetid",
                      [i.code for i in V.validate_section(section).warnings])

    def test_traffic_at_the_edge_is_flagged(self):
        section = CrossSection(slices=[
            Slice("drive_lane", 3.0), Slice("sidewalk", 2.0)], sharedstreetid="x")
        self.assertIn("traffic-at-edge",
                      [i.code for i in V.validate_section(section).warnings])

    def test_distinct_sidewalk_zones_are_not_merge_candidates(self):
        section = CrossSection(slices=[
            Slice("sidewalk", 0.9, meta={"zone": "frontage"}),
            Slice("sidewalk", 2.4, meta={"zone": "through"}),
        ], sharedstreetid="x")
        self.assertNotIn("adjacent-duplicate",
                         [i.code for i in V.validate_section(section).issues])

    def test_additive_missing_required_field(self):
        result = V.validate_additive({"SharedStreetID": "a"})
        self.assertFalse(result)
        self.assertIn("missing-required-field", [i.code for i in result.errors])

    def test_additive_enum_warning(self):
        record = {"Center_Lane_Meta": "roundabout"}
        self.assertIn("meta-outside-enumeration",
                      [i.code for i in V.validate_additive(record).warnings])

    def test_crosswalk_duplicate_rowindex(self):
        rows = [{"rowindex": 0, "type": "sidewalk"},
                {"rowindex": 0, "type": "drive_lane"}]
        self.assertIn("duplicate-rowindex",
                      [i.code for i in V.validate_crosswalk_rows(rows).errors])

    def test_crosswalk_bad_meta_json(self):
        rows = [{"rowindex": 0, "type": "sidewalk", "meta": "{not json"}]
        self.assertIn("meta-not-json",
                      [i.code for i in V.validate_crosswalk_rows(rows).warnings])

    def test_result_serialises(self):
        payload = V.validate_section(CrossSection(slices=[])).to_dict()
        self.assertFalse(payload["valid"])
        self.assertGreater(payload["errors"], 0)


@NEEDS_SAMPLES
class TestSamplesValidate(unittest.TestCase):
    def test_sample_slice_file_has_no_errors(self):
        from shared_row_parametric import io as I
        sections, _ = I.load(SLICE_SAMPLE)
        result = V.validate_many(sections)
        self.assertTrue(result, result.report(min_level="error"))


class TestRendering(unittest.TestCase):
    def setUp(self):
        self.section = T.get("urban_arterial").fit(30.0).section

    def test_svg_is_well_formed_xml(self):
        svg = R.to_svg(self.section, title="test")
        minidom.parseString(svg)
        self.assertIn("right-of-way", svg)

    def test_svg_escapes_text(self):
        section = CrossSection(slices=[Slice("sidewalk", 2.0)])
        svg = R.to_svg(section, title='a<b&c"d')
        minidom.parseString(svg)
        self.assertNotIn("<b&c", svg)

    def test_svg_rejects_empty(self):
        with self.assertRaises(ValueError):
            R.to_svg(CrossSection(slices=[]))

    def test_ascii_lists_every_slice(self):
        text = R.to_ascii(self.section)
        for s in self.section.slices:
            self.assertIn(s.type, text)
        self.assertIn("total", text)

    def test_ascii_bar_and_arrows_align(self):
        lines = R.to_ascii(self.section).splitlines()
        self.assertLessEqual(len(lines[1]), len(lines[0]))

    def test_ascii_handles_empty(self):
        self.assertIn("zero-width", R.to_ascii(CrossSection(slices=[])))

    def test_legend(self):
        self.assertIn("pedestrian", R.legend())


class TestCli(unittest.TestCase):
    def test_templates_command(self):
        self.assertEqual(cli.main(["templates"]), 0)

    def test_templates_dump_one(self):
        self.assertEqual(cli.main(["templates", "main_street"]), 0)

    def test_fit_command(self):
        self.assertEqual(cli.main(["fit", "20"]), 0)

    def test_generate_to_file(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "s.geojson")
            self.assertEqual(
                cli.main(["generate", "main_street", "22", "--out", out]), 0)
            with open(out) as fh:
                payload = json.load(fh)
            self.assertEqual(len(payload["features"]), 1)
            self.assertIn("slices", payload["features"][0]["properties"])

    def test_generate_rejects_impossible_width(self):
        self.assertEqual(cli.main(["generate", "transit_boulevard", "6"]), 2)

    def test_generate_force_emits_anyway(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "s.geojson")
            self.assertEqual(cli.main(
                ["generate", "transit_boulevard", "6", "--force", "--out", out]), 0)

    def test_unknown_template_exits_nonzero(self):
        self.assertEqual(cli.main(["generate", "nope", "20"]), 2)

    def test_every_output_format(self):
        with tempfile.TemporaryDirectory() as d:
            for fmt in ("slice", "additive", "crosswalk", "svg", "ascii", "summary"):
                with self.subTest(format=fmt):
                    out = os.path.join(d, fmt)
                    self.assertEqual(cli.main(
                        ["generate", "main_street", "22",
                         "--format", fmt, "--out", out]), 0)
                    self.assertGreater(os.path.getsize(out), 0)

    @NEEDS_SAMPLES
    def test_roundtrip_through_the_cli(self):
        with tempfile.TemporaryDirectory() as d:
            cw = os.path.join(d, "cw.geojson")
            back = os.path.join(d, "back.geojson")
            self.assertEqual(cli.main(
                ["convert", ADDITIVE_SAMPLE, "--format", "crosswalk",
                 "--out", cw]), 0)
            self.assertEqual(cli.main(
                ["convert", cw, "--format", "additive", "--out", back]), 0)
            self.assertEqual(cli.main(["validate", ADDITIVE_SAMPLE]), 0)
            self.assertEqual(cli.main(["metrics", ADDITIVE_SAMPLE]), 0)
            self.assertEqual(cli.main(["metrics", ADDITIVE_SAMPLE, "--json"]), 0)

    @NEEDS_SAMPLES
    def test_diet_through_the_cli(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "diet.geojson")
            self.assertEqual(cli.main(
                ["diet", ADDITIVE_SAMPLE, "--keep-lanes", "1", "--protected",
                 "--coalesce", "--out", out]), 0)

    def test_missing_file_exits_nonzero(self):
        self.assertEqual(cli.main(["validate", "/nonexistent/x.geojson"]), 2)


if __name__ == "__main__":
    unittest.main()
