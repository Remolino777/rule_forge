"""Step 6.6: building indices (IC/IO), vertical schemes, area budget per lot, area matrix, flag lots."""

import copy
import json

import pytest

from conftest import load_brief
from spaceplan.lib.area_budget import SiteMeasurer, evaluate_split, frontage_need, lot_budget
from spaceplan.lib.area_matrix import household_cells, pareto_cells
from spaceplan.lib.building_indices import INDICES_RULE, IndexLimits, evaluate_indices, indices_all_variants
from spaceplan.lib.catalog import catalog_errors, load_catalog
from spaceplan.lib.cost_models import get_cost_model
from spaceplan.lib.flag_lot import FlagLotError, resolve_flag_lot
from spaceplan.lib.quantities import build_sheet, reference_sheet
from spaceplan.lib.vertical_split import (
    applicable_schemes,
    has_empty_upper,
    program_group_facts,
    split_program,
    vertical_metrics,
)
from spaceplan.lib_aux.pareto import dominates, pareto_front
from spaceplan.main.cli import main as cli_main
from spaceplan.main.run_area_matrix import PILOT_LOTS, run_area_matrix
from spaceplan.main.run_capacity import prepare_lot, run_capacity
from spaceplan.main.run_household import household_stages
from spaceplan.main.run_profiles import profile_programs

NO_LOT = {"steep_hillside_fraction": 0.0, "view_side": "none"}


@pytest.fixture(scope="module")
def catalog():
    return load_catalog()


@pytest.fixture(scope="module")
def vs(catalog):
    return catalog.data["vertical_schemes"]


def programs(catalog, archetype, culture=None, far=3000.0):
    st = household_stages({"archetype_id": archetype, "cultural_profile": culture}, None)
    _, prof = profile_programs(st, catalog, get_cost_model("base"), reference_sheet(catalog, far, "lot"),
                               far_sqft=far)
    return st, prof


def schemes_by_id(vs):
    return {s["scheme_id"]: s for s in vs["schemes"]}


def facts_of(st, vs, program, lot=NO_LOT):
    return {**st["now"]["derivation"].facts, **program_group_facts(vs, program), **lot}


@pytest.fixture(scope="module")
def lot_setups(rs, catalog):
    out = {}
    for name in ("interior_50x100", "fan_cul_de_sac_35_80x100", "hillside_50x100"):
        brief = load_brief(name)
        setup = prepare_lot(brief, rs, catalog)
        budget = lot_budget(catalog, rs, brief, setup)
        out[name] = (brief, setup, budget, SiteMeasurer(catalog, rs, brief, setup, budget))
    return out


# ------------------------------------------------------------------------------------------ data


def test_indices_rule_in_dsl(rs):
    rule = rs.rule(INDICES_RULE)
    symbols = {i["symbol"] for i in rule["parameters"]["indices"]}
    assert symbols == {"IC", "IO"}
    assert {v["variant_id"] for v in rule["variants"]} == {"garage_included", "garage_excluded"}
    assert rule["parameters"]["default_variant"] == "garage_included"
    assert all(v["verified"] is False for v in rule["variants"])  # pending SDMC 113.0234


def test_catalog_sections_have_provisional_source(catalog):
    for key in ("area_analysis", "vertical_schemes"):
        assert catalog.data[key]["source"]["status"] == "provisional"
    assert [s["scheme_id"] for s in catalog.data["vertical_schemes"]["schemes"]] == ["V0", "V1", "V2", "V3", "V4", "V5"]


