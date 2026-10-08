"""Step 6.5b: quantity sheet, relative cost models, budget, tornado and metamorphic relations MR-C1..MR-C5."""

import copy
import re
from pathlib import Path

import pytest

from conftest import load_brief
from spaceplan.lib.budget import assess_budget, resolve_budget
from spaceplan.lib.catalog import catalog_errors, load_catalog
from spaceplan.lib.cost_models import MODELS, evaluate_all, get_cost_model, mode_point, relative_index
from spaceplan.lib.cost_sensitivity import tornado
from spaceplan.lib.enums import HOUSEHOLD_TIERS as TIERS
from spaceplan.lib.program_builder import expand_typology
from spaceplan.lib.quantities import build_sheet, reference_sheet
from spaceplan.main.run_capacity import run_capacity
from spaceplan.main.run_household import derive_household

ROOT = Path(__file__).resolve().parents[1] / "spaceplan"


@pytest.fixture(scope="module")
def catalog():
    return load_catalog()


@pytest.fixture(scope="module")
def ci(catalog):
    return catalog.data["cost_index"]


@pytest.fixture(scope="module")
def program(catalog):
    return expand_typology(catalog, "t3_standard", 2)


@pytest.fixture(scope="module")
def reference_package():
    return run_capacity(load_brief("interior_50x100"), corrections=False, budget={"level": "medium"})


def sheet_of(catalog, program, **kw):
    return build_sheet(catalog, program, kw.pop("label", "x"), **kw)


# --------------------------------------------------------------------------------------- catalog


@pytest.mark.parametrize("mutation, message", [
    (lambda c: c["coefficients"]["habitable_dry"].update(mode=1.2, max=1.3), "anchor class"),
    (lambda c: c["reference_mix"].update(wet=0.5), "sum to 1"),
    (lambda c: c["coefficients"].pop("garage"), "cover exactly"),
    (lambda c: c["form_factors"]["two_floors"].update(min=1.5), "min <= mode <= max"),
    (lambda c: c.update(default_model="carbon"), "default_model"),
])
def test_invalid_cost_index_is_rejected(catalog, mutation, message):
    bad = copy.deepcopy(catalog.data)
    mutation(bad["cost_index"])
    assert any(message in e for e in catalog_errors(bad))


def test_no_money_anywhere():
    """The index is relative: no currency symbol or unit in code or data."""
    pattern = re.compile(r"\$|\busd\b|\bdollars?\b|\beur\b|\bcop\b|per_sq_ft_cost", re.IGNORECASE)
    files = [*ROOT.rglob("*.py"), *(f for f in ROOT.rglob("*.json") if "schemas" not in f.parts)]
    offenders = [str(f) for f in files if pattern.search(f.read_text(encoding="utf-8"))]
    assert offenders == []


# ------------------------------------------------------------------------------------ quantities


def test_sheet_without_site_is_estimated(catalog, program):
    sheet = sheet_of(catalog, program)
    assert sheet.footprint.basis == "estimated" and sheet.confidence == "estimated"
    assert sheet.exterior_by_class["paving"].basis == "not_available"
    assert sheet.gross_area == pytest.approx(sum(s["target_area_sqft"] for s in program["spaces"]) * 1.15)


def test_two_floors_add_the_stair(catalog, program):
    one, two = sheet_of(catalog, program), sheet_of(catalog, program, floors=2)
    stair = catalog.space_type("stair")["area"]["target"]
    assert two.gross_area - one.gross_area == pytest.approx(2 * stair)
    assert two.stairs == 1 and one.stairs == 0 and two.footprint.value < one.footprint.value


def test_site_quantities_are_measured(reference_package):
    options = {o["option_id"]: o for o in reference_package["site_partition"]["options"]}
    for entry in reference_package["cost"]["options"]:
        q, option = entry["quantities"], options[entry["label"]]
        assert q["footprint"] == {"value": option["footprint_area_sqft"], "unit": "sq_ft", "basis": "measured"}
        assert q["exterior_by_class"]["deck"]["basis"] == "measured"


# -------------------------------------------------------------------------------- models / index


@pytest.mark.parametrize("model", list(MODELS))
def test_mr_c3_reference_is_one(catalog, ci, model):
    ref = reference_sheet(catalog, 3000, "ref")
    assert relative_index(get_cost_model(model), ref, ref, ci) == pytest.approx(1.0)


def test_base_index_is_gross_over_far(reference_package):
    n1 = next(e for e in reference_package["cost"]["options"] if e["label"] == "n1")
    far = reference_package["capacity"]["gross_area_max"]["value"]
    assert n1["by_model"]["base"] == pytest.approx(2212 / far, abs=1e-4)


def test_mr_c4_neutral_coefficients_give_base(catalog, ci, program):
    sheet, ref = sheet_of(catalog, program), reference_sheet(catalog, 3000, "ref")
    weighted = get_cost_model("weighted")
    ones = dict.fromkeys(mode_point(weighted, ci), 1.0)
    assert relative_index(weighted, sheet, ref, ci, ones) == pytest.approx(relative_index(get_cost_model("base"), sheet, ref, ci))


@pytest.mark.parametrize("model", list(MODELS))
def test_mr_c1_adding_a_space_never_lowers_the_index(catalog, ci, program, model):
    ref = reference_sheet(catalog, 3000, "ref")
    bigger = copy.deepcopy(program)
    extra = dict(next(s for s in program["spaces"] if s["space_type"] == "bedroom"))
    extra["space_id"] = "bedroom_extra"
    bigger["spaces"].append(extra)
    m = get_cost_model(model)
    assert relative_index(m, sheet_of(catalog, bigger), ref, ci) > relative_index(m, sheet_of(catalog, program), ref, ci)


