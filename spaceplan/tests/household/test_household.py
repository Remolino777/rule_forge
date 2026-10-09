"""Step 6.5a: household model, archetypes, tier programs, trajectory and metamorphic relations MR-H1..MR-H5."""

import copy

import pytest
from conftest import load_brief

from spaceplan.core.lib.catalog import load_catalog
from spaceplan.core.lib.enums import HOUSEHOLD_TIERS as TIERS
from spaceplan.core.lib.schema_validation import BriefValidationError, validate_brief
from spaceplan.core.lib_aux.predicates import (
    evaluate,
    evaluate_number,
    number_errors,
    predicate_errors,
)
from spaceplan.modules.household.lib.household import (
    HouseholdError,
    advance,
    load_household,
    to_raw,
)
from spaceplan.modules.household.lib.household_catalog import (
    household_catalog_errors,
    load_household_catalog,
)
from spaceplan.modules.household.lib.program_builder import expand_typology
from spaceplan.modules.household.main.run_household import resolve_brief_program
from spaceplan.pipeline.main.run_capacity import run_capacity
from spaceplan.pipeline.main.run_household_report import derive_household

ARCHETYPES = ["young_couple", "early_childhood", "teens_family", "multigenerational", "empty_nest",
              "remote_work", "shared_adults"]


@pytest.fixture(scope="module")
def catalog():
    return load_catalog()


@pytest.fixture(scope="module")
def hcat(catalog):
    return load_household_catalog(residential=catalog)


@pytest.fixture(scope="module")
def derived():
    return {a: derive_household({"archetype_id": a}) for a in ARCHETYPES}


def bedrooms_in(program):
    return sum(s["space_type"] in ("bedroom", "primary_suite") for s in program["spaces"])


def comparable(result):
    """Everything that must be invariant, without catalog hashes or ids that legitimately differ."""
    keys = ("composition", "dimensions", "facts", "bedrooms", "needs", "garage_cars", "programs", "relation_hints",
            "quality_weights", "zone_factors")
    return {k: result[k] for k in keys}


# ------------------------------------------------------------------------------------- lib_aux


def test_predicates_evaluate_and_compose():
    facts = {"a": 3, "b": "x"}
    assert evaluate({"always": True}, facts)
    assert evaluate({"all": [{"fact": "a", "op": "ge", "value": 3}, {"fact": "b", "op": "in", "value": ["x", "y"]}]}, facts)
    assert not evaluate({"not": {"any": [{"fact": "a", "op": "lt", "value": 1}, {"fact": "b", "op": "eq", "value": "x"}]}}, facts)
    with pytest.raises(KeyError):
        evaluate({"fact": "missing", "op": "eq", "value": 1}, facts)


def test_numeric_expressions():
    facts = {"n": 5}
    assert evaluate_number(2, facts) == 2
    assert evaluate_number({"fact": "n", "divide_by": 2, "round": "ceil"}, facts) == 3
    assert evaluate_number({"fact": "n", "max": 2}, facts) == 2
    assert evaluate_number({"fact": "n", "multiply": 0, "min": 1}, facts) == 1


def test_expression_structure_errors():
    assert predicate_errors({"fact": "a", "op": "near", "value": 1})
    assert predicate_errors({"all": []})
    assert predicate_errors({"fact": "zz", "op": "eq", "value": 1}, known_facts={"a"})
    assert number_errors({"fact": "a", "divide_by": 0})
    assert number_errors({"fact": "a", "power": 2})
    assert number_errors(True)


# ------------------------------------------------------------------------------------- catalog


def test_household_catalog_loads_with_sources(hcat):
    assert hcat.archetype_ids() == ARCHETYPES
    for rule in hcat.data["rules"]:
        assert hcat.source_of(rule)["status"] in ("verified", "provisional")


