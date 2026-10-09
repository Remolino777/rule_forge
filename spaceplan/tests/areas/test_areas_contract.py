"""areas module through its contract (refactor tanda 4): area_matrix of one lot and one household."""

import copy
import csv
import io
from pathlib import Path

import pytest
from conftest import GOLDEN, _round6, load_fixture, without_seconds

from spaceplan.core.lib.contracts import ContractValidationError, contract_problems
from spaceplan.modules.areas.lib.area_matrix import compact
from spaceplan.modules.areas.main.contract import from_contract, to_contract

SUBJECT = "interior_50x100_empty_nest_anglo"


@pytest.fixture(scope="module")
def produced():
    from spaceplan.pipeline.main.run_area_analysis import run_area_matrix

    return to_contract(run_area_matrix(lots=["interior_50x100"], households=[("empty_nest", "anglo")], zone_top=0))


def test_module_output_equals_the_fixture(produced):
    assert without_seconds(produced) == without_seconds(load_fixture("area_matrix", SUBJECT))


def test_fixture_cells_are_golden_rows():
    """Each cell, written as tools/golden_check.py writes it, is a row of the frozen pilot table."""
    rows = [_round6(compact(c)) for c in from_contract(load_fixture("area_matrix", SUBJECT))["cells"]]
    buf = io.StringIO()
    csv.DictWriter(buf, fieldnames=list(rows[0]), lineterminator="\n").writerows(rows)
    golden = set((GOLDEN / "area_matrix_cells.csv").read_text(encoding="utf-8").splitlines())
    lines = buf.getvalue().splitlines()
    assert len(lines) == len(rows) > 0 and all(line in golden for line in lines)


def test_contract_validates(produced):
    assert contract_problems(produced, "area_matrix") == []
    matrix = from_contract(produced)
    assert {c["household_id"] for c in matrix["cells"]} == {"empty_nest.anglo"}


def test_consumers_accept_the_contract(tmp_path):
    from spaceplan.modules.viz.main.run_viz import draw_area_matrix

    figures = draw_area_matrix(load_fixture("area_matrix", SUBJECT), tmp_path, lang="en")
    assert len(figures) == 4 and all(Path(f).stat().st_size > 10_000 for f in figures)


def test_cell_without_floors_is_rejected():
    bad = copy.deepcopy(load_fixture("area_matrix", SUBJECT))
    del bad["cells"][0]["floors"]
    with pytest.raises(ContractValidationError):
        from_contract(bad)
