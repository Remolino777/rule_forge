"""Step 6.5d: expansion curve, minimum / optimum / maximum, staged, accessible, review notes and sheets."""

import ast
import copy
from collections import Counter
from pathlib import Path

import pytest

from conftest import load_brief
from spaceplan.lib.catalog import load_catalog
from spaceplan.lib.cost_models import get_cost_model
from spaceplan.lib.program_profiles import ProfileContext, accessible_program, expansion_profiles, floor_feasibility
from spaceplan.lib.quantities import reference_sheet
from spaceplan.lib.review_notes import render_observations
from spaceplan.lib_aux.knee import greedy_ratio_path, knee_index
from spaceplan.main.run_capacity import run_capacity
from spaceplan.main.run_household import household_stages
from spaceplan.main.run_profiles import run_profiles

ROOT = Path(__file__).resolve().parents[1] / "spaceplan"
CASES = [("early_childhood", "latino"), ("multigenerational", None), ("young_couple", "anglo"), ("empty_nest", None)]


@pytest.fixture(scope="module")
def catalog():
    return load_catalog()


def make_ctx(archetype, culture=None, far=3000.0, budget=None, model="base"):
    st = household_stages({"archetype_id": archetype, **({"cultural_profile": culture} if culture else {})})
    cat = st["catalog"]
    common = dict(catalog=cat, hcat=st["hcat"], reference=reference_sheet(cat, far, "lot"),
                  model=get_cost_model(model), far_sqft=far, budget_fraction=budget)
    later = ProfileContext(derivation=st["later"]["derivation"], needs=st["later"]["needs"], **common)
    now = ProfileContext(derivation=st["now"]["derivation"], needs=st["now"]["needs"],
                         next_needs=st["later"]["needs"], **common)
    return now, later


def keys(program):
    return Counter((s["space_type"], s.get("household_role", "general")) for s in program["spaces"])


# ------------------------------------------------------------------------------------------ lib_aux


def test_knee_of_a_concave_curve():
    xs = [0, 1, 2, 3, 4, 5]
    ys = [0, 5, 7, 7.5, 7.8, 8]
    assert knee_index(xs, ys) == 2  # normalized distance above the chord: 0.425 at 1, 0.475 at 2
    assert knee_index([0, 1], [0, 1]) == 1
    assert knee_index([0, 1, 2], [0, 1, 2]) == 2  # straight line: no knee, last point


def test_greedy_ratio_path_respects_feasibility():
    items = {"a": (1, 10), "b": (5, 10), "c": (2, 1)}  # cost, gain

    def moves(s):
        return [k for k in items if k not in s]

    path, stop = greedy_ratio_path(frozenset(), moves, lambda s, m: s | {m},
                                   lambda s: sum(items[k][1] for k in s), lambda s: sum(items[k][0] for k in s),
                                   lambda s: (sum(items[k][0] for k in s) <= 6, "cap"))
    assert [m for _, m, _, _ in path[1:]] == ["a", "b"] and stop == "cap"


# ----------------------------------------------------------------------------------- MR-P1 .. MR-P5


@pytest.mark.parametrize("archetype, culture", CASES)
def test_mr_p1_profiles_are_nested(archetype, culture):
    ctx, _ = make_ctx(archetype, culture)
    e = expansion_profiles(ctx)
    sources = {s["src"] for s in ctx.substitutions} | {r for s in ctx.substitutions for r in s["rm"]}
    for small, big in (("minimum", "optimum"), ("optimum", "maximum")):
        a, b = keys(e[small]["program"]), keys(e[big]["program"])
        missing = {k for k in a if a[k] > b.get(k, 0) and k not in sources and not k[0].startswith("garage")}
        assert not missing, (small, big, missing)
        assert e[small]["garage_cars"] <= e[big]["garage_cars"]  # a car move swaps the garage type
    assert e["minimum"]["gross_area_sqft"] <= e["optimum"]["gross_area_sqft"] <= e["maximum"]["gross_area_sqft"]


