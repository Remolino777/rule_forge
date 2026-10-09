"""Contract fixtures for the per-module tests (refactor tanda 4).

    python tools/make_fixtures.py write    # regenerate tests/<module>/fixtures/*.json
    python tools/make_fixtures.py check    # exit 1 if a fixture differs from what the code produces now

Fixtures are the contracts the modules produce for a few reference inputs. Before writing, every fixture is
checked against the frozen snapshot (tests/golden): the package assembled from the fixtures, and the area-matrix
rows, must equal the golden files. So a fixture can only be regenerated while the snapshot still passes; the
snapshot itself is never written here.
"""

from __future__ import annotations

import csv
import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "tests"
sys.path.insert(0, str(Path(__file__).resolve().parent))

from golden_check import GOLDEN, _normalize, _round

HOUSES = ("interior_50x100", "interior_50x100_multigen_latino")
APARTMENTS = ("apt_2br_interior",)
PORTFOLIO = {"archetype_id": "empty_nest", "cultural_profile": "anglo"}
AREA_LOT, AREA_HOUSEHOLD = "interior_50x100", ("empty_nest", "anglo")
MODULE_OF = {"lot_capacity": "lotcap", "site_plan": "site", "zoning_scheme": "zoning", "program": "household",
             "cost_report": "cost", "program_portfolio": "profiles", "area_matrix": "areas"}


def fixture_path(contract: str, subject: str) -> Path:
    return TESTS / MODULE_OF[contract] / "fixtures" / f"{contract}_{subject}.json"


def produce() -> dict[Path, dict]:
    from spaceplan.core.lib_aux.json_io import load_resource_json
    from spaceplan.pipeline.main.run_capacity import run_capacity_contracts
    from spaceplan.pipeline.main.run_modules import area_matrix_contract_for, portfolio_contract_for

    out: dict[Path, dict] = {}
    for name in HOUSES + APARTMENTS:
        brief = load_resource_json("spaceplan", "data", "briefs", f"{name}.json")
        package, contracts = run_capacity_contracts(brief)
        golden = json.loads((GOLDEN / f"package_{name}.json").read_text(encoding="utf-8"))
        if json.dumps(_normalize(package), sort_keys=True) != json.dumps(golden, sort_keys=True):
            raise SystemExit(f"package of {name} differs from the golden snapshot: fixtures not written")
        for contract, instance in contracts.items():
            out[fixture_path(contract, name)] = instance
    out[fixture_path("program_portfolio", "_".join(PORTFOLIO.values()))] = portfolio_contract_for(dict(PORTFOLIO))
    matrix = area_matrix_contract_for(lots=[AREA_LOT], households=[AREA_HOUSEHOLD], zone_top=0)
    _check_area_rows(matrix)
    out[fixture_path("area_matrix", f"{AREA_LOT}_{'_'.join(AREA_HOUSEHOLD)}")] = matrix
    return out


def _check_area_rows(matrix: dict) -> None:
    """The cells of the small matrix are the golden rows of that lot and household."""
    from spaceplan.modules.areas.lib.area_matrix import compact

    rows = [_round(compact(c)) for c in matrix["cells"]]
    buf = io.StringIO()
    csv.DictWriter(buf, fieldnames=list(rows[0]), lineterminator="\n").writerows(rows)
    golden = (GOLDEN / "area_matrix_cells.csv").read_text(encoding="utf-8").splitlines()
    missing = [r for r in buf.getvalue().splitlines() if r not in golden]
    if missing:
        raise SystemExit(f"{len(missing)} area-matrix rows are not in the golden snapshot: fixtures not written")


def comparable(contract: dict) -> dict:
    """Contract without the volatile timing fields (area matrix: seconds per lot and per E2 run)."""
    data = json.loads(json.dumps(contract))
    if data.get("contract") == "area_matrix":
        for lot in data["lots"]:
            lot.pop("seconds", None)
            for e in lot["e2"]:
                e.pop("seconds", None)
    return data


def main(argv: list[str]) -> int:
    mode = argv[1] if len(argv) > 1 else "check"
    current = produce()
    if mode == "write":
        for path, contract in current.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(contract, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"wrote {len(current)} contract fixtures")
        return 0
    changed = [p for p, c in current.items()
               if not p.exists() or comparable(json.loads(p.read_text(encoding="utf-8"))) != comparable(c)]
    for p in changed:
        print(f"CHANGED {p.relative_to(ROOT)}")
    print("FIXTURES", "PASSED" if not changed else "FAILED", f"({len(current)} fixtures)")
    return 1 if changed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
