"""profiles module through its contract (refactor tanda 4): program_portfolio of a household without a lot."""

import copy

import pytest
from conftest import load_fixture
from jsonschema import Draft202012Validator

from spaceplan.core.lib.contracts import ContractValidationError, contract_problems
from spaceplan.core.lib.schema_validation import load_schema
from spaceplan.modules.profiles.main.contract import from_contract, to_contract

SOURCE = {"archetype_id": "empty_nest", "cultural_profile": "anglo"}
PROFILES = ("minimum", "optimum", "maximum", "accessible")


@pytest.fixture(scope="module")
def produced():
    from spaceplan.pipeline.main.run_portfolio import run_profiles

    source = dict(SOURCE)
    return to_contract(run_profiles(source), {"source": source, "budget": None, "cost_model": None, "zone": False})


def test_module_output_equals_the_fixture(produced):
    assert produced == load_fixture("program_portfolio", "empty_nest_anglo")


def test_contract_validates(produced):
    assert contract_problems(produced, "program_portfolio") == []
    portfolio = from_contract(produced)
    assert portfolio["reading"] == "reference_dwelling" and portfolio["household"]["archetype_id"] == "empty_nest"


def test_profiles_grow_along_the_curve():
    portfolio = from_contract(load_fixture("program_portfolio", "empty_nest_anglo"))
    areas = [portfolio["profiles"][p]["gross_area_sqft"] for p in ("minimum", "optimum", "maximum")]
    assert areas == sorted(areas)
    assert portfolio["curve"][0]["step"] == 0 or portfolio["curve"][0]["move"]


def test_consumers_accept_the_contract():
    """areas reads the programs of the portfolio (profile_program); each is a valid brief program block."""
    from spaceplan.modules.areas.lib.area_matrix import profile_program

    portfolio = from_contract(load_fixture("program_portfolio", "empty_nest_anglo"))
    brief_schema = load_schema("brief")
    program_schema = {**brief_schema["properties"]["program"], "$defs": brief_schema.get("$defs", {})}
    validator = Draft202012Validator(program_schema)
    for name in (*PROFILES, "staged_final"):
        assert list(validator.iter_errors(profile_program(portfolio["profiles"], name)["program"])) == []


def test_missing_profile_is_rejected():
    bad = copy.deepcopy(load_fixture("program_portfolio", "empty_nest_anglo"))
    del bad["profiles"]["accessible"]
    with pytest.raises(ContractValidationError):
        from_contract(bad)
