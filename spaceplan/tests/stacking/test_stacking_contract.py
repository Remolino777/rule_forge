"""stacking module through its contract (step 6.7a): stack_plan of one lot and one household from the area_matrix
and lot_capacity fixtures, the stacking catalog, cell selection and the CLI."""

import copy
import json

import pytest
from conftest import load_fixture

from spaceplan.core.lib.contracts import ContractValidationError, contract_problems
from spaceplan.modules.stacking.lib.cell_selection import select_cells, selection_label
from spaceplan.modules.stacking.lib.stacking_catalog import (
    StackingCatalogError,
    check_stacking_catalog,
    load_stacking_catalog,
)
from spaceplan.modules.stacking.main.contract import from_contract, to_contract
from spaceplan.modules.stacking.main.run_stacking import (
    TABLE_FIELDS,
    run_stacking,
    table_rows,
    write_tables,
)

SUBJECT = "interior_50x100_empty_nest_anglo"


@pytest.fixture(scope="module")
def inputs():
    return load_fixture("area_matrix", SUBJECT), load_fixture("lot_capacity", "interior_50x100")


@pytest.fixture(scope="module")
def result(inputs):
    am, lc = inputs
    return run_stacking(am, [lc], mode="all")


def test_module_output_equals_the_fixture(inputs):
    from spaceplan.pipeline.main.run_modules import stack_plan_contract_for

    am, lc = inputs
    assert stack_plan_contract_for(area_matrix=am, lot_capacities=[lc], mode="all") == load_fixture("stack_plan",
                                                                                                    SUBJECT)


def test_contract_validates_and_round_trips(result):
    contract = to_contract(result)
    assert contract_problems(contract, "stack_plan") == []
    assert contract["produced_by"] == "stacking" and contract["consumers"] == ["viz", "pipeline"]
    payload = from_contract(contract)
    assert payload["meta"]["stage"] == "S0" and len(payload["cells"]) == len(result["cells"])


def test_contract_rejects_a_bad_status(result):
    bad = copy.deepcopy(to_contract(result))
    bad["cells"][0]["status"] = "maybe"
    with pytest.raises(ContractValidationError):
        from_contract(bad)


def test_selection_modes(inputs):
    am, lc = inputs
    ranked = [c for c in am["cells"] if c["rank"] is not None]
    counts = {m: len(run_stacking(am, [lc], mode=m)["cells"]) for m in ("best", "top2", "all")}
    assert counts["best"] == sum(1 for c in ranked if c["rank"] == 1)
    assert counts["best"] <= counts["top2"] <= counts["all"] == len(ranked)
    assert select_cells(am["cells"], 1) and all(selection_label(c) == "best" for c in select_cells(am["cells"], 1))


def test_cells_carry_levels_height_and_next_stage(result, inputs):
    am, _ = inputs
    scat = load_stacking_catalog()
    assert len(result["cells"]) == sum(1 for c in am["cells"] if c["rank"] is not None)
    for c in result["cells"]:
        assert len(c["levels"]) == c["floors"]
        assert {h["roof_id"] for h in c["height"]} == {r["roof_id"] for r in scat.roofs}
        assert c["default_roof"] == scat.default_roof
        assert c["next_stage"] == ("S1" if c["floors"] > 1 and c["status"] != "exceeds_height" else None)
    # on the interior lot two floors of 10 ft fit under the 24 ft plane start with either roof
    assert {c["status"] for c in result["cells"]} == {"within_plane"}


def test_lot_facts(result):
    lot = result["lots"][0]
    assert lot["lot_id"] == "interior-50x100" and lot["lot_width_ft"] == 50.0
    env = lot["height_envelope"]
    assert (env["plane_start_ft"], env["overall_max_ft"], env["angle_deg"]) == (24.0, 30.0, 45)
    assert lot["floors_by_height"] == {"flat": 2, "pitched_4_12": 2} and not lot["third_floor_possible"]
    assert lot["slope_class"] == "flat"
    assert [b["band"] for b in lot["below_grade_probe"]] == ["outside_gfa", "outside_gfa", "gfa_not_story", "story"]
    assert lot["summary"]["cells"] == len(result["cells"])


def test_meta_traces_rules_and_catalogs(result):
    meta = result["meta"]
    assert meta["vertical_ruleset"] == "sdmc-rs-1-7-vertical" and len(meta["vertical_ruleset_sha256"]) == 64
    assert meta["stacking_catalog_version"] == "0.3.0" and meta["stair_sqft_per_level"] == 60.0
    assert meta["garage_counts_in_gfa"] is True and meta["lots"] == ["interior-50x100"]


def test_missing_lot_capacity_is_an_error(inputs):
    am, _ = inputs
    with pytest.raises(ValueError, match="no lot_capacity contract"):
        run_stacking(am, [], mode="all")


def test_tables(result, tmp_path):
    rows = table_rows(result)
    assert len(rows) == len(result["cells"]) and set(rows[0]) == set(TABLE_FIELDS)
    (path,) = write_tables(result, tmp_path)
    assert path.read_text(encoding="utf-8").splitlines()[0] == ",".join(TABLE_FIELDS)


def test_stacking_catalog_checks():
    data = copy.deepcopy(load_stacking_catalog().data)
    assert check_stacking_catalog(data) == []
    assert load_stacking_catalog().selection_k("best") == 1 and load_stacking_catalog().selection_k("all") is None
    with pytest.raises(StackingCatalogError):
        load_stacking_catalog().selection_k("top9")
    data["roofs"]["default_roof"] = "dome"
    data["roofs"]["types"][0]["kind"] = "dome"
    data["levels"]["floor_to_floor_ft"] = 0
    problems = check_stacking_catalog(data)
    assert any("default_roof" in p for p in problems) and any("kind" in p for p in problems)
    assert any("floor_to_floor_ft" in p for p in problems)
    assert check_stacking_catalog({}) and "missing block" in check_stacking_catalog({})[0]


def test_lot_capacity_contract_for_matches_the_capacity_workflow():
    """The light layer-0 path writes the same lot_capacity contract as the full capacity workflow."""
    from spaceplan.core.lib_aux.json_io import load_resource_json
    from spaceplan.pipeline.main.run_modules import lot_capacity_contract_for

    brief = load_resource_json("spaceplan", "data", "briefs", "interior_50x100.json")
    assert lot_capacity_contract_for(brief) == load_fixture("lot_capacity", "interior_50x100")
    apt = load_resource_json("spaceplan", "data", "briefs", "apt_2br_interior.json")
    assert lot_capacity_contract_for(apt) is None


def test_cli_stacking_from_contracts(inputs, tmp_path, capsys):
    from spaceplan.pipeline.main.cli import main

    am_path, lc_path = tmp_path / "am.json", tmp_path / "lc.json"
    am_path.write_text(json.dumps(inputs[0]), encoding="utf-8")
    lc_path.write_text(json.dumps(inputs[1]), encoding="utf-8")
    out = tmp_path / "stack_plan.json"
    code = main(["stacking", "--area-matrix", str(am_path), "--lot-capacity", str(lc_path), "--cells", "all",
                 "-o", str(out), "--tables", str(tmp_path)])
    assert code == 0
    assert json.loads(out.read_text(encoding="utf-8")) == load_fixture("stack_plan", SUBJECT)
    assert (tmp_path / "stack_plan_cells.csv").exists()
    text = capsys.readouterr().out
    assert "stack_plan 0.2.0 by stacking" in text and "interior-50x100" in text