@pytest.mark.parametrize("mutate, message", [
    (lambda d: d["vertical_schemes"]["schemes"][1]["assign"].update(sauna=1), "unknown group"),
    (lambda d: d["vertical_schemes"]["schemes"][1]["assign"].update(primary=2), "outside"),
    (lambda d: d["vertical_schemes"]["schemes"][1]["assign"].update(social="rule"), "only laundry"),
    (lambda d: d["vertical_schemes"]["scoring"]["weights"].pop("cost"), "cover exactly"),
    (lambda d: d["vertical_schemes"]["scoring"]["multipliers"][0].update(metric="beauty"), "unknown metric"),
    (lambda d: d["area_analysis"]["profiles"].append("luxury"), "unknown profile"),
    (lambda d: d["vertical_schemes"]["schemes"].append(copy.deepcopy(d["vertical_schemes"]["schemes"][0])),
     "duplicate scheme_id"),
])
def test_invalid_vertical_catalog(catalog, mutate, message):
    data = copy.deepcopy(catalog.data)
    mutate(data)
    assert any(message in e for e in catalog_errors(data))


def test_no_normative_number_in_new_code():
    """Only structural literals (0, 1, 2, rounding digits, tolerances, the 0.5 midpoint of a metric)."""
    import ast
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "spaceplan" / "lib"
    allowed = {0, 1, 2, 3, 4, 0.5, 1e-6, 0.01}
    for name in ("building_indices.py", "vertical_split.py", "area_budget.py", "area_matrix.py", "flag_lot.py"):
        tree = ast.parse((root / name).read_text())
        numbers = {n.value for n in ast.walk(tree) if isinstance(n, ast.Constant)
                   and isinstance(n.value, (int, float)) and not isinstance(n.value, bool)}
        assert numbers <= allowed, (name, numbers - allowed)


# ------------------------------------------------------------------------------------- indices


def test_ic_io_definitions():
    limits = IndexLimits(5000.0, 3000.0, None)
    r = evaluate_indices(load_ruleset_cached(), limits, (1500.0, 900.0), {"garage": 400.0, "social": 2000.0})
    assert r["indices"]["IC"]["value"] == pytest.approx(2400 / 5000)
    assert r["indices"]["IO"]["value"] == pytest.approx(1500 / 5000)
    assert r["indices"]["IC"]["limit"] == pytest.approx(0.6)
    assert r["indices"]["IO"]["limit"] is None and r["indices"]["IO"]["passes"]
    assert r["by_floor"] == [pytest.approx(0.3), pytest.approx(0.18)]
    alt = evaluate_indices(load_ruleset_cached(), limits, (1500.0, 900.0), {"garage": 400.0}, "garage_excluded")
    assert alt["indices"]["IC"]["value"] == pytest.approx(2000 / 5000)
    assert alt["indices"]["IO"]["value"] == pytest.approx(1500 / 5000)  # coverage is physical


def test_garage_variant_sensitivity_flag():
    limits = IndexLimits(5000.0, 3000.0, None)
    r = indices_all_variants(load_ruleset_cached(), limits, (2000.0, 1100.0), {"garage": 420.0})
    assert not r["indices"]["IC"]["passes"]
    assert r["alternatives"]["garage_excluded"]["passes"]
    assert r["variant_sensitive"] == ["IC"]


_RS = {}


def load_ruleset_cached():
    from spaceplan.lib.rules import load_ruleset

    if "rs" not in _RS:
        _RS["rs"] = load_ruleset()
    return _RS["rs"]


# ----------------------------------------------------------------------------- vertical schemes


def test_mr_a5_stair_is_the_only_ic_difference(catalog, vs):
    st, prof = programs(catalog, "teens_family", "anglo")
    program = prof["optimum"]["program"]
    by = schemes_by_id(vs)
    f = facts_of(st, vs, program)
    v0, v1 = split_program(catalog, program, by["V0"], f), split_program(catalog, program, by["V1"], f)
    stair = catalog.space_type("stair")["area"]["target"]
    assert v1.gross - v0.gross == pytest.approx(2 * stair)
    sheet = build_sheet(catalog, program, "x", floors=2, floor_shares=v1.shares)
    assert sheet.gross_area == pytest.approx(v1.gross)  # same convention as the quantity sheet
    assert sheet.footprint.value == pytest.approx(v1.ground)