@pytest.mark.parametrize("model", ["base", "weighted"])
def test_mr_c2_index_is_proportional_to_the_reference(catalog, ci, program, model):
    sheet, m = sheet_of(catalog, program), get_cost_model(model)
    small, large = reference_sheet(catalog, 2000, "r"), reference_sheet(catalog, 4000, "r")
    assert relative_index(m, sheet, small, ci) == pytest.approx(2 * relative_index(m, sheet, large, ci))


@pytest.mark.parametrize("archetype", ["young_couple", "multigenerational", "empty_nest"])
def test_mr_c5_tiers_are_ordered_in_every_model(archetype):
    cost = derive_household({"archetype_id": archetype}, next_stage=False)["cost"]
    assert cost["reading"] == "reference_dwelling" and [e["label"] for e in cost["options"]] == list(TIERS)
    for model in MODELS:
        values = [e["by_model"][model] for e in cost["options"]]
        assert values == sorted(values), (model, values)


def test_shape_model_applies_form_factors(catalog, ci, program):
    ref = reference_sheet(catalog, 3000, "ref")
    flat = sheet_of(catalog, program)
    stepped = sheet_of(catalog, program, strategy="B_stepped_footprint")
    hill = sheet_of(catalog, program, mean_slope=0.4)
    idx = {k: evaluate_all(catalog, s, ref)["shape"]["index"] for k, s in
           {"flat": flat, "stepped": stepped, "hill": hill}.items()}
    w = evaluate_all(catalog, flat, ref)["weighted"]["index"]
    assert idx["flat"] == pytest.approx(w)
    assert idx["stepped"] == pytest.approx(w * ci["form_factors"]["stepped_footprint"]["mode"])
    assert idx["hill"] == pytest.approx(w * ci["form_factors"]["hillside"]["mode"])


# ---------------------------------------------------------------------------------------- budget


def test_budget_levels_and_governing(ci):
    medium = resolve_budget(ci, {"level": "medium"})
    assert medium["fraction_of_max"] == ci["budget_levels"]["medium"]
    out = assess_budget(medium, {"required": 0.7, "preferred": 0.9}, "lot", "required")
    assert out["governing"] == "budget" and out["buildable_max_index"] == medium["fraction_of_max"]
    assert any(s.startswith("staged_construction") for s in out["suggestions"])
    free = assess_budget(None, {"a": 0.5}, "lot")
    assert free["governing"] == "normative" and free["verdicts"]["a"]["within_budget"] is None
    generous = assess_budget(resolve_budget(ci, {"fraction_of_max": 1.2}), {"a": 1.1}, "lot")
    assert generous["governing"] == "normative" and not generous["verdicts"]["a"]["within_normative"]
    assert assess_budget(medium, {"a": 0.5}, "reference_dwelling")["applies"] is False
    with pytest.raises(ValueError):
        resolve_budget(ci, {"level": "lavish"})


def test_household_brief_gets_tier_options_and_staging():
    brief = load_brief("interior_50x100_multigen")
    brief["budget"] = {"level": "tight"}
    pkg = run_capacity(brief, corrections=False)
    labels = [e["label"] for e in pkg["cost"]["options"]]
    assert {"required@1f", "preferred@2f", "desirable@1f"} <= set(labels)
    assert pkg["meta"]["schema_version"] == "0.9"
    assert any(s.startswith("staged_construction") for s in pkg["cost"]["budget"]["suggestions"])
    preferred = next(e for e in pkg["cost"]["options"] if e["label"] == "preferred@1f")
    assert preferred["index"] > 1  # the FAR conflict found in 6.5a, now as an index


def test_apartment_has_no_lot_cost():
    pkg = run_capacity(load_brief("apt_2br_interior"))
    assert "cost" not in pkg


# --------------------------------------------------------------------------------------- tornado


def test_tornado_rows_sorted_and_decisive(reference_package):
    t = reference_package["cost"]["tornado"]
    swings = [r["swing"] for r in t["rows"]]
    assert swings == sorted(swings, reverse=True)
    assert t["quantity"] == "index_b_minus_a" and t["rows"][0]["parameter"] == "form:two_floors"
    assert "form:two_floors" in t["decisive_parameters"]
    assert all(r["parameter"] != "coef:habitable_dry" for r in t["rows"])  # fixed anchor has no swing


def test_tornado_matches_manual_recomputation(catalog, ci, program):
    ref = reference_sheet(catalog, 3000, "ref")
    a, b = sheet_of(catalog, program, label="a"), sheet_of(catalog, program, floors=2, label="b")
    model = get_cost_model("shape")
    t = tornado(model, ci, ref, a, b)
    row = next(r for r in t["rows"] if r["parameter"] == "form:two_floors")
    point = {**mode_point(model, ci), "form:two_floors": ci["form_factors"]["two_floors"]["max"]}
    manual = relative_index(model, b, ref, ci, point) - relative_index(model, a, ref, ci, point)
    assert row["at_high"] == pytest.approx(manual, abs=1e-5)
    assert tornado(get_cost_model("base"), ci, ref, a, b) is None


def test_cli_budget_and_model(capsys):
    from spaceplan.main.cli import main

    brief = ROOT / "data" / "briefs" / "interior_50x100.json"
    assert main(["capacity", str(brief), "--no-corrections", "--budget", "0.8", "--cost-model", "shape"]) == 0
    out = capsys.readouterr().out
    assert "model shape" in out and "fraction 0.8" in out and "tornado" in out
    assert main(["capacity", str(brief), "--no-corrections", "--budget", "lavish"]) == 2
