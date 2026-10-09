"""Step 6.7a, stage S0: levels of a cell and the height check against the angled envelope plane."""

import copy

import pytest
from conftest import load_fixture

from spaceplan.modules.stacking.lib.height_check import (
    EXCEEDS_HEIGHT,
    PLANE_GOVERNS,
    WITHIN_PLANE,
    best_status,
    check_height,
    roof_profile,
    worst_status,
)
from spaceplan.modules.stacking.lib.levels import build_levels, cell_gross_by_floor
from spaceplan.modules.stacking.lib.stacking_catalog import load_stacking_catalog
from spaceplan.modules.stacking.lib.vertical_rules import HeightEnvelope, load_vertical_ruleset

SUBJECT = "interior_50x100_empty_nest_anglo"
ENV = HeightEnvelope(start_ft=24.0, overall_max_ft=30.0, angle_deg=45, front_trigger_ft=27, status="provisional",
                     sources=())
FLAT = {"roof_id": "flat", "kind": "flat", "parapet_ft": 2.0}
PITCH = {"roof_id": "p", "kind": "pitched", "pitch_rise_per_run": 1 / 3}


@pytest.fixture(scope="module")
def vrs():
    return load_vertical_ruleset()


@pytest.fixture(scope="module")
def scat():
    return load_stacking_catalog()


@pytest.fixture(scope="module")
def cells():
    return load_fixture("area_matrix", SUBJECT)["cells"]


def _levels(*areas, ground_ff=1.0, f2f=10.0):
    return [{"level": k, "finish_floor_ft": ground_ff + k * f2f, "gross_sqft": a} for k, a in enumerate(areas)]


def test_levels_of_one_and_two_floor_cells(cells, scat, vrs):
    one = next(c for c in cells if c["floors"] == 1)
    two = next(c for c in cells if c["floors"] == 2)
    levels, warnings = build_levels(one, scat.levels, vrs, 60.0, scat.stair_tolerance_sqft)
    assert [lv["kind"] for lv in levels] == ["ground"] and warnings == []
    assert levels[0]["stair_sqft"] == 0.0 and levels[0]["counts_in_io"]
    levels, warnings = build_levels(two, scat.levels, vrs, 60.0, scat.stair_tolerance_sqft)
    assert [lv["kind"] for lv in levels] == ["ground", "upper"] and warnings == []
    assert levels[1]["finish_floor_ft"] - levels[0]["finish_floor_ft"] == scat.levels["floor_to_floor_ft"]
    assert levels[1]["spaces"] == two["split"]["upper_spaces"] and not levels[1]["counts_in_io"]
    assert sum(lv["gross_sqft"] for lv in levels) == pytest.approx(sum(cell_gross_by_floor(two)))
    assert all(lv["stair_sqft"] == two["split"]["stair_sqft_per_floor"] for lv in levels)


def test_levels_warn_on_stair_mismatch_and_high_ground_floor(cells, scat, vrs):
    two = copy.deepcopy(next(c for c in cells if c["floors"] == 2))
    _, warnings = build_levels(two, scat.levels, vrs, 90.0, scat.stair_tolerance_sqft)
    assert any("stair area" in w for w in warnings)
    _, warnings = build_levels(two, {**scat.levels, "ground_floor_above_grade_ft": 3.0}, vrs, 60.0,
                               scat.stair_tolerance_sqft)
    assert any("first-story" in w for w in warnings)


def test_roof_profiles():
    assert roof_profile(FLAT, 20.0, 30.0, True) == {"side_wall": "parapet", "side_edge_ft": 22.0, "top_ft": 22.0,
                                                    "run_to_top_ft": 0.0}
    eave = roof_profile(PITCH, 20.0, 30.0, True)
    assert eave["side_wall"] == "eave" and eave["side_edge_ft"] == 20.0 and eave["top_ft"] == pytest.approx(25.0)
    gable = roof_profile(PITCH, 20.0, 30.0, False)
    assert gable["side_wall"] == "gable" and gable["side_edge_ft"] == pytest.approx(25.0)


def test_two_floors_flat_roof_stay_within_the_plane(vrs):
    h = check_height(_levels(1500.0, 800.0), 40.0, FLAT, 9.0, ENV, vrs, 0.0)
    assert (h["status"], h["plate_ft"], h["top_ft"], h["side_inset_ft"]) == (WITHIN_PLANE, 20.0, 22.0, 0.0)
    assert not h["front_plane_required"] and h["headroom_ft"] == 8.0


def test_gable_on_the_side_needs_an_inset(vrs):
    # ground 40 x 50: the short side is the width, so a narrower-than-deep house has its eaves on the sides;
    # a wide shallow one (60 x 25) has the gables on the sides and the ridge must step back from the plane
    h = check_height(_levels(1500.0, 1500.0), 60.0, PITCH, 9.0, ENV, vrs, 0.0)
    assert h["side_wall"] == "gable" and h["status"] == PLANE_GOVERNS
    assert h["side_inset_ft"] == pytest.approx(h["top_ft"] - 24.0)
    eave = check_height(_levels(2000.0, 2000.0), 40.0, PITCH, 9.0, ENV, vrs, 0.0)
    assert eave["side_wall"] == "eave" and eave["status"] == WITHIN_PLANE  # 4:12 is flatter than the 45 deg plane


def test_exceeds_height_and_front_plane(vrs):
    h = check_height(_levels(1500.0, 1500.0, 1500.0), 40.0, FLAT, 9.0, ENV, vrs, 0.0)
    assert h["status"] == EXCEEDS_HEIGHT and h["front_plane_required"] and h["headroom_ft"] < 0
    tall = check_height(_levels(2700.0, 2700.0), 45.0, PITCH, 9.0, ENV, vrs, 0.0)  # 45 x 60, ridge 27.5 ft
    assert tall["top_ft"] == pytest.approx(27.5) and tall["front_plane_required"]
    assert tall["status"] == WITHIN_PLANE


def test_grade_differential_raises_the_overall_limit(vrs):
    h = check_height(_levels(2000.0), 40.0, FLAT, 9.0, ENV, vrs, 0.1)
    assert h["grade_differential_ft"] == pytest.approx(5.0)
    assert h["overall_limit_ft"] == pytest.approx(35.0) and h["status"] == WITHIN_PLANE


def test_no_plane_beyond_150_ft(vrs):
    env = HeightEnvelope(24.0, 30.0, None, 27, "provisional", ())
    h = check_height(_levels(1500.0, 1500.0), 60.0, PITCH, 9.0, env, vrs, 0.0)
    assert h["side_inset_ft"] == 0.0 and h["status"] == WITHIN_PLANE


def test_status_order():
    assert worst_status([WITHIN_PLANE, PLANE_GOVERNS]) == PLANE_GOVERNS
    assert worst_status([WITHIN_PLANE, EXCEEDS_HEIGHT, PLANE_GOVERNS]) == EXCEEDS_HEIGHT
    assert best_status([EXCEEDS_HEIGHT, PLANE_GOVERNS]) == PLANE_GOVERNS
