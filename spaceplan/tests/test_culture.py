"""Step 6.5c: cultural layer (aspects, presets, kitchen typologies, culture rules) and MR-K1..MR-K5."""

import copy
import json
from collections import Counter

import pytest

from conftest import load_brief
from spaceplan.lib.catalog import load_catalog
from spaceplan.lib.culture import merge_culture_into_brief
from spaceplan.lib.enums import CULTURE_ASPECTS, CULTURE_FACTS, HOUSEHOLD_TIERS as TIERS
from spaceplan.lib.household import load_household, to_raw
from spaceplan.lib.household_catalog import household_catalog_errors, load_household_catalog
from spaceplan.lib.schema_validation import load_schema
from spaceplan.main.run_capacity import run_capacity
from spaceplan.main.run_household import derive_household, resolve_brief_household

ARCHETYPES = ["young_couple", "early_childhood", "teens_family", "multigenerational", "empty_nest",
              "remote_work", "shared_adults"]
PROFILES = ["latino", "anglo"]


@pytest.fixture(scope="module")
def catalog():
    return load_catalog()


@pytest.fixture(scope="module")
def hcat(catalog):
    return load_household_catalog(residential=catalog)


@pytest.fixture(scope="module")
def runs():
    return {(a, p): derive_household({"archetype_id": a, **({"cultural_profile": p} if p else {})}, next_stage=False)
            for a in ARCHETYPES for p in (None, *PROFILES)}


def space_types(program):
    return Counter(s["space_type"] for s in program["spaces"])


def comparable(r):
    return {k: r[k] for k in ("needs", "programs", "facts", "relation_hints", "quality_weights", "culture")
            if k != "facts"} | {"culture": {k: v for k, v in r["culture"].items() if k != "aspects"}}


# ------------------------------------------------------------------------------------------ catalog


@pytest.mark.parametrize("mutation, message", [
    (lambda d: d["culture_presets"][0]["aspects"].update(patio_use="pool_party"), "not an allowed value"),
    (lambda d: d["culture_aspects"].pop(), "culture_aspects must list exactly"),
    (lambda d: d["kitchen_typology_selection"].append({"when": {"always": True}, "typology": "open_island"})
     or d["kitchen_typologies"].pop(), "unknown typology"),
    (lambda d: d["rules"][0].update(when={"fact": "patio_use", "op": "eq", "value": "gathering"}),
     "must not read the cultural profile or aspects"),
    (lambda d: next(r for r in d["rules"] if r["rule_id"] == "C06-SERVICE-YARD")["effects"][0].update(a="sauna"),
     "unknown matrix role"),
    (lambda d: d["rules"][0]["effects"].append({"effect": "anchor_override", "anchor_id": "kitchen_faces_rear",
                                                "mode": "hard", "tiers": ["required"]}), "belongs to the culture layer"),
    (lambda d: d["kitchen_typologies"][2]["effects"][1].update(anchor_id="pool_faces_moon"), "unknown zoning anchor"),
])
def test_invalid_culture_catalog_is_rejected(hcat, catalog, mutation, message):
    bad = copy.deepcopy(hcat.data)
    mutation(bad)
    assert any(message in e for e in household_catalog_errors(bad, catalog)), household_catalog_errors(bad, catalog)


def test_ethics_no_identity_facts():
    """Culture is a set of explicit preferences: no fact or input field about name, origin, language or ethnicity."""
    forbidden = {"name", "origin", "language", "ethnicity", "nationality", "race", "religion", "surname"}
    assert not forbidden & set(CULTURE_FACTS)
    assert not forbidden & set(load_schema("household")["properties"])
    member = load_schema("household")["properties"]["members"]["items"]["properties"]
    assert not forbidden & set(member)


# ------------------------------------------------------------------------------- MR-K1 .. MR-K5


@pytest.mark.parametrize("archetype", ARCHETYPES)
def test_mr_k1_no_profile_is_neutral(runs, archetype):
    r = runs[(archetype, None)]
    assert r["culture"]["applied"] is False and r["culture"]["kitchen_typology"] == "none"
    assert all(t["layer"] == "household" for t in r["rule_trace"])
    assert all(not r["culture"][k][t] for k in ("relation_overrides", "anchor_overrides") for t in TIERS)


@pytest.mark.parametrize("profile", PROFILES)
@pytest.mark.parametrize("archetype", ["multigenerational", "teens_family"])
def test_mr_k2_preset_equals_manual_aspects(hcat, runs, archetype, profile):
    raw = to_raw(load_household({"archetype_id": archetype}, hcat))
    raw["cultural_profile"] = None
    raw["culture_aspects"] = hcat.preset(profile)
    manual = derive_household(raw, next_stage=False)
    assert comparable(manual) == comparable(runs[(archetype, profile)])


@pytest.mark.parametrize("profile", PROFILES)
@pytest.mark.parametrize("archetype", ARCHETYPES)
def test_mr_k3_culture_never_removes_required_spaces(runs, archetype, profile):
    neutral, cultured = runs[(archetype, None)], runs[(archetype, profile)]
    for tier in TIERS:
        missing = space_types(neutral["programs"][tier]) - space_types(cultured["programs"][tier])
        assert not missing, (tier, missing)
    for tier in TIERS:
        review = cultured["reviews"][tier]
        assert review["counts"]["error"] == 0 and review["counts"]["warning"] == 0, review["findings"]


@pytest.mark.parametrize("profile", PROFILES)
@pytest.mark.parametrize("archetype", ARCHETYPES)
def test_mr_k4_every_difference_traces_to_culture(runs, archetype, profile):
    neutral = {(n["space_type"], n["household_role"]): n for n in runs[(archetype, None)]["needs"]}
    culture_rules = set(runs[(archetype, profile)]["culture"]["rule_ids"])
    for n in runs[(archetype, profile)]["needs"]:
        before = neutral.get((n["space_type"], n["household_role"]))
        if before is None or before["counts"] != n["counts"]:
            assert set(n["rule_ids"]) & culture_rules, n


