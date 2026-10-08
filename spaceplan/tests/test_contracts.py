"""Module contracts (refactor tanda 1): schemas are valid and today's outputs fit them.

Instances are assembled from the golden packages and from run_profiles / run_area_matrix; the
to_contract / from_contract functions of each module arrive in tanda 4.
"""

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from spaceplan.core.lib.schema_validation import (
    CONTRACTS,
    contract_errors,
    contract_registry,
    load_contract_schema,
)
from spaceplan.core.lib_aux.hashing import sha256_of
from spaceplan.core.lib_aux.json_io import load_resource_json

GOLDEN = Path(__file__).resolve().parent / "golden"
ENVELOPE = ("contract", "version", "produced_by", "input_sha256")
PRODUCERS = {"lot_capacity": "lotcap", "site_plan": "site", "program": "household", "cost_report": "cost",
             "program_portfolio": "profiles", "zoning_scheme": "zoning", "area_matrix": "areas"}
HOUSES = ["interior_50x100", "fan_cul_de_sac_35_80x100", "corner_55x100", "hillside_50x100",
          "flag_70x80_pole20", "interior_50x100_multigen_latino"]
APARTMENTS = ["apt_2br_interior"]


@pytest.fixture(scope="module")
def registry():
    return contract_registry()


def _golden(name: str) -> dict:
    return json.loads((GOLDEN / f"package_{name}.json").read_text(encoding="utf-8"))


def _brief(name: str) -> dict:
    return load_resource_json("spaceplan", "data", "briefs", f"{name}.json")


def _envelope(contract: str, inputs) -> dict:
    return {"contract": contract, "version": "0.1.0", "produced_by": PRODUCERS[contract],
            "input_sha256": sha256_of(inputs)}


def _polygon(vertices) -> dict:
    ring = [list(map(float, v)) for v in vertices]
    return {"type": "Polygon", "coordinates": [ring + [ring[0]]]}


@pytest.mark.parametrize("name", CONTRACTS)
def test_contract_schema_is_valid_draft_2020_12(name):
    schema = load_contract_schema(name)
    Draft202012Validator.check_schema(schema)
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert set(ENVELOPE) <= set(schema["required"])
    assert schema["properties"]["contract"] == {"const": name}
    assert schema["properties"]["produced_by"] == {"const": PRODUCERS[name]}


def test_contract_ids_are_unique():
    ids = [load_contract_schema(n)["$id"] for n in CONTRACTS]
    assert len(set(ids)) == len(ids)


@pytest.mark.parametrize("name", HOUSES)
def test_lot_capacity_site_zoning_cost_from_golden_packages(name, registry):
    pkg, brief = _golden(name), _brief(name)
    lot = {"polygon": _polygon(brief["lot"]["vertices"]), "flag": brief["lot"].get("flag")}
    instances = {
        "lot_capacity": {**_envelope("lot_capacity", brief), "lot": lot,
                         **{k: pkg[k] for k in ("scope", "lot_metrics", "boundaries", "rule_variants",
                                                "lot_conformity", "capacity", "realizable_capacity",
                                                "sensitivity", "warnings")}},
        "site_plan": {**_envelope("site_plan", brief), "site_partition": pkg["site_partition"]},
        "zoning_scheme": {**_envelope("zoning_scheme", brief), "zoning": pkg["zoning"], "unit": pkg["unit"],
                          "corrections": pkg["corrections"]},
    }
    if "cost" in pkg:
        instances["cost_report"] = {**_envelope("cost_report", brief), "cost": pkg["cost"]}
    for contract, instance in instances.items():
        assert contract_errors(instance, contract, registry) == [], contract


@pytest.mark.parametrize("name", APARTMENTS)
def test_zoning_scheme_from_apartment(name, registry):
    pkg = _golden(name)
    instance = {**_envelope("zoning_scheme", _brief(name)), "zoning": pkg["zoning"], "unit": pkg["unit"],
                "corrections": pkg["corrections"]}
    assert contract_errors(instance, "zoning_scheme", registry) == []


@pytest.mark.parametrize("name", ["interior_50x100", "interior_50x100_multigen_latino"])
def test_program_contract(name, registry):
    from spaceplan.main.run_household import resolve_brief_household

    brief = _brief(name)
    resolved = resolve_brief_household(brief)[0] if "household" in brief else brief
    pkg = _golden(name)
    instance = {**_envelope("program", brief), "program": resolved["program"],
                "household": pkg.get("household"), "program_review": pkg["program_review"]}
    assert contract_errors(instance, "program", registry) == []


def test_program_portfolio_contract(registry):
    from spaceplan.main.run_profiles import run_profiles

    raw = {"archetype_id": "empty_nest", "cultural_profile": "anglo"}
    portfolio = run_profiles(raw)
    instance = {**_envelope("program_portfolio", raw), **json.loads(json.dumps(portfolio))}
    assert contract_errors(instance, "program_portfolio", registry) == []


def test_area_matrix_contract(registry):
    from spaceplan.main.run_area_matrix import run_area_matrix

    result = run_area_matrix(lots=["interior_50x100"], households=[("empty_nest", "anglo")], measure_site=False,
                             zone_top=0)
    instance = {**_envelope("area_matrix", result["meta"]), **json.loads(json.dumps(result, default=str))}
    assert contract_errors(instance, "area_matrix", registry) == []


def test_contract_rejects_wrong_envelope(registry):
    pkg, brief = _golden("interior_50x100"), _brief("interior_50x100")
    instance = {**_envelope("site_plan", brief), "site_partition": pkg["site_partition"]}
    assert contract_errors({**instance, "produced_by": "zoning"}, "site_plan", registry)
    assert contract_errors({**instance, "input_sha256": "x"}, "site_plan", registry)
    assert contract_errors({k: v for k, v in instance.items() if k != "version"}, "site_plan", registry)
    assert contract_errors({**instance, "extra": 1}, "site_plan", registry)