@pytest.mark.parametrize("archetype", ["young_couple", "early_childhood", "teens_family", "multigenerational",
                                       "remote_work", "shared_adults"])
def test_mr_a6_private_up_lowers_occupancy(catalog, vs, archetype):
    st, prof = programs(catalog, archetype)
    program = prof["optimum"]["program"]
    f = facts_of(st, vs, program)
    by = schemes_by_id(vs)
    v0 = split_program(catalog, program, by["V0"], f)
    v1 = split_program(catalog, program, by["V1"], f)
    assert v1.ground < v0.ground
    if by["V2"] in applicable_schemes(vs, f):
        assert v1.ground <= split_program(catalog, program, by["V2"], f).ground + 1e-6


def test_mr_v1_reduced_mobility_suite_stays_down(catalog, vs):
    st, prof = programs(catalog, "multigenerational", "latino")
    for name in ("minimum", "optimum", "accessible"):
        program = prof[name]["program"]
        f = facts_of(st, vs, program)
        for scheme in applicable_schemes(vs, f):
            sp = split_program(catalog, program, scheme, f)
            for s in program["spaces"]:
                if s.get("household_role") == "accessible" or s.get("floor_preference") == 0:
                    assert sp.floor_of[s["space_id"]] == 0, (name, scheme["scheme_id"], s["space_id"])


def test_suite_cohesion_for_anticipated_mobility(catalog, vs):
    """Empty nest (H16: primary bath on the ground floor) - the suite is never split across floors."""
    st, prof = programs(catalog, "empty_nest")
    program = prof["maximum"]["program"]
    f = facts_of(st, vs, program)
    sp = split_program(catalog, program, schemes_by_id(vs)["V1"], f)
    floors = {sp.floor_of[s["space_id"]] for s in program["spaces"]
              if s.get("household_role") == "primary" and not s.get("host_space_id")}
    assert floors == {0}
    assert any("suite stays together" in e["reason"] for e in sp.exceptions)


def test_empty_nest_has_options(catalog, vs):
    """The empty nest is not forced into 'private upstairs': with guests in the program V2/V4 compete."""
    st, prof = programs(catalog, "empty_nest", "anglo")
    program = prof["maximum"]["program"]
    f = facts_of(st, vs, program)
    ids = {s["scheme_id"] for s in applicable_schemes(vs, f)}
    assert {"V0", "V2", "V4"} <= ids
    splits = [split_program(catalog, program, s, f) for s in applicable_schemes(vs, f)]
    assert sum(not has_empty_upper(catalog, sp) for sp in splits) >= 3


def test_mr_v2_single_floor_has_no_stair_dependency(catalog, vs):
    for arch in ("young_couple", "empty_nest", "multigenerational"):
        st, prof = programs(catalog, arch)
        program = prof["optimum"]["program"]
        f = facts_of(st, vs, program)
        m = vertical_metrics(catalog, split_program(catalog, program, schemes_by_id(vs)["V0"], f), program, f)
        assert m["stair_independence"] == 1.0 and m["upper_efficiency"] == 1.0


def test_mr_v5_household_changes_order_not_set(catalog, vs):
    """Applicability depends on the program and the lot, never on who the household is."""
    _, prof = programs(catalog, "teens_family")
    program = prof["optimum"]["program"]
    sets = []
    for arch in ("teens_family", "empty_nest", "young_couple"):
        st = household_stages({"archetype_id": arch}, None)
        sets.append([s["scheme_id"] for s in applicable_schemes(vs, facts_of(st, vs, program))])
    assert sets[0] == sets[1] == sets[2]


