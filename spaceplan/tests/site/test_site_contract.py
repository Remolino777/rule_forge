"""site module through its contract (refactor tanda 4): site_plan from lotcap's output, without zoning."""

import copy

import pytest
from conftest import assert_close, golden_package, load_brief, load_fixture, normalized

from spaceplan.core.lib.catalog import load_catalog
from spaceplan.core.lib.contracts import ContractValidationError, contract_problems
from spaceplan.modules.lotcap.main.run_lotcap import prepare_lot, select_strategy
from spaceplan.modules.site.main.contract import from_contract, to_contract
from spaceplan.modules.site.main.run_site import plan_site, plan_site_backyard


@pytest.fixture(scope="module")
def produced(rs):
    """Site options of the interior lot; the backyard reads the zoning block of the zoning_scheme fixture."""
    brief, catalog = load_brief("interior_50x100"), load_catalog()
    setup = prepare_lot(brief, rs, catalog)
    strategy, _ = select_strategy(catalog, setup)
    site, warnings = plan_site(rs, catalog, brief, setup, strategy)
    zoning = load_fixture("zoning_scheme", "interior_50x100")["zoning"]
    plan_site_backyard(catalog, rs, brief, setup, site, zoning)
    return to_contract(brief, site, warnings)


def test_module_output_equals_the_fixture(produced):
    """Everything but the backyard is identical; the backyard reads the zoning contract, rounded to the package
    decimals, so its areas and coordinates may move in the last digits (< 0.01 ft or sq ft)."""
    fixture = load_fixture("site_plan", "interior_50x100")
    assert {k: v for k, v in produced.items() if k != "site_partition"} == \
        {k: v for k, v in fixture.items() if k != "site_partition"}
    def strip(site):
        return {**site, "options": [{k: v for k, v in o.items() if k != "backyard"} for o in site["options"]]}

    assert strip(produced["site_partition"]) == strip(fixture["site_partition"])
    assert_close(produced["site_partition"], fixture["site_partition"], 0.01)


def test_fixture_is_the_golden_site_partition():
    for name in ("interior_50x100", "interior_50x100_multigen_latino"):
        site = from_contract(load_fixture("site_plan", name))
        assert normalized(site["site_partition"]) == golden_package(name)["site_partition"]


def test_contract_validates(produced):
    assert contract_problems(produced, "site_plan") == []
    assert produced["produced_by"] == "site"


def test_consumers_accept_the_contract():
    from spaceplan.modules.viz.main.run_viz import package_view

    site = load_fixture("site_plan", "interior_50x100")
    view = package_view(load_fixture("lot_capacity", "interior_50x100"), site)
    assert view["site_partition"] == site["site_partition"]
    assert view["site_partition"]["selected_option_id"] in {o["option_id"] for o in view["site_partition"]["options"]}


def test_wrong_contract_is_rejected():
    lot = copy.deepcopy(load_fixture("lot_capacity", "interior_50x100"))
    with pytest.raises(ContractValidationError):
        from_contract(lot)