@pytest.mark.parametrize("mutation, message", [
    (lambda d: d["rules"][0].update(when={"fact": "nope", "op": "eq", "value": 1}), "unknown fact"),
    (lambda d: d["rules"][0].update(when={"fact": "cultural_profile", "op": "eq", "value": "latino"}),
     "must not read the cultural profile"),
    (lambda d: d["rules"][0]["effects"][0].update(space_type="sauna"), "unknown space type"),
    (lambda d: d["tiers"].reverse(), "tiers must be listed in order"),
    (lambda d: d["age_bands"][1].update(min_years=7), "not contiguous"),
    (lambda d: d["rules"].append(copy.deepcopy(d["rules"][0])), "duplicate rule_id"),
])
def test_invalid_household_catalog_is_rejected(hcat, catalog, mutation, message):
    bad = copy.deepcopy(hcat.data)
    mutation(bad)
    assert any(message in e for e in household_catalog_errors(bad, catalog))


# ------------------------------------------------------------------------------ archetypes / tiers


@pytest.mark.parametrize("archetype", ARCHETYPES)
def test_archetype_programs_are_clean_now_and_next(derived, archetype):
    """7 archetypes x 2 stages x 3 tiers: catalog ranges and CRC habitability minima hold."""
    result = derived[archetype]
    for stage in (result, result["next_stage"]):
        for tier in TIERS:
            review = stage["reviews"][tier]
            assert review["counts"]["error"] == 0, (tier, review["findings"])
            assert review["counts"]["warning"] == 0, (tier, review["findings"])


@pytest.mark.parametrize("archetype", ARCHETYPES)
def test_tiers_are_ordered(derived, archetype):
    stage = derived[archetype]
    nets = [stage["reviews"][t]["net_area_sqft"] for t in TIERS]
    assert nets[0] < nets[1] <= nets[2]
    beds = [bedrooms_in(stage["programs"][t]) for t in TIERS]
    assert beds[0] <= beds[1] <= beds[2]
    for need in stage["needs"]:
        assert all(need["ground_floor_counts"][t] <= need["counts"][t] for t in TIERS)


def test_every_need_traces_to_a_fired_rule(derived):
    for result in derived.values():
        fired = {t["rule_id"] for t in result["rule_trace"]}
        for need in result["needs"]:
            if any(need["counts"].values()):
                assert need["rule_ids"] and set(need["rule_ids"]) <= fired, need


def test_bedroom_grouping_follows_policy(hcat):
    early = derive_household({"archetype_id": "early_childhood"}, next_stage=False)
    assert early["facts"]["bedrooms_required"] == 2 and early["facts"]["bedrooms_preferred"] == 2
    no_share = derive_household({"archetype_id": "early_childhood", "shared_rooms_ok": False}, next_stage=False)
    assert no_share["facts"]["bedrooms_preferred"] == 3 and no_share["facts"]["bedrooms_required"] == 2
    multi = derive_household({"archetype_id": "multigenerational"}, next_stage=False)
    roles = [r["role"] for r in multi["bedrooms"]["required"]]
    assert sorted(roles) == ["accessible", "child", "primary"]
    accessible = [s for s in multi["programs"]["required"]["spaces"] if s["household_role"] == "accessible"]
    assert {s["space_type"] for s in accessible} == {"bedroom", "bathroom"}
    assert all(s["floor_preference"] == 0 for s in accessible)
    hint = multi["relation_hints"]["required"][0]
    assert (hint["a"], hint["b"], hint["relation"]) == ("bedroom:accessible", "bathroom:accessible", "en_suite")


def test_work_and_garage_rules(derived):
    couple = derived["young_couple"]
    types = {t: {s["space_id"] for s in couple["programs"][t]["spaces"]} for t in TIERS}
    assert "flex_room_work" in types["required"] and "study_work" in types["preferred"]
    assert couple["garage_cars"] == {"required": 1, "preferred": 2, "desirable": 2}
    teens = derived["teens_family"]
    assert teens["driveway_vehicles"]["preferred"] == 1  # 3 vehicles, garage capped at 2


