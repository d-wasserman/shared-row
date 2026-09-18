"""Shared test helpers: locate the specification's sample data."""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(HERE)
REPO = os.path.dirname(os.path.dirname(PROJECT))
SAMPLES = os.path.join(REPO, "specification", "Samples")

if PROJECT not in sys.path:
    sys.path.insert(0, PROJECT)

ADDITIVE_SAMPLE = os.path.join(SAMPLES, "Additive", "additive_test_sample.geojson")
SLICE_SAMPLE = os.path.join(SAMPLES, "Slice", "slice_spec_sample.geojson")
CROSSWALK_SAMPLE = os.path.join(
    SAMPLES, "Schema_Crosswalk", "srow_schema_crosswalk.geojson")


def have_samples():
    return all(os.path.exists(p) for p in
               (ADDITIVE_SAMPLE, SLICE_SAMPLE, CROSSWALK_SAMPLE))


def load_json(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)
