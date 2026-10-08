"""Reference values from spaceplan v1.1 (sections 4 and 10) and the approved analysis."""

import pytest

from conftest import load_brief
from spaceplan.main.run_capacity import run_capacity


def cap(pkg):
    return pkg["capacity"]


def level(pkg, name):
    return next(lv for lv in cap(pkg)["feasibility"]["levels"] if lv["level"] == name)


def test_interior_lot(packages):
    pkg = packages["interior_50x100"]
    c = cap(pkg)
    assert c["envelope"]["area"]["value"] == pytest.approx(3024)
    assert c["envelope"]["area"]["status"] == "verified"
    assert c["gross_area_max"]["value"] == pytest.approx(3000)
    assert c["active_constraint_normative"]["constraint"] == "far"
    assert c["active_constraint_effective"]["constraint"] == "garden_preference"
    assert c["garden_footprint_limit"]["value"] == pytest.approx(1890, abs=0.5)
    assert level(pkg, "normative")["floors_min"] == 1
    assert level(pkg, "normative_with_preferences")["floors_min"] == 2
    assert level(pkg, "strategy_A_with_preferences")["feasible"] is True
    classes = {b["edge_id"]: b["boundary_class"] for b in pkg["boundaries"]}
    assert classes == {"e0": "front", "e1": "side", "e2": "rear", "e3": "side"}


def test_fan_curve_false_infeasible(packages):
    pkg = packages["fan_curve_35_80x100"]
    c = cap(pkg)
    assert pkg["lot_metrics"]["area_sqft"] == pytest.approx(5750)
    assert c["gross_area_max"]["value"] == pytest.approx(3392.5)
    assert c["envelope"]["area"]["value"] == pytest.approx(3582, abs=0.5)
    assert c["envelope"]["area"]["status"] == "provisional"
    assert pkg["realizable_capacity"][0]["area"]["value"] == pytest.approx(2415.6, abs=1.0)
    assert c["active_constraint_effective"]["constraint"] == "realization"
    assert level(pkg, "normative_with_preferences")["feasible"] is True
    assert level(pkg, "strategy_A_with_preferences")["feasible"] is False
    assert c["feasibility"]["false_infeasible_risk"] is True


def test_fan_sensitivity_to_width_method(packages):
    s = packages["fan_curve_35_80x100"]["sensitivity"]
    assert s["varies"] and s["side_setback_varies"] and not s["rear_setback_varies"]
    assert s["envelope_area_max_sqft"] == pytest.approx(3759, abs=1.0)
    widths = {r["width_method"]: r["lot_width_ft"] for r in s["rows"]}
    assert widths == pytest.approx({"mean_width": 57.5, "frontage": 35, "at_front_setback": 41.75})


def test_fan_cul_de_sac(packages):
    c = cap(packages["fan_cul_de_sac_35_80x100"])
    assert c["setbacks"]["front"]["value"] == 10
    assert c["envelope"]["area"]["value"] == pytest.approx(3744, abs=1.0)


def test_corner_lot(packages):
    pkg = packages["corner_55x100"]
    c = cap(pkg)
    assert c["setbacks"]["street_side"]["value"] == 5
    assert c["envelope"]["area"]["value"] == pytest.approx(3312)
    assert c["gross_area_max"]["value"] == pytest.approx(3245)
    assert c["active_constraint_effective"]["constraint"] == "far"
    assert pkg["lot_metrics"]["is_corner"] is True


def test_hillside_occupancy_becomes_active():
    brief = load_brief("interior_50x100")
    brief["terrain"]["steep_hillside_fraction"] = 0.6
    brief["preferences"]["min_garden_area_sqft"] = None
    c = run_capacity(brief)["capacity"]
    assert c["footprint_max_normative"]["value"] == pytest.approx(2500)
    assert c["active_constraint_normative"]["constraint"] == "occupancy_hillside"


def test_shallow_lot_rear_setback_in_pipeline():
    brief = load_brief("interior_50x100")
    brief["lot"]["vertices"] = [[0, 0], [55, 0], [55, 95], [0, 95]]
    c = run_capacity(brief)["capacity"]
    assert c["setbacks"]["rear"]["value"] == pytest.approx(9.5)
    assert c["envelope"]["area"]["value"] == pytest.approx(47 * 70.5)


def test_arc_front_lot_runs_and_is_flagged():
    brief = load_brief("interior_50x100")
    brief["lot"]["edges"][0]["kind"] = "arc"
    brief["lot"]["edges"][0]["arc"] = {"radius_ft": 60, "bulge": "inward"}
    brief["streets"][0]["street_type"] = "cul_de_sac"
    brief["streets"][0]["curve_radius_ft"] = 60
    pkg = run_capacity(brief)
    assert pkg["lot_metrics"]["frontage_ft"] > 50
    assert pkg["lot_metrics"]["is_convex"] is False
    assert pkg["capacity"]["envelope"]["area"]["status"] == "provisional"


def test_triangular_lot_rear_is_provisional():
    brief = load_brief("interior_50x100")
    brief["lot"]["vertices"] = [[0, 0], [60, 0], [30, 120]]
    brief["lot"]["edges"] = brief["lot"]["edges"][:3]
    brief["preferences"]["min_garden_area_sqft"] = None
    pkg = run_capacity(brief)
    rear = [b for b in pkg["boundaries"] if b["boundary_class"] == "rear"]
    assert len(rear) == 1 and rear[0]["status"] == "provisional"