def test_trajectory_events(derived):
    couple = derived["young_couple"]["next_stage"]
    assert [e["event"] for e in couple["events_applied"]] == ["child_expected"]
    assert couple["composition"]["child_0_5"] == 1
    assert any(c["space_type"] == "bedroom" and c["household_role"] == "child" and c["change"] == 1
               for c in couple["growth_delta"]["changes"])
    assert any("convertible" in n for n in couple["growth_delta"]["notes"])
    nest = derived["empty_nest"]["next_stage"]["growth_delta"]
    assert any(c["space_type"] == "primary_bath" and c["tier"] == "required" and c["ground_next"] == 1
               for c in nest["changes"])
    teens = derived["teens_family"]["next_stage"]
    assert teens["composition"]["teen_13_18"] == 0 and teens["composition"]["adult"] == 3


def test_expansion_of_typologies_is_unchanged(catalog):
    program = expand_typology(catalog, "t3_standard", 2)
    assert all("household_role" not in s for s in program["spaces"])


# -------------------------------------------------------------------------- metamorphic relations


ADDITIONS = [{"member_id": "x_child", "age_years": 3}, {"member_id": "x_teen", "age_years": 15},
             {"member_id": "x_senior", "age_years": 80, "mobility": "reduced"}, {"member_id": "x_adult", "age_years": 40}]


@pytest.mark.parametrize("archetype", ARCHETYPES)
@pytest.mark.parametrize("extra", ADDITIONS, ids=lambda m: m["member_id"])
def test_mr_h1_adding_a_member_never_reduces_the_minimum(hcat, derived, archetype, extra):
    base = derived[archetype]
    raw = to_raw(load_household({"archetype_id": archetype}, hcat))
    raw["members"].append(extra)
    more = derive_household(raw, next_stage=False)
    assert more["facts"]["bedrooms_required"] >= base["facts"]["bedrooms_required"]
    assert more["reviews"]["required"]["net_area_sqft"] >= base["reviews"]["required"]["net_area_sqft"]
    assert more["reviews"]["preferred"]["net_area_sqft"] >= base["reviews"]["preferred"]["net_area_sqft"] - 1e-9


@pytest.mark.parametrize("archetype", ARCHETYPES)
def test_mr_h2_member_order_is_irrelevant(hcat, derived, archetype):
    raw = to_raw(load_household({"archetype_id": archetype}, hcat))
    raw["members"].reverse()
    assert comparable(derive_household(raw, next_stage=False)) == comparable(derived[archetype])


@pytest.mark.parametrize("archetype", ARCHETYPES)
def test_mr_h3_preset_equals_manual_entry(hcat, derived, archetype):
    manual = derive_household(to_raw(load_household({"archetype_id": archetype}, hcat)))
    assert comparable(manual) == comparable(derived[archetype])
    assert comparable(manual["next_stage"]) == comparable(derived[archetype]["next_stage"])


@pytest.mark.parametrize("profile", ["latino", "anglo", "mixed", "custom"])
def test_mr_h4_cultural_profile_does_not_touch_the_household_layer(derived, profile):
    """The household layer is identical under any profile; only culture-layer rules may differ (6.5c)."""
    result = derive_household({"archetype_id": "multigenerational", "cultural_profile": profile}, next_stage=False)

    def household_layer(r):
        return [t for t in r["rule_trace"] if t["layer"] == "household"]

    assert household_layer(result) == household_layer(derived["multigenerational"])
    assert result["bedrooms"] == derived["multigenerational"]["bedrooms"]
    if profile in ("mixed", "custom"):  # presets without aspects: neutral
        assert comparable(result) == comparable(derived["multigenerational"])
    assert "cultural_profile" not in result["dimensions"]  # privacy: not echoed unless include_household


@pytest.mark.parametrize("archetype", ARCHETYPES)
def test_mr_h5_next_stage_equals_manual_aging(hcat, derived, archetype):
    household = load_household({"archetype_id": archetype}, hcat)
    later, _ = advance(household, household.horizon_years, hcat)
    manual = derive_household(to_raw(later), next_stage=False)
    expected = derived[archetype]["next_stage"]
    assert comparable(manual) == comparable(expected)


# -------------------------------------------------------------------- ethics, validation, privacy