def test_supervision_and_separation(catalog, vs):
    st, prof = programs(catalog, "early_childhood")
    program = prof["optimum"]["program"]
    f = facts_of(st, vs, program)
    by = schemes_by_id(vs)
    v1 = vertical_metrics(catalog, split_program(catalog, program, by["V1"], f), program, f)
    v2 = vertical_metrics(catalog, split_program(catalog, program, by["V2"], f), program, f)
    assert v1["supervision"] == 1.0 and v2["supervision"] == 0.0
    st, prof = programs(catalog, "teens_family")
    program = prof["optimum"]["program"]
    f = facts_of(st, vs, program)
    v0 = vertical_metrics(catalog, split_program(catalog, program, by["V0"], f), program, f)
    v2 = vertical_metrics(catalog, split_program(catalog, program, by["V2"], f), program, f)
    assert v0["separation"] == 0.0 and v2["separation"] == 1.0


@pytest.mark.parametrize("culture, upstairs", [("anglo", True), ("latino", False)])
def test_laundry_follows_cultural_aspect(catalog, vs, culture, upstairs):
    st, prof = programs(catalog, "teens_family", culture)
    program = prof["optimum"]["program"]
    f = facts_of(st, vs, program)
    sp = split_program(catalog, program, schemes_by_id(vs)["V1"], f)
    laundry = [s["space_id"] for s in program["spaces"] if s["space_type"] in ("laundry", "laundry_closet")]
    assert laundry
    assert all((sp.floor_of[sid] == 1) is upstairs for sid in laundry)


def test_v5_needs_view_or_hillside(catalog, vs):
    st, prof = programs(catalog, "young_couple")
    program = prof["optimum"]["program"]
    flat = {s["scheme_id"] for s in applicable_schemes(vs, facts_of(st, vs, program))}
    view = {s["scheme_id"] for s in applicable_schemes(vs, facts_of(st, vs, program, {**NO_LOT, "view_side": "rear"}))}
    assert "V5" not in flat and "V5" in view
    st, prof = programs(catalog, "multigenerational")
    program = prof["optimum"]["program"]
    hill = {"steep_hillside_fraction": 0.6, "view_side": "rear"}
    assert "V5" not in {s["scheme_id"] for s in applicable_schemes(vs, facts_of(st, vs, program, hill))}


# ------------------------------------------------------------------------------- lot budget (E0/E1)


def test_mr_a4_rectangular_lots_collapse_strategies(lot_setups):
    assert lot_setups["interior_50x100"][2].strategies_equal
    fan = lot_setups["fan_cul_de_sac_35_80x100"][2]
    assert not fan.strategies_equal
    areas = [s.area_sqft for s in fan.strategies]
    assert areas == sorted(areas)  # A <= B2 <= B3 <= P


def test_mr_a7_hillside_occupancy_binds(lot_setups, catalog, rs, vs):
    brief, _, budget, measurer = lot_setups["hillside_50x100"]
    assert budget.limits.coverage_max == pytest.approx(0.5)
    st, prof = programs(catalog, "teens_family", far=budget.limits.gross_area_max_sqft)
    program = prof["maximum"]["program"]
    f = facts_of(st, vs, program, budget.lot_facts)
    by = schemes_by_id(vs)
    v0 = split_program(catalog, program, by["V0"], f)
    assert v0.ground > 0.5 * budget.lot_area_sqft
    ev = evaluate_split(catalog, rs, budget, program, v0, measurer)
    assert ev["status"] == "exceeds_coverage"
    flat = lot_setups["interior_50x100"]
    ev_flat = evaluate_split(catalog, rs, flat[2], program, v0, flat[3])
    assert "exceeds_coverage" not in ev_flat["strategies"][0]["fails"]
    v1 = split_program(catalog, program, by["V1"], f)
    assert evaluate_split(catalog, rs, budget, program, v1, measurer)["indices"]["indices"]["IO"]["passes"]


