"""Space-quality indicators (step 6.7a S2.2a)."""

import json
from pathlib import Path

import pytest
from shapely.geometry import Polygon, box, mapping

from spaceplan.modules.design.lib import design_profile as dp
from spaceplan.modules.design.lib.design_registry import load_registry
from spaceplan.modules.stacking.lib.space_quality import (
    category,
    fits_rectangle,
    quality_report,
    space_metrics,
)
from spaceplan.modules.stacking.main.run_quality import run_quality
from spaceplan.pipeline.main.cli import main

FIXTURE = Path(__file__).parent / "fixtures" / "s21_quality_sample.json"


@pytest.fixture(scope="module")
def reg():
    return load_registry()


@pytest.fixture(scope="module")
def values(reg):
    return dp.effective_values(reg, None)


def _space(st, geom, ext=0.0):
    return {"space_id": st, "space_type": st, "polygon": mapping(geom), "exterior_ft": ext}


def test_fits_rectangle_both_orientations():
    assert fits_rectangle(box(0, 0, 10, 10), 9, 9)
    assert not fits_rectangle(box(0, 0, 10, 10), 11, 5)
    assert fits_rectangle(box(0, 0, 5, 12), 8, 5)
    ell = Polygon([(0, 0), (12, 0), (12, 4), (4, 4), (4, 12), (0, 12)])
    assert fits_rectangle(ell, 4, 12) and not fits_rectangle(ell, 6, 6)


def test_strip_bath_is_flagged(values):
    m = space_metrics(_space("bathroom", box(0, 0, 5, 11.5)), 1, values)
    assert m["aspect"] == pytest.approx(2.3)
    assert m["aspect_pref_ok"] is False and m["aspect_max_ok"] is False and m["max_side_ok"] is False
    assert m["furniture_fits"] is True and m["category"] == "M"
    ok = space_metrics(_space("bathroom", box(0, 0, 5, 8)), 1, values)
    assert ok["aspect_pref_ok"] and ok["aspect_max_ok"] and ok["furniture_fits"]


def test_bedroom_furniture_and_daylight(values):
    good = space_metrics(_space("bedroom", box(0, 0, 10, 14), ext=10.0), 1, values)
    assert good["furniture_fits"] is True and good["daylight_ok"] is True
    narrow = space_metrics(_space("bedroom", box(0, 0, 9, 16), ext=9.0), 1, values)
    assert narrow["furniture_fits"] is False  # queen + 30 in at both sides needs 10 ft
    deep = space_metrics(_space("bedroom", box(0, 0, 8, 20), ext=8.0), 1, values)
    assert deep["furniture_fits"] is False and deep["daylight_ok"] is False and deep["min_side_ok"] is False


def test_upper_floor_category_override(values):
    assert category(values, "bathroom", 0) == "P" and category(values, "bathroom", 1) == "M"
    assert category(values, "bedroom", 1) == "N"


def test_report_on_pilot_sample(values):
    report = quality_report([json.loads(FIXTURE.read_text())], values)
    o = report["overall"]
    assert (o["cells_with_s21"], o["cells_spaced"]) == (2, 1)
    assert o["spaces"] == len(report["cells"][0]["spaces"]) > 10
    types = {r["space_type"] for r in report["by_type"]}
    assert {"bedroom", "kitchen", "hall"} & types


def test_profile_changes_the_yardstick(reg):
    sample = [json.loads(FIXTURE.read_text())]
    base = quality_report(sample, dp.effective_values(reg, None))["overall"]
    loose = dp.new_profile(reg, "loose")
    loose = dp.apply(reg, loose, [{"id": f"space.{t}.aspect_max", "value": 3.0} for t in
                                  ("bedroom", "bathroom", "kitchen", "dining_room", "foyer", "pantry", "laundry",
                                   "primary_bath", "breakfast_nook", "study", "flex_room", "mudroom", "primary_suite",
                                   "walk_in_closet", "living_room", "family_room", "work_kitchen", "half_bath")],
                     "test", "2026-10-11")
    after = quality_report(sample, dp.effective_values(reg, loose))["overall"]
    assert after["pct_over_max"] <= base["pct_over_max"]


def test_run_quality_writes_the_tables(tmp_path):
    report = run_quality([str(FIXTURE)], None, str(tmp_path))
    assert report["profile_id"] == "baseline"
    for name in ("quality_summary.json", "quality_by_type.csv", "quality_spaces.csv", "quality.md"):
        assert (tmp_path / name).is_file()
    assert main(["quality", str(FIXTURE)]) == 0
