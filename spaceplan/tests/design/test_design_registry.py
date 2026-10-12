"""Design module (step 6.7a S2.2a): registry, profiles, contract, LLM tools and CLI."""

import copy

import pytest
from jsonschema import Draft202012Validator

from spaceplan.core.lib.contracts import validate_contract
from spaceplan.core.lib_aux.json_io import load_resource_json
from spaceplan.modules.design.lib import design_profile as dp
from spaceplan.modules.design.lib.design_registry import RULESET_PREFIX, load_registry
from spaceplan.modules.design.lib.llm_tools import dispatch, tool_definitions
from spaceplan.modules.design.lib_aux.param_paths import PathError, get_path, set_path
from spaceplan.modules.design.lib_aux.units import convert
from spaceplan.modules.design.main.contract import from_contract, to_contract
from spaceplan.modules.design.main.run_design import BASELINE_PROFILE, load_profile
from spaceplan.pipeline.main.cli import main

DATE = "2026-10-11"


@pytest.fixture(scope="module")
def reg():
    return load_registry()


@pytest.fixture()
def base(reg):
    return dp.new_profile(reg, "test")


# ------------------------------------------------------------------ registry


def test_registry_baseline_is_valid(reg):
    assert reg.self_check() == []
    assert len(reg.params) > 300
    assert {p.origin for p in reg.params.values()} == {"reference", "design"}


def test_every_parameter_is_described(reg):
    for p in reg.params.values():
        assert p.description["es"] and p.description["en"], p.id
        assert p.source, p.id
        assert p.kind in p.kinds_allowed, p.id
        if p.type == "number":
            assert p.range is not None, p.id
        if p.type in ("enum", "list"):
            assert p.choices, p.id


def test_reference_reads_the_store_without_copy(reg):
    cat = reg.stores["catalog"]
    bath = next(s for s in cat["space_types"] if s["space_type"] == "bathroom")
    assert reg.get("space.bathroom.area_target_sqft").value == bath["area"]["target"]
    assert reg.get("weights.floor.shape").value == reg.stores["stacking_catalog"]["s21"]["weights"]["shape"]


def test_code_floors_come_from_the_crc_rulesets(reg):
    f = reg.get("space.bedroom.min_side_ft").floor
    assert (f.rule_id, f.value, f.bound) == ("C01-HABITABLE-DIMENSION", 7.0, "min")
    assert reg.get("circulation.hall.design_width_ft").floor.rule_id == "C06-HALLWAY-WIDTH"
    assert reg.get("light.daylight.glazing_pref_sleeping").floor.rule_id == "C03-GLAZING"
    assert reg.get("space.great_room.through_strip_ft").floor.value == pytest.approx(3.0)


def test_values_below_the_code_floor_are_rejected(reg):
    problems = reg.check_value("space.bedroom.min_side_ft", 6.5)
    assert any("C01-HABITABLE-DIMENSION" in x for x in problems)
    assert reg.check_value("space.bedroom.min_side_ft", 10) == []
    assert any("C06-HALLWAY-WIDTH" in x for x in reg.check_value("circulation.hall.design_width_ft", 2.9))


def test_code_parameters_cannot_change(reg):
    assert "set by code" in reg.check_value("light.category.bedroom", "M")[0]


def test_type_choice_and_kind_checks(reg):
    assert reg.check_value("space.kitchen.template", "island") == []
    assert reg.check_value("space.kitchen.template", "round")
    assert reg.check_value("exits.patio.order", ["kitchen", "kitchen"])
    assert reg.check_value("space.bathroom.aspect_max", 1.8, kind="hard") == []
    assert reg.check_value("space.bathroom.area_min_sqft", 40, kind="soft")


def test_upper_floor_baths_may_be_mechanical(reg):
    assert reg.get("light.category.bathroom__upper").value == "M"
    assert reg.get("light.category.primary_bath__upper").value == "M"
    assert reg.get("light.category.walk_in_closet").value == "M"
    assert reg.get("light.facade.order").value[:2] == ["primary_suite", "bedroom"]


def test_unknown_id_suggests_close_matches(reg):
    with pytest.raises(KeyError, match="did you mean"):
        reg.get("space.bathroom.aspect_maxx")


# ------------------------------------------------------------------ profiles


def test_propose_reports_constraints(reg, base):
    r = dp.propose(reg, base, "space.bathroom.aspect_pref_max", 1.9)
    assert not r["ok"] and any("aspect_max" in x for x in r["problems"])
    assert dp.propose(reg, base, "space.bathroom.aspect_max", 2.0)["ok"]
    r = dp.propose(reg, base, "space.bathroom.area_min_sqft", 60)
    assert not r["ok"] and any("area_target_sqft" in x for x in r["problems"])


def test_apply_writes_a_valid_contract_and_round_trips(reg, base):
    prof = dp.apply(reg, base, [{"id": "space.bathroom.aspect_max", "value": 1.8, "kind": "hard"},
                                {"id": "exits.patio.order", "value": ["kitchen", "dining_room"]}], "javier", DATE,
                    "test")
    assert [c["id"] for c in prof["changes"]] == ["exits.patio.order", "space.bathroom.aspect_max"]
    contract = to_contract(prof)
    validate_contract(contract, "design_profile")
    assert from_contract(contract) == prof
    back = dp.apply(reg, prof, [{"id": "space.bathroom.aspect_max", "value": 1.7, "kind": "hard"}], "javier", DATE)
    assert [c["id"] for c in back["changes"]] == ["exits.patio.order"]