def test_mr_a1_more_program_never_more_open_area(lot_setups, catalog, rs, vs):
    brief, _, budget, measurer = lot_setups["fan_cul_de_sac_35_80x100"]
    st, prof = programs(catalog, "multigenerational", "latino", far=budget.limits.gross_area_max_sqft)
    by = schemes_by_id(vs)
    for scheme in ("V0", "V1"):
        prev = None
        for name in ("minimum", "optimum", "maximum"):
            program = prof[name]["program"]
            sp = split_program(catalog, program, by[scheme], facts_of(st, vs, program, budget.lot_facts))
            ev = evaluate_split(catalog, rs, budget, program, sp, measurer)
            if prev is not None and ev["strategy_used"] == prev[1]:
                assert ev["open_area_sqft"] <= prev[0] + 1e-6
            prev = (ev["open_area_sqft"], ev["strategy_used"])


def test_mr_a2_two_floors_free_land(lot_setups, catalog, rs, vs):
    brief, _, budget, measurer = lot_setups["interior_50x100"]
    st, prof = programs(catalog, "early_childhood")
    program = prof["optimum"]["program"]
    f = facts_of(st, vs, program, budget.lot_facts)
    by = schemes_by_id(vs)
    e0 = evaluate_split(catalog, rs, budget, program, split_program(catalog, program, by["V0"], f), measurer)
    e1 = evaluate_split(catalog, rs, budget, program, split_program(catalog, program, by["V1"], f), measurer)
    assert e1["open_area_sqft"] > e0["open_area_sqft"]
    assert e1["indices"]["indices"]["IO"]["value"] < e0["indices"]["indices"]["IO"]["value"]


def test_frontage_need_living_anchor(catalog, vs):
    st, prof = programs(catalog, "young_couple")
    program = prof["optimum"]["program"]
    f = facts_of(st, vs, program, {**NO_LOT, "view_side": "rear"})
    by = schemes_by_id(vs)
    v0 = frontage_need(catalog, program, split_program(catalog, program, by["V0"], f))
    v5 = frontage_need(catalog, program, split_program(catalog, program, by["V5"], f))
    assert v0["hard_ft"] == v5["hard_ft"] and v0["soft_ft"] > v5["soft_ft"]
    assert v0["living_on_ground"] and not v5["living_on_ground"]


# ---------------------------------------------------------------------------------- area matrix


@pytest.fixture(scope="module")
def small_matrix():
    return run_area_matrix(lots=["interior_50x100", "fan_cul_de_sac_35_80x100"],
                           households=[("empty_nest", "anglo"), ("multigenerational", "latino"),
                                       ("early_childhood", None)], zone_top=0)


def test_mr_a3_consistent_with_profiles(small_matrix, catalog):
    """A single-floor cell exceeds the IC exactly when 6.5d says the profile exceeds the norm."""
    for c in small_matrix["cells"]:
        if c["floors"] == 1:
            assert (c["status"] == "exceeds_far") == (c["IC"] > c["IC_max"] + 1e-6)


def test_every_feasible_group_has_one_best(small_matrix):
    groups = {}
    for c in small_matrix["cells"]:
        groups.setdefault((c["lot_id"], c["household_id"], c["profile"]), []).append(c)
    for cells in groups.values():
        feasible = [c for c in cells if c["score"] is not None]
        assert sum(c["best"] for c in cells) == (1 if feasible else 0)
        for c in cells:
            assert (c["score"] is None) == (c["status"] not in ("fits", "fits_small_garden"))


def test_two_floor_maximum_net_of_stair(small_matrix):
    for c in small_matrix["cells"]:
        if c["profile"] == "maximum" and c["floors"] == 2:
            assert c["status"] != "exceeds_far" or c["variant_sensitive"]


def test_pareto_cells_non_dominated(small_matrix):
    cells = [c for c in small_matrix["cells"] if c["household_id"] == "multigenerational.latino"
             and c["lot_id"] == "interior-50x100"]
    front = pareto_cells(cells)
    assert front
    key = lambda c: (c["open_area_sqft"], -c["index"], c["program_quality"] or 0.0)  # noqa: E731
    for a in front:
        assert not any(dominates(key(b), key(a), ("max", "max", "max")) for b in cells if b["score"] is not None)


