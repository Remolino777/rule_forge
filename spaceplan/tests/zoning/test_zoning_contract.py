"""zoning module through its contract (refactor tanda 4): zoning_scheme of an apartment (unit only) and checks of
the house fixture, without running the pipeline."""

import pytest
from conftest import golden_package, load_brief, load_fixture, normalized

from spaceplan.core.lib.catalog import load_catalog
from spaceplan.core.lib.contracts import ContractValidationError, contract_problems
from spaceplan.core.lib.enums import Strategy
from spaceplan.modules.zoning.main.contract import from_contract, to_contract
from spaceplan.modules.zoning.main.run_zoning import unit_record, zone_apartment

BLOCKS = ("zoning", "unit", "corrections")


@pytest.fixture(scope="module")
def apartment():
    brief = load_brief("apt_2br_interior")
    unit, zoning = zone_apartment(brief, load_catalog())
    net = load_fixture("program", "apt_2br_interior")["program_review"]["summary"]["net_area_sqft"]
    return to_contract(brief, zoning, unit_record(unit, net), None, Strategy.A_INSCRIBED_RECTANGLE.value)


def test_apartment_output_equals_the_fixture(apartment):
    assert apartment == load_fixture("zoning_scheme", "apt_2br_interior")


@pytest.mark.parametrize("name", ["apt_2br_interior", "interior_50x100", "interior_50x100_multigen_latino"])
def test_fixture_blocks_are_the_golden_package_blocks(name):
    zoning, golden = from_contract(load_fixture("zoning_scheme", name)), golden_package(name)
    assert {k: normalized(zoning[k]) for k in BLOCKS} == {k: golden[k] for k in BLOCKS}
    assert zoning["dwelling_type"] == golden["meta"]["dwelling_type"]
    assert zoning["realization_strategy"] == golden["meta"]["realization_strategy"]


def test_house_zoning_names_the_selected_strategy():
    zoning = from_contract(load_fixture("zoning_scheme", "interior_50x100"))
    assert zoning["zoning"]["selection"]["strategy"] == zoning["realization_strategy"]
    assert zoning["unit"] is None and any(o["status"] == "zoned" for o in zoning["zoning"]["options"])


def test_contract_validates_and_rejects_a_bad_dwelling_type(apartment):
    assert contract_problems(apartment, "zoning_scheme") == []
    with pytest.raises(ContractValidationError):
        from_contract({**apartment, "dwelling_type": "castle"})


def test_consumers_accept_the_contract():
    """viz reads the zoning block and the apartment unit outline from the contract."""
    from spaceplan.modules.viz.main.run_viz import package_view

    view = package_view(zoning_scheme=load_fixture("zoning_scheme", "apt_2br_interior"))
    assert view["meta"]["dwelling_type"] == "apartment" and view["unit"]["polygon"]["type"] == "Polygon"
