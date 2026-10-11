"""Why a two-floor cell of stage S1.2 was not zoned: per strategy, what S1 discarded and what S2 could not zone.

Reads stack_plan contracts only. For each cell with s2.status != zoned: the S1 discards by strategy and cause
(door, circulation, K06, no_wall), the candidates handed to S2 with their S2 status, the first hard-rule violations
of the upper and ground searches, and the drawn floor widths (narrowest side of the upper floor).

usage: python tools/diagnose_unzoned.py OUT_DIR STACK_PLAN.json [...]
"""

from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from pathlib import Path

from shapely.geometry import shape

STRATEGIES = ("A", "D", "C", "B")


def _narrow_side(poly: dict) -> float:
    r = shape(poly).minimum_rotated_rectangle
    xs = list(r.exterior.coords)
    sides = sorted(((xs[i][0] - xs[i + 1][0]) ** 2 + (xs[i][1] - xs[i + 1][1]) ** 2) ** 0.5 for i in range(2))
    return round(sides[0], 1)


def main(out_dir: str, *paths: str) -> None:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for p in paths:
        for c in json.load(open(p))["cells"]:
            s1, s2 = c.get("s1") or {}, c.get("s2") or {}
            if not s2 or s2.get("status") == "zoned":
                continue
            acc = s1.get("access_core") or {}
            disc = acc.get("discards") or {}
            handed = Counter(k["strategy"] for k in acc.get("candidates", []))
            tried = Counter((n["strategy"], n["s2_status"]) for n in (s2.get("stair_choice") or {}).get("not_zoned", []))
            row = {"lot_id": c["lot_id"], "household_id": c["household_id"], "profile": c["profile"],
                   "scheme_id": c["scheme_id"], "s2_status": s2["status"], "upper_placement": s1.get("upper_placement"),
                   "upper_narrow_ft": _narrow_side(s1["levels"][1]["polygon"]) if s1.get("levels") else None,
                   "upper_sqft": round(shape(s1["levels"][1]["polygon"]).area, 1) if s1.get("levels") else None,
                   "upper_spaces": ",".join(c["levels"][1].get("spaces") or []) if len(c.get("levels", [])) > 1 else "",
                   "upper_violations": json.dumps((s2.get("upper_search") or {}).get("first_violations")),
                   "ground_violations": json.dumps((s2.get("ground_search") or {}).get("first_violations"))}
            for st in STRATEGIES:
                causes = {k.split(":", 1)[1]: v for k, v in disc.items() if k.startswith(f"{st}:")}
                row[f"{st}_placed"] = causes.pop("placed", 0)
                row[f"{st}_discards"] = json.dumps(causes)
                row[f"{st}_to_s2"] = handed.get(st, 0)
                row[f"{st}_s2"] = json.dumps({k[1]: v for k, v in tried.items() if k[0] == st})
            rows.append(row)
    if rows:
        with (out / "unzoned_cells.csv").open("w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
    for r in rows:
        print(r["lot_id"], r["household_id"], r["profile"], r["s2_status"], "upper", r["upper_narrow_ft"], "ft",
              r["upper_sqft"], "sqft", r["upper_violations"],
              {st: (r[f"{st}_placed"], r[f"{st}_discards"], r[f"{st}_to_s2"]) for st in STRATEGIES})


if __name__ == "__main__":
    main(*sys.argv[1:])