@pytest.mark.parametrize("archetype, culture", CASES)
def test_mr_p2_curve_is_monotone(archetype, culture):
    ctx, _ = make_ctx(archetype, culture)
    curve = expansion_profiles(ctx)["curve"]
    for a, b in zip(curve, curve[1:]):
        assert b["quality"] > a["quality"] and b["index"] >= a["index"] - 1e-9
    assert curve[-1]["quality"] <= 1.0 + 1e-9


@pytest.mark.parametrize("archetype", ["multigenerational", "early_childhood"])
def test_mr_p3_more_budget_never_lowers_the_maximum(archetype):
    previous = None
    for fraction in (0.45, 0.55, 0.65, 0.85, None):
        ctx, _ = make_ctx(archetype, budget=fraction)
        m = expansion_profiles(ctx)["maximum"]
        if fraction is not None:  # or the minimum itself is already over the budget (staged suggestion)
            assert m["index"] <= fraction + 1e-9 or not m["within_ceilings"]
        if previous is not None:
            assert m["quality"] >= previous["quality"] - 1e-9
        previous = m


@pytest.mark.parametrize("archetype, culture", CASES)
def test_mr_p4_accessible_has_ground_bedroom_and_bath(catalog, archetype, culture):
    ctx, _ = make_ctx(archetype, culture)
    program, features = accessible_program(catalog, expansion_profiles(ctx)["optimum"]["program"])
    by_id = {s["space_id"]: s for s in program["spaces"]}
    bed, bath = by_id[features["ground_floor_bedroom"]], by_id[features["ground_floor_full_bath"]]
    assert bed["floor_preference"] == 0 and bath["floor_preference"] == 0
    assert bath["space_type"] in ("bathroom", "primary_bath") and features["step_free_entry"]


def test_mr_p5_staged_reaches_the_next_stage_and_costs_more_than_building_now():
    from spaceplan.lib.program_profiles import staged_profile

    ctx, later = make_ctx("young_couple")
    e = expansion_profiles(ctx)
    st = staged_profile(ctx, later, e["_states"]["minimum"], e["_states"]["optimum"])
    final = keys(st["final"]["program"])
    for n in later.needs:
        if n.counts["required"]:
            assert final.get((n.space_type, n.household_role), 0) >= n.counts["required"] or \
                (n.space_type, n.household_role) in {s["src"] for s in later.substitutions}
    assert st["staging_premium"] >= 0 and st["final"]["within_normative"]
    assert any(c["space_type"] == "bedroom" and c["household_role"] == "child" for c in st["expansion"])
    assert st["convertible_now"] == ["flex_room_work"]


# ------------------------------------------------------------------------------------------ ceilings


def test_maximum_respects_far_and_reports_the_governing_ceiling():
    ctx, _ = make_ctx("multigenerational", far=2500.0)
    e = expansion_profiles(ctx)
    assert e["maximum"]["gross_area_sqft"] <= 2500 and e["maximum"]["governing"] == "normative"
    ctx, _ = make_ctx("multigenerational", budget=0.6)
    assert expansion_profiles(ctx)["maximum"]["governing"] == "budget"


def test_minimum_over_the_ceiling_is_reported():
    ctx, _ = make_ctx("multigenerational", budget=0.3)
    e = expansion_profiles(ctx)
    assert e["minimum"]["note"] and e["maximum"]["governing"] == "budget" and len(e["curve"]) == 1


def test_floor_feasibility_states():
    assert floor_feasibility(3100, 3000, 2800, 120) == "exceeds_normative"
    assert floor_feasibility(2000, 3000, 2800, 120) == "fits_one_floor"
    assert floor_feasibility(2900, 3000, 2000, 120) == "needs_two_floors"
    assert floor_feasibility(2000, None, None, 0) == "no_lot"


