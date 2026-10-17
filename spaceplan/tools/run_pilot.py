"""Pilot run of stage S2.1 on the 10 pilot lots (all households), for the automated V6.8 steps.

    python tools/run_pilot.py OUT_DIR [--jobs 2] [--lots a,b] [--baseline SUMMARY.json]

Inputs: tools/pilot_inputs/pilot_inputs_10lots.tgz (area_matrix, lot_capacity_*, site_plan_* frozen 2026-10-14).
Writes OUT_DIR/stack_plan_<lot>.json, OUT_DIR/<lot>.log and OUT_DIR/pilot_summary.json:
houses (cells with S2.1 status 'spaced') per lot, stair mix of the spaced houses, first violations of the failed
ones and, with --baseline, the difference per lot. Run `spaceplan quality --stack-plans OUT_DIR/stack_plan_*.json
--out OUT_DIR/quality` afterwards for the space-quality indicators."""

from __future__ import annotations

import argparse
import collections
import json
import subprocess
import sys
import tarfile
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "tools" / "pilot_inputs" / "pilot_inputs_10lots.tgz"

ONE_LOT = r"""
import json, sys, time
from spaceplan.modules.stacking.main.run_stacking import run_stacking
inp, lot, out = sys.argv[1], sys.argv[2], sys.argv[3]
am = json.load(open(f"{inp}/area_matrix.json"))
lc = json.load(open(f"{inp}/lot_capacity_{lot}.json"))
sp = [json.load(open(f"{inp}/site_plan_{lot}.json"))]
lot_id = lc["brief_id"]
am["lots"] = [l for l in am["lots"] if l["budget"]["lot_id"] == lot_id]
am["cells"] = [c for c in am["cells"] if c["lot_id"] == lot_id]
t = time.time()
res = run_stacking(am, [lc], None, stage="S2.1", site_plans=sp)
json.dump(res, open(out, "w"))
print(lot, "secs", round(time.time() - t))
"""


def lots_in(inp: Path) -> list[str]:
    return sorted(p.name[len("lot_capacity_"):-5] for p in inp.glob("lot_capacity_*.json"))


def run_lot(inp: Path, lot: str, out: Path) -> tuple[str, int]:
    with open(out / f"{lot}.log", "w") as log:
        rc = subprocess.call([sys.executable, "-c", ONE_LOT, str(inp), lot, str(out / f"stack_plan_{lot}.json")],
                             stdout=log, stderr=subprocess.STDOUT, cwd=str(ROOT))
    return lot, rc


def summarize(out: Path, lots: list[str]) -> dict:
    per_lot, stairs, viol, errors = {}, collections.Counter(), collections.Counter(), []
    for lot in lots:
        fn = out / f"stack_plan_{lot}.json"
        if not fn.exists():
            errors.append(lot)
            continue
        n = 0
        for c in json.load(open(fn))["cells"]:
            s21 = c.get("s21")
            if not s21:
                continue
            if s21.get("status") == "spaced":
                n += 1
                ch = ((c.get("s2") or {}).get("stair_choice") or {}).get("chosen") or {}
                stairs[f"{ch.get('strategy')}:{ch.get('stair_id')}:{ch.get('placement')}"] += 1
            else:
                viol[":".join(str(s21.get("first_violation") or s21.get("status")).split(":")[:3])] += 1
        per_lot[lot] = n
    return {"houses": sum(per_lot.values()), "houses_by_lot": per_lot, "stairs_spaced": dict(stairs.most_common()),
            "first_violations": dict(viol.most_common(25)), "lots_failed_to_run": errors}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--jobs", type=int, default=2)
    ap.add_argument("--lots")
    ap.add_argument("--baseline")
    a = ap.parse_args()
    out = Path(a.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        with tarfile.open(ARCHIVE) as tf:
            tf.extractall(tmp, filter="data")
        inp = Path(tmp) / "inputs"
        lots = a.lots.split(",") if a.lots else lots_in(inp)
        t = time.time()
        with ThreadPoolExecutor(a.jobs) as ex:
            for lot, rc in ex.map(lambda l: run_lot(inp, l, out), lots):
                print(lot, "rc", rc, "elapsed", round(time.time() - t), flush=True)
    summary = summarize(out, lots)
    if a.baseline:
        base = json.load(open(a.baseline))
        summary["baseline_houses"] = base["houses"]
        summary["delta_by_lot"] = {k: v - base["houses_by_lot"].get(k, 0) for k, v in summary["houses_by_lot"].items()}
    (out / "pilot_summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))
    return 1 if summary["lots_failed_to_run"] else 0


if __name__ == "__main__":
    sys.exit(main())
