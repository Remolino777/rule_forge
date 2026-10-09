"""The pipeline chains contracts (refactor tanda 4): the package is assembled from the module contracts, and the
per-module commands read and write them."""

import json
from pathlib import Path

import pytest
from conftest import golden_package, load_brief, load_fixture, normalized

from spaceplan.core.lib.contracts import contract_problems
from spaceplan.core.lib.rules import load_ruleset
from spaceplan.pipeline.lib.package import package_from_contracts
from spaceplan.pipeline.main.cli import main
from spaceplan.pipeline.main.run_capacity import run_capacity_contracts

BRIEFS = Path(__file__).resolve().parents[2] / "spaceplan" / "data" / "briefs"
VOLATILE = ("package_id", "generator")


def _strip(package: dict) -> dict:
    package = normalized(package)
    for key in VOLATILE:
        package["meta"].pop(key, None)
    return package


def test_package_from_fixtures_equals_the_golden_package():
    """No module runs: the package of the interior lot is assembled from its five contract fixtures."""
    name = "interior_50x100"
    lot = load_fixture("lot_capacity", name)
    package = package_from_contracts(load_brief(name), load_ruleset(), lot["scope"], load_fixture("program", name),
                                     lot["realization_strategy"], lot, load_fixture("site_plan", name),
                                     load_fixture("zoning_scheme", name))
    package["cost"] = load_fixture("cost_report", name)["cost"]
    assert _strip(package) == golden_package(name)


@pytest.mark.parametrize("name", ["apt_2br_interior", "interior_50x100"])
def test_pipeline_contracts_equal_the_fixtures(name):
    package, contracts = run_capacity_contracts(load_brief(name))
    assert _strip(package) == golden_package(name)
    expected = {"program", "zoning_scheme"} | ({"lot_capacity", "site_plan", "cost_report"} if name != "apt_2br_interior"
                                              else set())
    assert set(contracts) == expected
    for contract, instance in contracts.items():
        assert contract_problems(instance, contract) == []
        assert instance == load_fixture(contract, name), contract


def test_out_of_scope_house_has_only_a_program_contract():
    brief = load_brief("interior_50x100")
    brief["overlays"] = {**brief.get("overlays", {}), "coastal": True}
    package, contracts = run_capacity_contracts(brief)
    if package["scope"]["in_scope"]:
        pytest.skip("overlay does not take this brief out of scope")
    assert set(contracts) == {"program"} and package["capacity"] is None


def test_cli_module_commands_read_and_write_contracts(tmp_path, capsys):
    """household -> program; cost reads three contracts; viz draws from them; zoning writes an apartment."""
    prog = tmp_path / "program.json"
    assert main(["household", f"{BRIEFS}/interior_50x100.json", "--contract", str(prog)]) == 0
    assert json.loads(prog.read_text()) == load_fixture("program", "interior_50x100")
    paths = {}
    for contract in ("lot_capacity", "site_plan", "zoning_scheme"):
        paths[contract] = tmp_path / f"{contract}.json"
        paths[contract].write_text(json.dumps(load_fixture(contract, "interior_50x100")))
    cost = tmp_path / "cost.json"
    assert main(["cost", "--lot-capacity", str(paths["lot_capacity"]), "--site-plan", str(paths["site_plan"]),
                 "--program", str(prog), "-o", str(cost)]) == 0
    assert json.loads(cost.read_text()) == load_fixture("cost_report", "interior_50x100")
    png = tmp_path / "zoning.png"
    assert main(["viz", "--lot-capacity", str(paths["lot_capacity"]), "--site-plan", str(paths["site_plan"]),
                 "--zoning-scheme", str(paths["zoning_scheme"]), "--zoning-plot", str(png)]) == 0
    assert png.stat().st_size > 10_000
    apt = tmp_path / "apt_zoning.json"
    assert main(["zoning", f"{BRIEFS}/apt_2br_interior.json", "-o", str(apt)]) == 0
    assert json.loads(apt.read_text()) == load_fixture("zoning_scheme", "apt_2br_interior")
    assert main(["lotcap", f"{BRIEFS}/apt_2br_interior.json"]) == 2  # apartments have no lot_capacity
    assert "contract    zoning_scheme" in capsys.readouterr().out


def test_cli_rejects_a_contract_of_the_wrong_kind(tmp_path, capsys):
    site = tmp_path / "site.json"
    site.write_text(json.dumps(load_fixture("site_plan", "interior_50x100")))
    assert main(["cost", "--lot-capacity", str(site), "--site-plan", str(site), "--program", str(site)]) == 2
    assert "lot_capacity" in capsys.readouterr().err


def test_capacity_command_writes_every_contract(tmp_path):
    out = tmp_path / "contracts"
    assert main(["capacity", f"{BRIEFS}/apt_2br_interior.json", "--contracts", str(out)]) == 0
    assert {p.stem for p in out.glob("*.json")} == {"program", "zoning_scheme"}
