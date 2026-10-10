"""Area logic with the client's design variables (2026-10-09): design footprint, one floor first, optimum at the
footprint, maximum at the effective FOT, lot minimum and the normative sensitivity."""

import pytest

from spaceplan.core.lib.catalog import load_catalog
from spaceplan.core.lib.design_variables import load_design_variables
from spaceplan.modules.areas.lib.area_matrix import rank_schemes
from spaceplan.modules.areas.lib.sensitivity import EXCEEDS, ONE, TWO, classify, sweep, thresholds
from spaceplan.modules.profiles.lib.program_profiles import footprint_index
from spaceplan.pipeline.main.run_area_analysis import run_area_matrix


@pytest.fixture(scope="module")
def interior():
    return run_area_matrix(lots=["interior_50x100"], households=[("empty_nest", "anglo"), ("teens_family", "latino")],
                           zone_top=0)


@pytest.fixture(scope="module")
def legacy():
    return run_area_matrix(lots=["interior_50x100"], households=[("empty_nest", "anglo"), ("teens_family", "latino")],
                           zone_top=0, design=False)


def test_budget_carries_the_design_limits(interior):
    b = interior["lots"][0]["budget"]
    assert b["footprint_design_sqft"] == pytest.approx(1814.4)
    assert b["design"]["maximum_governing"] == "sdmc_far" and b["far_gross_max_sqft"] == pytest.approx(3000.0)
    assert interior["meta"]["design_variables"]["fos"] == 0.6 and interior["meta"]["normative"]


def test_ground_floor_never_exceeds_the_design_footprint(interior):
    fp = interior["lots"][0]["budget"]["footprint_design_sqft"]
    for c in interior["cells"]:
        if c["status"] in ("fits", "fits_small_garden"):
            assert c["ground_sqft"] <= fp + 1e-6
        if c["ground_sqft"] > fp + 1e-6:
            assert c["status"] == "exceeds_design_footprint"


def test_one_floor_first(interior):
    groups = {}
    for c in interior["cells"]:
        groups.setdefault((c["household_id"], c["profile"]), []).append(c)
    for cells in groups.values():
        best = [c for c in cells if c["best"]]
        one_ok = any(c["floors"] == 1 and c["score"] is not None for c in cells)
        if best and one_ok:
            assert best[0]["floors"] == 1
        for c in cells:
            assert c["policy_excluded"] == (one_ok and c["floors"] > 1 and c["score"] is not None)


def test_optimum_fits_one_floor_and_maximum_reaches_the_fot(interior, legacy):
    fp = interior["lots"][0]["budget"]["footprint_design_sqft"]
    opt = [c for c in interior["cells"] if c["profile"] == "optimum" and c["scheme_id"] == "V0"]
    assert opt and all(c["gross_sqft"] <= fp + 1e-6 for c in opt)
    leg = [c for c in legacy["cells"] if c["profile"] == "optimum" and c["scheme_id"] == "V0"]
    assert {c["household_id"] for c in leg} == {c["household_id"] for c in opt}
    assert all(c["gross_sqft"] <= interior["lots"][0]["budget"]["far_gross_max_sqft"] + 1e-6
               for c in interior["cells"] if c["profile"] == "maximum")


def test_lot_minimum_is_a_one_bedroom_reference(interior):
    m = interior["lots"][0]["budget"]["lot_minimum"]
    assert m["typology_id"] == "h1_basic" and "primary_suite" in m["spaces"] and "bedroom" not in m["spaces"]
    assert 600 < m["gross_sqft"] < 1000 and m["fits_one_floor"] and m["within_fot"]
    assert m["gross_sqft"] < min(c["gross_sqft"] for c in interior["cells"] if c["profile"] == "minimum")


def test_rank_policy_keeps_two_floors_when_one_does_not_fit():
    cells = [{"lot_id": "l", "household_id": "h", "profile": "p", "floors": 1, "score": None, "scheme_id": "V0",
              "score_parts": {"a": 0}},
             {"lot_id": "l", "household_id": "h", "profile": "p", "floors": 2, "score": 0.5, "scheme_id": "V1",
              "score_parts": {"a": 0.5}}]
    rank_schemes(cells, "one_floor_first")
    assert cells[1]["best"] and not cells[1]["policy_excluded"]


def test_footprint_index():
    assert footprint_index([1000, 1500, 1900, 2400], 1814) == (1, True)
    assert footprint_index([2000, 2400], 1814) == (0, False)


# ------------------------------------------------------------------ sensitivity


def test_classify_and_monotone_sweep(interior):
    assert classify(1500, 1814, 3000, 88) == ONE and classify(2500, 1814, 3000, 88) == TWO
    assert classify(2950, 1814, 3000, 88) == EXCEEDS
    dv = load_design_variables()
    lots = [{"budget": interior["lots"][0]["budget"]}]
    demands = {"a": {"minimum": 1300, "complete": 2400}, "b": {"minimum": 1500, "complete": 3200}}
    stair = 2 * load_catalog().space_type("stair")["area"]["target"]
    rows = sweep(dv, lots, demands, [0.4, 0.6, 0.8], [0.6, 0.85, 1.2], stair)
    fos = [r for r in rows if r["sweep"] == "fos"]
    one = [r["complete_one_floor_share"] for r in fos]
    assert one == sorted(one)  # more FOS, never fewer one-floor programs
    fot = [r for r in rows if r["sweep"] == "fot"]
    exceed = [r["complete_exceeds_share"] for r in fot]
    assert exceed == sorted(exceed, reverse=True)  # more FOT, never more programs left out
    assert all(not r["normative"] for r in fot) and all(r["normative"] for r in fos)
    assert fot[-1]["maximum_governing"] == "height_floors_x_footprint"
    t = thresholds(rows, demands)[0]
    assert t["lot_id"] == "interior-50x100" and t["median_complete_sqft"] == pytest.approx(2800)


def test_cli_sensitivity(tmp_path):
    from spaceplan.pipeline.main.cli import main

    assert main(["sensitivity", "interior_50x100", "--households", "empty_nest.anglo", "--fos-grid", "0.5:0.7:0.1",
                 "--fot-grid", "0.6:0.8:0.1", "--tables", str(tmp_path), "--figure", str(tmp_path / "s.png"),
                 "--fos", "0.55"]) == 0
    assert (tmp_path / "sensitivity_grid.csv").exists() and (tmp_path / "s.png").stat().st_size > 0
