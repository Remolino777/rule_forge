"""lotcap module through its contract (refactor tanda 4): lot_capacity without running the pipeline."""

import copy

import pytest
from conftest import golden_package, load_brief, load_fixture, normalized

from spaceplan.core.lib.catalog import load_catalog
from spaceplan.core.lib.contracts import ContractValidationError, contract_problems, read_contract
from spaceplan.modules.lotcap.lib.scope import check_scope
from spaceplan.modules.lotcap.main.contract import from_contract, to_contract
from spaceplan.modules.lotcap.main.run_lotcap import prepare_lot, select_strategy

BLOCKS = ("scope", "lot_metrics", "boundaries", "rule_variants", "lot_conformity", "capacity", "realizable_capacity",
          "sensitivity")


@pytest.fixture(scope="module")
def produced(rs):
    brief, catalog = load_brief("interior_50x100"), load_catalog()
    setup = prepare_lot(brief, rs, catalog)
    strategy, _ = select_strategy(catalog, setup)
    return to_contract(brief, check_scope(brief, rs), setup, strategy)


def test_module_output_equals_the_fixture(produced):
    assert produced == load_fixture("lot_capacity", "interior_50x100")


def test_fixture_blocks_are_the_golden_package_blocks():
    lot, golden = from_contract(load_fixture("lot_capacity", "interior_50x100")), golden_package("interior_50x100")
    assert {k: normalized(lot[k]) for k in BLOCKS} == {k: golden[k] for k in BLOCKS}
    assert lot["realization_strategy"] == golden["meta"]["realization_strategy"]
    assert set(lot["warnings"]) <= set(golden["warnings"])


def test_contract_validates_and_carries_the_envelope(produced):
    assert contract_problems(produced, "lot_capacity") == []
    assert produced["produced_by"] == "lotcap" and produced["brief_id"] == "interior-50x100"
    assert {"site", "zoning", "cost", "viz"} <= set(produced["consumers"])


def test_from_contract_returns_blocks_without_envelope(produced):
    lot = from_contract(produced)
    assert not {"contract", "version", "produced_by", "input_sha256", "consumers"} & set(lot)
    assert lot["lot"]["lot_block"] == load_brief("interior_50x100")["lot"]
    assert lot["lot"]["polygon"]["type"] == "Polygon"


def test_consumers_accept_the_contract():
    """cost (lot reading of the index) and viz (package view) read lot_capacity as it is."""
    from spaceplan.modules.cost.main.contract import cost_from_contracts
    from spaceplan.modules.viz.main.run_viz import package_view

    lot = load_fixture("lot_capacity", "interior_50x100")
    report = cost_from_contracts(load_catalog(), lot, load_fixture("site_plan", "interior_50x100"),
                                 load_fixture("program", "interior_50x100"))
    assert report["cost"]["reference"]["gross_area_sqft"] == pytest.approx(lot["capacity"]["gross_area_max"]["value"])
    assert package_view(lot)["capacity"] == lot["capacity"]


@pytest.mark.parametrize("mutate", [
    lambda c: c.update(produced_by="site"),
    lambda c: c.pop("capacity"),
    lambda c: c.update(input_sha256="nope"),
    lambda c: c["lot"].update(polygon={"type": "Point", "coordinates": [0, 0]}),
])
def test_tampered_contract_is_rejected(mutate):
    bad = copy.deepcopy(load_fixture("lot_capacity", "interior_50x100"))
    mutate(bad)
    with pytest.raises(ContractValidationError):
        read_contract(bad, "lot_capacity")
