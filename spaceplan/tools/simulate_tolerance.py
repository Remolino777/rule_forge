"""Route tolerance of stage S1.2 simulated from stack_plan contracts (no zoning again).

Every zoned stair candidate of a cell is kept in s2.stair_choice.ranked; the three-level choice (access_rank) is
re-run on them with each tolerance. Reports, per tolerance and per lot: strategy counts, natural light, median route
of the chosen candidates and the extra route paid against the shortest candidate.

usage: python tools/simulate_tolerance.py OUT_DIR TOLERANCES(comma) STACK_PLAN.json [...]
"""

from __future__ import annotations

import csv
import json
import statistics
import sys
from collections import Counter
from pathlib import Path

from spaceplan.modules.stacking.lib.access_rank import rank_stair_candidates


def main(out_dir: str, tolerances: str, *paths: str) -> None:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    tols = [float(t) for t in tolerances.split(",")]
    cells = []
    for p in paths:
        for c in json.load(open(p))["cells"]:
            ch = (c.get("s2") or {}).get("stair_choice") or {}
            if ch.get("ranked"):
                cells.append((c["lot_id"], ch))
    rows = []
    for tol in tols:
        by_lot: dict[str, list] = {}
        for lot, ch in cells:
            trials = [dict(t) for t in ch["ranked"]]
            best = rank_stair_candidates(trials, tol, ch["strategy_preference"], ch.get("arrival_order"))[0].trial
            shortest = min(t["route_ft"] for t in trials)
            by_lot.setdefault(lot, []).append((best, best["route_ft"] - shortest))
            by_lot.setdefault("ALL", []).append((best, best["route_ft"] - shortest))
        for lot, picks in sorted(by_lot.items()):
            st = Counter(b["strategy"] for b, _ in picks)
            rows.append({"tolerance_ft": tol, "lot_id": lot, "cells": len(picks),
                         **{f"strategy_{k}": st.get(k, 0) for k in "ADCB"},
                         "light_window": sum(1 for b, _ in picks if b["light"] != "none"),
                         "median_route_ft": round(statistics.median(b["route_ft"] for b, _ in picks), 1),
                         "median_extra_route_ft": round(statistics.median(x for _, x in picks), 1),
                         "max_extra_route_ft": round(max(x for _, x in picks), 1)})
    with (out / "tolerance_simulation.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    for r in rows:
        if r["lot_id"] == "ALL":
            print(r)


if __name__ == "__main__":
    main(*sys.argv[1:])
