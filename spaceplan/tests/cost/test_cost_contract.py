"""cost module through its contract (refactor tanda 4): cost_report from the lot_capacity, site_plan and program
contracts only (no lot, site or zoning computation)."""

import copy

import pytest
from conftest import golden_package, load_brief, load_fixture, normalized

from spaceplan.core.lib.catalog import load_catalog
from spaceplan.core.lib.contracts import ContractValidationError, contract_problems
from spaceplan.modules.cost.main.contract import cost_from_contracts, from_contract
from spaceplan.modules.household.main.run_household import resolve_brief_household

SUBJECTS = ["interior_50x100", "interior_50x100_multigen_latino"]


def _produce(name: str) -> dict:
    brief = load_brief(name)
    _, _, tiers = resolve_brief_household(brief)
    return cost_from_contracts(load_catalog(), load_fixture("lot_capacity", name), load_fixture("site_plan", name),
                               load_fixture("program", name), tiers, None, brief.get("budget"))


@pytest.mark.parametrize("name", SUBJECTS)
def test_module_output_equals_the_fixture(name):
    assert _produce(name) == load_fixture("cost_report", name)


@pytest.mark.parametrize("name", SUBJECTS)
def test_fixture_is_the_golden_cost_block(name):
    assert normalized(from_contract(load_fixture("cost_report", name))["cost"]) == golden_package(name)["cost"]


def test_input_hash_chains_the_upstream_contracts():
    a = _produce("interior_50x100")
    lot = copy.deepcopy(load_fixture("lot_capacity", "interior_50x100"))
    lot["input_sha256"] = "0" * 64
    b = cost_from_contracts(load_catalog(), lot, load_fixture("site_plan", "interior_50x100"),
                            load_fixture("program", "interior_50x100"))
    assert a["cost"] == b["cost"] and a["input_sha256"] != b["input_sha256"]
    assert contract_problems(a, "cost_report") == []


def test_no_lot_maximum_gives_no_report():
    lot = copy.deepcopy(load_fixture("lot_capacity", "interior_50x100"))
    lot["capacity"]["gross_area_max"]["value"] = None
    assert cost_from_contracts(load_catalog(), lot, load_fixture("site_plan", "interior_50x100"),
                               load_fixture("program", "interior_50x100")) is None


def test_inputs_must_be_the_right_contracts():
    site = load_fixture("site_plan", "interior_50x100")
    with pytest.raises(ContractValidationError):
        cost_from_contracts(load_catalog(), site, site, load_fixture("program", "interior_50x100"))


def test_budget_changes_the_assessment_not_the_index():
    base = from_contract(_produce("interior_50x100"))["cost"]
    tight = cost_from_contracts(load_catalog(), load_fixture("lot_capacity", "interior_50x100"),
                                load_fixture("site_plan", "interior_50x100"), load_fixture("program", "interior_50x100"),
                                budget={"level": "tight"})
    assert [o["index"] for o in tight["cost"]["options"]] == [o["index"] for o in base["options"]]
    assert tight["cost"]["budget"] != base["budget"]