def test_apply_rejects_as_a_whole(reg, base):
    with pytest.raises(dp.ProfileError) as exc:
        dp.apply(reg, base, [{"id": "space.bathroom.aspect_max", "value": 1.8},
                             {"id": "space.bedroom.min_side_ft", "value": 5}], "javier", DATE)
    assert any("C01-HABITABLE-DIMENSION" in x for x in exc.value.problems)


def test_materialize_writes_copies_only(reg, base):
    before = copy.deepcopy(reg.stores)
    prof = dp.apply(reg, base, [{"id": "space.bathroom.aspect_max", "value": 1.8, "kind": "hard"},
                                {"id": "space.bathroom.area_target_sqft", "value": 50}], "javier", DATE)
    stores = dp.materialize(reg, prof)
    obj = get_path(stores[RULESET_PREFIX + "design_space_standards.json"],
                   "rules[rule_id=S04-BATHROOM].parameters.aspect_max")
    assert (obj["value"], obj["kind"]) == (1.8, "hard")
    assert get_path(stores["catalog"], "space_types[space_type=bathroom].area.target") == 50
    assert reg.stores == before
    again = load_registry(stores=stores)
    assert again.get("space.bathroom.aspect_max").value == 1.8


def test_diff_and_snapshot(reg, base):
    prof = dp.apply(reg, base, [{"id": "upper.cantilever_depth_ft", "value": 4.0}], "javier", DATE)
    assert [r["id"] for r in dp.diff(reg, None, prof)] == ["upper.cantilever_depth_ft"]
    snap = {r["id"]: r for r in dp.snapshot(reg, prof)}
    assert snap["upper.cantilever_depth_ft"]["changed"] and snap["upper.cantilever_depth_ft"]["value"] == 4.0
    assert not snap["space.bedroom.min_side_ft"]["changed"]


def test_shipped_baseline_profile(reg):
    contract = load_resource_json("spaceplan", *BASELINE_PROFILE)
    validate_contract(contract, "design_profile")
    prof = load_profile(None)
    assert prof["changes"] == []
    problems, _ = dp.check_profile(reg, prof)
    assert problems == []


# ------------------------------------------------------------------ LLM tools


def test_tool_definitions_are_valid_and_current(reg):
    defs = tool_definitions(reg)
    names = [t["name"] for t in defs["tools"]]
    assert names == ["list_parameters", "explain_parameter", "propose_change", "apply_changes", "diff_profile",
                     "get_criteria", "set_criteria", "run_variant", "compare_variants"]
    for t in defs["tools"]:
        Draft202012Validator.check_schema(t["input_schema"])
    ids = defs["tools"][1]["input_schema"]["properties"]["id"]["enum"]
    assert ids == sorted(reg.params)
    shipped = load_resource_json("spaceplan", "data", "schemas", "design_tools.json")
    assert shipped == defs, "refresh with: spaceplan design tools"


def test_dispatch_runs_the_tools(reg, base):
    res, prof = dispatch(reg, base, "list_parameters", {"prefix": "space.bathroom."}, "llm", DATE)
    assert res["ok"] and all(r["id"].startswith("space.bathroom.") for r in res["parameters"])
    res, prof = dispatch(reg, prof, "propose_change", {"id": "space.bedroom.min_side_ft", "value": 6}, "llm", DATE)
    assert not res["ok"] and res["problems"]
    res, prof = dispatch(reg, prof, "apply_changes", {"changes": [{"id": "space.dining_room.seats", "value": 8}],
                                                      "reason": "bigger family"}, "llm", DATE)
    assert res["ok"] and prof["changes"][0]["id"] == "space.dining_room.seats"
    res, prof2 = dispatch(reg, prof, "apply_changes", {"changes": [{"id": "space.dining_room.seats", "value": 7}],
                                                       "reason": "x"}, "llm", DATE)
    assert not res["ok"] and prof2 is prof
    res, _ = dispatch(reg, prof, "run_variant", {}, "llm", DATE)
    assert res["error"] == "not_available"
    res, _ = dispatch(reg, prof, "diff_profile", {}, "llm", DATE)
    assert [r["id"] for r in res["diff"]] == ["space.dining_room.seats"]


# ------------------------------------------------------------------ helpers and CLI


def test_param_paths_and_units():
    data = {"a": [{"k": "x", "v": {"w": 1}}, {"k": "y.z", "v": {"w": 2}}]}
    assert get_path(data, "a[k=y.z].v.w") == 2
    set_path(data, "a[k=x].v.w", 5)
    assert data["a"][0]["v"]["w"] == 5
    with pytest.raises(PathError):
        get_path(data, "a[k=q].v")
    with pytest.raises(PathError):
        set_path(data, "a[k=x].v.new", 1)
    assert convert(36, "in", "ft") == pytest.approx(3.0)
    assert convert(3.0, "ft", "ft") == 3.0


def test_cli_design_commands(tmp_path, capsys):
    assert main(["design", "check"]) == 0
    assert main(["design", "propose", "space.bedroom.min_side_ft", "6"]) == 2
    out = tmp_path / "p.json"
    assert main(["design", "apply", "--new", "cli", "--set", "space.bathroom.aspect_max=1.8", "--author", "javier",
                 "--date", DATE, "-o", str(out)]) == 0
    assert main(["design", "diff", str(out)]) == 0
    assert "space.bathroom.aspect_max: 1.7 -> 1.8" in capsys.readouterr().out
    assert main(["design", "materialize", "--profile", str(out), "-o", str(tmp_path / "m")]) == 0
    assert (tmp_path / "m" / "rules" / "design_space_standards.json").is_file()
