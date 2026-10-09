"""household module through its contract (refactor tanda 4): program, without planning the lot."""

import pytest
from conftest import golden_package, load_brief, load_fixture, normalized

from spaceplan.core.lib.catalog import load_catalog
from spaceplan.core.lib.contracts import contract_problems
from spaceplan.core.lib.rules import CRC_RULESET, load_ruleset_resource
from spaceplan.modules.household.lib.program_review import review_program
from spaceplan.modules.household.main.contract import from_contract, to_contract
from spaceplan.modules.household.main.run_household import resolve_brief_household

SUBJECTS = ["interior_50x100", "interior_50x100_multigen_latino", "apt_2br_interior"]


def _produce(name: str) -> dict:
    brief, household, _ = resolve_brief_household(load_brief(name))
    review = review_program(load_catalog(), load_ruleset_resource(*CRC_RULESET), brief["program"])
    return to_contract(brief, review, household)


@pytest.mark.parametrize("name", SUBJECTS)
def test_module_output_equals_the_fixture(name):
    assert _produce(name) == load_fixture("program", name)


@pytest.mark.parametrize("name", SUBJECTS)
def test_fixture_blocks_are_the_golden_package_blocks(name):
    program, golden = from_contract(load_fixture("program", name)), golden_package(name)
    assert normalized(program["program_review"]) == golden["program_review"]
    assert normalized(program["household"]) == golden.get("household")


def test_derived_program_is_carried_with_the_privacy_minimized_household():
    program = from_contract(load_fixture("program", "interior_50x100_multigen_latino"))
    assert program["household"]["archetype_id"] == "multigenerational"
    assert program["program"]["spaces"] and contract_problems(load_fixture("program", "interior_50x100_multigen_latino"),
                                                              "program") == []
    assert from_contract(load_fixture("program", "interior_50x100"))["household"] is None


def test_consumers_accept_the_contract():
    """cost reads the program to build the quantity sheets of the site options."""
    from spaceplan.modules.cost.main.contract import cost_from_contracts

    report = cost_from_contracts(load_catalog(), load_fixture("lot_capacity", "interior_50x100"),
                                 load_fixture("site_plan", "interior_50x100"), load_fixture("program", "interior_50x100"))
    assert report is not None and report["cost"]["options"]
