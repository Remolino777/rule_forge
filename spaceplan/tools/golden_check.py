"""Golden-output check for the modular refactor (tandas 1-4).

    python tools/golden_check.py write    # freeze today's outputs (done once, at tanda-0)
    python tools/golden_check.py check    # exit 1 if any output differs from the frozen snapshot

Outputs compared:
  * the capacity package of every brief in spaceplan/data/briefs (run_capacity, default arguments);
  * the compact area-matrix table of the 10 pilot lots (step 6.6, no E2, no figures).
Volatile fields (package id, generator version) are removed before comparing. Floats are rounded to
6 decimals so a harmless reordering of a sum does not fail the check.
"""

from __future__ import annotations

import csv
import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "tests" / "golden"
VOLATILE_META = ("package_id", "generator")


def _round(obj):
    if isinstance(obj, float):
        return round(obj, 6)
    if isinstance(obj, dict):
        return {k: _round(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_round(v) for v in obj]
    return obj


def _normalize(package: dict) -> dict:
    package = json.loads(json.dumps(package, default=str))
    for key in VOLATILE_META:
        package.get("meta", {}).pop(key, None)
    return _round(package)


def packages() -> dict[str, str]:
    from spaceplan.lib_aux.json_io import load_json
    from spaceplan.main.run_capacity import run_capacity

    out = {}
    for path in sorted((ROOT / "spaceplan" / "data" / "briefs").glob("*.json")):
        out[f"package_{path.stem}.json"] = json.dumps(_normalize(run_capacity(load_json(path))), sort_keys=True,
                                                      indent=1)
    return out


def area_matrix() -> dict[str, str]:
    from spaceplan.lib.area_matrix import compact
    from spaceplan.main.run_area_matrix import run_area_matrix

    result = run_area_matrix(zone_top=0)
    rows = [_round(compact(c)) for c in result["cells"]]
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(rows[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return {"area_matrix_cells.csv": buf.getvalue()}


def produce() -> dict[str, str]:
    return {**packages(), **area_matrix()}


def main(argv: list[str]) -> int:
    mode = argv[1] if len(argv) > 1 else "check"
    current = produce()
    if mode == "write":
        GOLDEN.mkdir(parents=True, exist_ok=True)
        for name, text in current.items():
            (GOLDEN / name).write_text(text, encoding="utf-8")
        print(f"wrote {len(current)} golden files to {GOLDEN}")
        return 0
    frozen = {p.name: p.read_text(encoding="utf-8") for p in GOLDEN.glob("*") if p.is_file()}
    missing = sorted(set(frozen) - set(current))
    extra = sorted(set(current) - set(frozen))
    changed = sorted(n for n in set(frozen) & set(current) if frozen[n] != current[n])
    for name in changed:
        a, b = frozen[name].splitlines(), current[name].splitlines()
        first = next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), min(len(a), len(b)))
        print(f"CHANGED {name} (first difference at line {first + 1})")
    for name in missing:
        print(f"MISSING {name}")
    for name in extra:
        print(f"NEW (not frozen) {name}")
    ok = not (changed or missing)
    print("GOLDEN CHECK", "PASSED" if ok else "FAILED", f"({len(frozen)} frozen files)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