# -------------------------------------------------------------------------------- catalog / display


def test_display_covers_every_label_and_note(catalog):
    display = catalog.data["display"]
    types = {t["space_type"] for t in catalog.data["space_types"]}
    elements = {e["element"] for e in catalog.data["backyard_elements"]}
    for lang in ("es", "en"):
        labels = display["labels"][lang]
        assert types <= set(labels["space_types"]) and elements <= set(labels["backyard"])
        assert set(display["review_notes"]["es"]) == set(display["review_notes"][lang])
        assert set(display["sheet"]["es"]) == set(display["sheet"][lang])


def test_breakfast_nook_is_social_and_retry_is_off_in_corrections(catalog):
    assert catalog.space_type("breakfast_nook")["zone"] == "social"
    assert catalog.data["circulation"]["search_retry"]["zone_schemes"] > catalog.data["circulation"]["search"]["zone_schemes"]
    tree = ast.parse((ROOT / "main" / "run_corrections.py").read_text(encoding="utf-8"))
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "zone_site_options"]
    assert calls and all(any(k.arg == "retry" and k.value.value is False for k in c.keywords) for c in calls)


def test_empty_nest_anglo_now_zones():
    brief = load_brief("interior_50x100_multigen")
    brief["household"] = {"archetype_id": "empty_nest", "program_tier": "preferred", "cultural_profile": "anglo"}
    assert run_capacity(brief, corrections=False)["zoning"]["options"][0]["status"] == "zoned"


# ------------------------------------------------------------------------------ portfolio end to end


@pytest.fixture(scope="module")
def portfolio(tmp_path_factory):
    brief = load_brief("interior_50x100_multigen")
    brief["household"] = {"archetype_id": "early_childhood", "cultural_profile": "latino"}
    brief["meta"]["brief_id"] = "ec-latino"
    out = tmp_path_factory.mktemp("sheets")
    return run_profiles(brief, budget={"level": "medium"}, zone=True, sheets_dir=out), out


def test_portfolio_profiles_and_sheets(portfolio):
    pf, out = portfolio
    p = pf["profiles"]
    assert pf["reading"] == "lot" and pf["ceilings"]["governing"] == "budget"
    assert p["maximum"]["index"] <= pf["ceilings"]["budget_fraction"] + 1e-9
    assert p["optimum"]["zoning_status"] == "zoned" and p["optimum"]["observations"]
    assert any(o["code"] == "passed" for o in p["optimum"]["observations"])
    files = sorted(Path(f).name for f in pf["sheets"])
    assert "ec-latino_optimum.png" in files and "ec-latino_portfolio.png" in files
    assert all((out / f).stat().st_size > 50_000 for f in files)


def test_observation_templates_render_every_code(portfolio, catalog):
    pf, _ = portfolio
    obs = pf["profiles"]["optimum"]["observations"]
    for lang in ("es", "en"):
        lines = render_observations(obs, catalog.data["display"]["review_notes"][lang], lambda k: k)
        assert len(lines) == len(obs) and all("{" not in line for line in lines)


def test_reference_reading_without_lot():
    pf = run_profiles({"household": {"archetype_id": "remote_work"}, "meta": {"brief_id": "rw"}})
    assert pf["reading"] == "reference_dwelling" and pf["ceilings"]["governing"] == "program_complete"
    assert all(pf["profiles"][k]["feasibility"] == "no_lot" for k in ("minimum", "optimum", "maximum"))


def test_cli_profiles(capsys):
    from spaceplan.main.cli import main

    assert main(["profiles", "empty_nest", "--culture", "anglo"]) == 0
    out = capsys.readouterr().out
    assert "optimum" in out and "staged" in out and "curve" in out


def test_profiles_never_mutate_the_brief():
    brief = load_brief("interior_50x100_multigen")
    before = copy.deepcopy(brief)
    run_profiles({"household": brief["household"], "meta": brief["meta"]})
    assert brief == before