def test_mr_v3_client_forced_scheme_is_evaluated(rs, catalog):
    r = run_area_matrix(lots=["interior_50x100"], households=[("young_couple", None)], zone_top=0,
                        forced_schemes=("V5",))
    forced = [c for c in r["cells"] if c["scheme_id"] == "V5"]
    assert forced and all(c["forced"] for c in forced)
    r0 = run_area_matrix(lots=["interior_50x100"], households=[("young_couple", None)], zone_top=0)
    assert not any(c["scheme_id"] == "V5" for c in r0["cells"])


def test_cells_do_not_expose_household_composition(small_matrix):
    text = json.dumps(small_matrix["cells"][:20])
    assert "age_years" not in text and "members" not in text


def test_pilot_lot_list():
    assert len(PILOT_LOTS) == 10
    for name in PILOT_LOTS:
        assert load_brief(name)["dwelling_type"] == "house"


# ------------------------------------------------------------------------------------- flag lot


def test_flag_lot_transform():
    brief = load_brief("flag_70x80_pole20")
    body, flag = resolve_flag_lot(brief)
    assert flag["body_area_sqft"] == pytest.approx(5600) and flag["access_strip_area_sqft"] == pytest.approx(800)
    assert flag["street_frontage_ft"] == pytest.approx(20) and flag["status"] == "provisional"
    assert "flag" not in body["lot"] and body["lot"]["edges"][0]["boundary_class"] == "front"
    same, none = resolve_flag_lot(load_brief("interior_50x100"))
    assert none is None


def test_flag_lot_invalid():
    brief = load_brief("flag_70x80_pole20")
    brief["lot"]["flag"]["access_strip_vertices"] = [[25, 0], [45, 0], [45, 20], [25, 20]]
    with pytest.raises(FlagLotError):
        resolve_flag_lot(brief)


def test_flag_lot_capacity_and_budget(rs, catalog):
    pkg = run_capacity(load_brief("flag_70x80_pole20"), corrections=False)
    assert any("flag lot (provisional)" in w for w in pkg["warnings"])
    brief = load_brief("flag_70x80_pole20")
    body, flag = resolve_flag_lot(brief)
    budget = lot_budget(catalog, rs, body, prepare_lot(body, rs, catalog), flag)
    assert budget.extra_paving_sqft == pytest.approx(800)
    assert budget.far_alternatives["full_lot"]["gross_max_sqft"] > budget.limits.gross_area_max_sqft


def test_new_pilot_lots_variants(rs, catalog):
    shallow = prepare_lot(load_brief("shallow_50x95"), rs, catalog)
    narrow = prepare_lot(load_brief("narrow_40x125"), rs, catalog)
    assert shallow.evaluation.decisions["rear"].value == pytest.approx(9.5)
    assert narrow.evaluation.decisions["side"].value == pytest.approx(3.2)


# -------------------------------------------------------------------------------------- helpers


def test_pareto_helper():
    pts = [(1, 1), (2, 0), (0, 2), (0.5, 0.5)]
    assert pareto_front(pts, key=lambda p: p, senses=("max", "max")) == [(1, 1), (2, 0), (0, 2)]
    assert dominates((1, 0), (2, 0), ("min", "max"))
    with pytest.raises(ValueError):
        dominates((1,), (2,), ("best",))


def test_cli_areas(capsys, tmp_path):
    rc = cli_main(["areas", "interior_50x100", "--households", "empty_nest.anglo", "--zone-top", "0",
                   "--tables", str(tmp_path)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "interior-50x100" in out and "IC max 0.60" in out
    assert (tmp_path / "area_matrix_cells.csv").exists() and (tmp_path / "area_matrix_best.csv").exists()