def test_fair_housing_large_household_still_gets_a_program():
    members = [{"member_id": f"a{i}", "age_years": 30 + i} for i in range(4)]
    members += [{"member_id": f"c{i}", "age_years": i} for i in range(6)]
    result = derive_household({"members": members}, next_stage=False)
    for tier in TIERS:
        assert result["reviews"][tier]["buildable_as_stated"]
    text = repr({k: v for k, v in result.items() if k != "privacy"}).lower()
    assert "occupan" not in text.replace("occupants", "") and "too many" not in text
    assert result["facts"]["bedrooms_preferred"] == 7  # 4 own rooms + 6 young children sharing in pairs


@pytest.mark.parametrize("raw, message", [
    ({"members": [{"member_id": "a", "age_years": 30, "partner_id": "b"}, {"member_id": "b", "age_years": 30}]},
     "not mutual"),
    ({"members": [{"member_id": "a", "age_years": 30, "partner_id": "b"},
                  {"member_id": "b", "age_years": 15, "partner_id": "a"}]}, "between adults"),
    ({"members": [{"member_id": "a", "age_years": 30}, {"member_id": "a", "age_years": 31}]}, "duplicate member_id"),
    ({"members": [{"member_id": "a", "age_years": 30}],
      "trajectory": {"events": [{"event": "member_leaves", "in_years": 1, "member_id": "z"}]}}, "current member"),
    ({"archetype_id": "astronauts"}, "unknown archetype"),
    ({"members": [{"member_id": "a", "age_years": -1}]}, "minimum"),
    ({}, "members are required"),
])
def test_invalid_households_are_rejected(hcat, raw, message):
    with pytest.raises(HouseholdError) as exc:
        load_household(raw, hcat)
    assert any(message in e for e in exc.value.errors), exc.value.errors


def test_privacy_members_only_on_request():
    hidden = derive_household({"archetype_id": "young_couple"}, next_stage=False)
    shown = derive_household({"archetype_id": "young_couple", "include_household": True, "cultural_profile": "mixed"},
                             next_stage=False)
    assert "members" not in hidden and "cultural_profile" not in hidden["facts"]
    assert len(shown["members"]) == 2 and shown["dimensions"]["cultural_profile"] == "mixed"


def test_apartment_household_has_no_garage():
    result = derive_household({"archetype_id": "young_couple"}, dwelling_type="apartment", next_stage=False)
    assert all(p["garage_cars"] == 0 for p in result["programs"].values())
    assert result["driveway_vehicles"]["preferred"] == 2


# --------------------------------------------------------------------------------- brief integration


def test_household_only_brief_derives_its_program():
    brief = load_brief("interior_50x100_multigen")
    with pytest.raises(BriefValidationError, match="derive it first"):
        validate_brief(brief)
    resolved, block = resolve_brief_program(brief)
    validate_brief(resolved)
    assert block["program_source"] == "derived" and block["program_tier"] == "preferred"
    package = run_capacity(brief, corrections=False)
    assert package["meta"]["schema_version"] == "0.9"
    assert package["household"]["composition"]["senior"] == 1 and "members" not in package["household"]
    assert package["program_review"]["buildable_as_stated"]


def test_brief_program_wins_and_is_compared():
    brief = load_brief("interior_50x100")
    brief["household"] = {"archetype_id": "early_childhood"}
    resolved, block = resolve_brief_program(brief)
    assert resolved["program"] == brief["program"] and block["program_source"] == "brief"
    comparison = block["program_comparison"]
    assert comparison["derived_bedrooms"] == 2 and comparison["brief_bedrooms"] >= 1


def test_briefs_without_household_are_untouched():
    brief = load_brief("corner_55x100")
    resolved, block = resolve_brief_program(brief)
    assert resolved is brief and block is None


def test_cli_household_and_rules_table(tmp_path, capsys, hcat):
    from spaceplan.pipeline.main.cli import main

    assert main(["household", "--list"]) == 0
    assert "multigenerational" in capsys.readouterr().out
    assert main(["household", "empty_nest", "--tier", "required"]) == 0
    assert "primary_bath" in capsys.readouterr().out
    out = tmp_path / "rules.md"
    assert main(["household", "--rules-markdown", str(out)]) == 0
    table = out.read_text()
    assert all(f"| {r['rule_id']} |" in table for r in hcat.data["rules"])
    assert main(["household", "astronauts"]) == 2