def test_mr_k5_brief_overrides_win():
    tier_culture = {
        "relation_overrides": [{"a": "living", "b": "kitchen", "type": "D", "kind": "soft", "weight": 1.0, "rule_id": "X"}],
        "anchor_overrides": {"kitchen_faces_rear": {"mode": "hard", "rule_id": "Y"}},
        "backyard": {"elements": {"pool": {"priority": 1, "rule_id": "Z", "add": False},
                                  "covered_terrace": {"priority": 1, "rule_id": "Z", "add": True}},
                     "min_green_fraction": {"value": 0.5, "rule_id": "Z"}}}
    brief = {"relation_overrides": [{"a": "kitchen", "b": "living", "type": "I"}],
             "zoning_overrides": {"anchors": {"kitchen_faces_rear": "off"}},
             "backyard_program": {"min_green_fraction": 0.4, "elements": [{"element": "pool", "priority": 3}]}}
    merged, record = merge_culture_into_brief(brief, tier_culture)
    assert merged["relation_overrides"] == brief["relation_overrides"]
    assert merged["zoning_overrides"]["anchors"]["kitchen_faces_rear"] == "off"
    assert merged["backyard_program"]["min_green_fraction"] == 0.4
    assert {"element": "pool", "priority": 3} in merged["backyard_program"]["elements"]
    assert {"element": "covered_terrace", "priority": 1} in merged["backyard_program"]["elements"]
    assert {o["kind"] for o in record["overridden_by_brief"]} == {"relation", "anchor", "backyard_priority",
                                                                  "backyard_green"}


# --------------------------------------------------------------------------------- behaviour


def test_two_profiles_same_household_differ(runs):
    lat, ang = runs[("multigenerational", "latino")], runs[("multigenerational", "anglo")]
    assert lat["culture"]["kitchen_typology"] == "semi_open_separable"
    assert ang["culture"]["kitchen_typology"] == "double_kitchen"  # open + intensive cooking
    assert "work_kitchen" in space_types(ang["programs"]["preferred"])
    assert "mudroom" in space_types(ang["programs"]["preferred"])
    rel = {(o["a"], o["b"]): o["type"] for o in lat["culture"]["relation_overrides"]["preferred"]}
    assert rel[("living", "kitchen")] == "I" and rel[("kitchen", "laundry")] == "D"
    rel = {(o["a"], o["b"]): o["type"] for o in ang["culture"]["relation_overrides"]["preferred"]}
    assert rel[("living", "kitchen")] == "D" and rel[("kitchen", "laundry")] == "I"
    dining = {r: next(s for s in x["programs"]["preferred"]["spaces"] if s["space_type"] == "dining_room")
              for r, x in (("lat", lat), ("ang", ang))}
    assert dining["lat"]["target_area_sqft"] > dining["ang"]["target_area_sqft"]


@pytest.mark.parametrize("aspects, typology", [
    ({"kitchen_living_relation": "closed"}, "closed_ventilated"),
    ({"kitchen_living_relation": "open"}, "open_island"),
    ({"social_center": "kitchen_island"}, "open_island"),
    ({"ventilation_priority": "high"}, "semi_open_separable"),
    ({"patio_use": "lawn_play"}, "none"),
])
def test_kitchen_typology_selection(aspects, typology):
    r = derive_household({"archetype_id": "young_couple", "culture_aspects": aspects}, next_stage=False)
    assert r["culture"]["kitchen_typology"] == typology


def test_explicit_typology_wins_and_mixed_profile_takes_aspects():
    r = derive_household({"archetype_id": "young_couple", "cultural_profile": "latino",
                          "kitchen_typology": "open_island"}, next_stage=False)
    assert r["culture"]["kitchen_typology"] == "open_island"
    mixed = derive_household({"archetype_id": "young_couple", "cultural_profile": "mixed",
                              "culture_aspects": {"dining_capacity": "extended_family", "entry_sequence":
                                                  "garage_mudroom_kitchen"}}, next_stage=False)
    assert {"C01-DINING-EXTENDED", "C09-MUDROOM-SEQUENCE"} <= set(mixed["culture"]["rule_ids"])


@pytest.mark.parametrize("profile", PROFILES)
def test_brief_with_profile_runs_end_to_end(profile):
    brief = load_brief("interior_50x100_multigen")
    brief["household"].update(cultural_profile=profile, program_tier="required")
    resolved, block, _ = resolve_brief_household(brief)
    assert block["culture"]["applied"] and "profile" not in block["culture"]  # privacy
    pkg = run_capacity(brief, corrections=False)
    placed = {e["element"] for e in pkg["site_partition"]["options"][0]["backyard"]["elements"] if e["status"] == "placed"}
    if profile == "latino":
        assert {"covered_terrace", "outdoor_kitchen"} <= placed
        assert pkg["cost"]["options"][0]["quantities"]["exterior_by_class"]["backyard"]["basis"] == "measured"
    else:
        assert "pool" in placed and resolved["backyard_program"]["min_green_fraction"] == 0.5
    json.dumps(pkg)


def test_cli_culture_flag(capsys):
    from spaceplan.main.cli import main

    assert main(["household", "multigenerational", "--culture", "anglo", "--no-next"]) == 0
    out = capsys.readouterr().out
    assert "kitchen double_kitchen" in out and "C09-MUDROOM-SEQUENCE" in out
    assert main(["household", "multigenerational", "--no-next"]) == 0
    assert "culture     none" in capsys.readouterr().out
