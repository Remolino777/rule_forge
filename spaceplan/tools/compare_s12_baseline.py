"""Before/after of stage S1.2 (step 6.7a) on the pilot, read only from contracts.

Before: the frozen baseline docs/baselines/stack_plan_04bbba2 (stair at the joint, S1.1 choice, S2 backtrack).
After:  stack_plan contracts produced with the stair from the main door (S1 candidates, S2 three-level choice).
Cells are matched by (lot, household, profile, scheme). The same geometric measures are taken on both:
  zoned, stair type, stair touching an exterior wall of both floors (>= the catalog light contact), occupied area
  (stair + net ground under it + void), largest free rectangle of each floor (stair, garage, void taken), arrival,
  half bath under the stair. Routes from the door exist only in the new contracts (the baseline had no main door).

usage: python tools/compare_s12_baseline.py OUT_DIR NEW_STACK_PLAN.json [...]
"""

from __future__ import annotations

import csv
import gzip
import json
import math
import statistics
import sys
from collections import Counter
from pathlib import Path

from shapely import affinity
from shapely.geometry import shape
from shapely.ops import unary_union

from spaceplan.modules.stacking.lib.stacking_catalog import load_stacking_catalog
from spaceplan.modules.stacking.lib_aux.zone_grid import largest_rectangle, rasterize

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "docs" / "baselines" / "stack_plan_04bbba2" / "stack_plan_s2_joint_best.json.gz"
RES_FT = 0.5


def _key(c: dict) -> tuple:
    return (c["lot_id"], c["household_id"], c["profile"], c["scheme_id"])


def _angle(poly) -> float:
    """Angle (deg) of the longest edge of the floor's minimum rotated rectangle, to rasterize axis-aligned."""
    pts = list(poly.minimum_rotated_rectangle.exterior.coords)
    edges = [(pts[i], pts[i + 1]) for i in range(4)]
    (x0, y0), (x1, y1) = max(edges, key=lambda e: math.dist(*e))
    return math.degrees(math.atan2(y1 - y0, x1 - x0))


def _free_rect(floor, taken) -> float:
    a = _angle(floor)
    f = affinity.rotate(floor, -a, origin=(0, 0))
    t = affinity.rotate(taken, -a, origin=(0, 0)) if taken is not None and not taken.is_empty else None
    g = rasterize(f, [("taken", t)] if t is not None else [], RES_FT)
    return largest_rectangle(g.free) * g.cell_area


def _geo(x):
    return shape(x) if x else None


def measures(c: dict, contact_ft: float) -> dict:
    s1, s2 = c.get("s1") or {}, c.get("s2") or {}
    out = {"zoned": s2.get("status") == "zoned", "s2_status": s2.get("status")}
    if s1.get("status") != "drawn":
        return out
    ground, upper = _geo(s1["levels"][0]["polygon"]), _geo(s1["levels"][1]["polygon"])
    stair = _geo(s1["stair"]["polygon"])
    garage = _geo(s1["ground"].get("garage_polygon"))
    access = s1.get("access_core") or {}
    void = _geo(access.get("void"))
    g_taken = unary_union([x for x in (stair, garage) if x is not None])
    u_taken = unary_union([x for x in (stair, void) if x is not None])
    exterior = min(stair.boundary.intersection(ground.boundary.buffer(1e-3)).length,
                   stair.boundary.intersection(upper.boundary.buffer(1e-3)).length)
    net = s1["stair_core"]["under_stair"]["net_ground_sqft"]
    out.update({"stair_id": s1["stair"]["stair_id"], "placement": s1["upper_placement"],
                "exterior_wall": exterior >= contact_ft,
                "occupied_sqft": round(net + stair.area + (void.area if void is not None else 0.0), 1),
                "free_rect_ground": round(_free_rect(ground, g_taken), 1),
                "free_rect_upper": round(_free_rect(upper, u_taken), 1)})
    if out["zoned"]:
        opt = s2["options"][s2["chosen_option"]]
        out.update({"arrival": s2["arrival"]["receiving"], "half_bath": opt.get("half_bath"),
                    "score": s2.get("score")})
        routes = opt.get("routes") or {}
        out["route_ft"] = routes.get("total_ft")
    choice = (s2.get("stair_choice") or {}).get("chosen") or {}
    out.update({"strategy": choice.get("strategy"), "light": choice.get("light"),
                "reason": (s2.get("stair_choice") or {}).get("reason")})
    return out


def _med(xs):
    xs = [x for x in xs if x is not None]
    return round(statistics.median(xs), 1) if xs else None


def main(out_dir: str, *new_paths: str) -> None:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    contact = float(load_stacking_catalog().access_core["light"]["min_contact_ft"])
    base = {_key(c): c for c in json.load(gzip.open(BASELINE))["cells"] if c.get("s2")}
    new = {}
    for p in new_paths:
        new.update({_key(c): c for c in json.load(open(p))["cells"] if c.get("s2")})
    rows = []
    for k in sorted(set(base) | set(new)):
        row = dict(zip(("lot_id", "household_id", "profile", "scheme_id"), k))
        for tag, src in (("before", base), ("after", new)):
            if k in src:
                row.update({f"{tag}_{m}": v for m, v in measures(src[k], contact).items()})
        rows.append(row)
    fields = sorted({f for r in rows for f in r}, key=lambda f: (f not in ("lot_id", "household_id", "profile",
                                                                           "scheme_id"), f))
    with (out / "s12_before_after.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    both = [r for r in rows if "before_zoned" in r and "after_zoned" in r]
    zb = [r for r in both if r["before_zoned"] and r["after_zoned"]]
    summary = {"cells_before": len(base), "cells_after": len(new), "matched": len(both),
               "zoned": [sum(r["before_zoned"] for r in both), sum(r["after_zoned"] for r in both)],
               "exterior_wall_stair": [sum(bool(r.get("before_exterior_wall")) for r in both),
                                       sum(bool(r.get("after_exterior_wall")) for r in both)],
               "natural_light_after": dict(Counter(r.get("after_light") for r in both)),
               "strategy_after": dict(Counter(r.get("after_strategy") for r in both)),
               "stair_type": [dict(Counter(r.get("before_stair_id") for r in both)),
                              dict(Counter(r.get("after_stair_id") for r in both))],
               "half_bath_under_stair": [sum(r.get("before_half_bath") == "under_stair" for r in both),
                                         sum(r.get("after_half_bath") == "under_stair" for r in both)],
               "arrival": [dict(Counter(r.get("before_arrival") for r in both if r["before_zoned"])),
                           dict(Counter(r.get("after_arrival") for r in both if r["after_zoned"]))],
               "median_both_zoned": {m: [_med(r.get(f"before_{m}") for r in zb), _med(r.get(f"after_{m}") for r in zb)]
                                     for m in ("occupied_sqft", "free_rect_ground", "free_rect_upper", "score")},
               "median_route_ft_after": _med(r.get("after_route_ft") for r in both),
               "by_lot": {lot: {"zoned": [sum(r["before_zoned"] for r in both if r["lot_id"] == lot),
                                          sum(r["after_zoned"] for r in both if r["lot_id"] == lot)],
                                "cells": sum(1 for r in both if r["lot_id"] == lot)}
                          for lot in sorted({r["lot_id"] for r in both})}}
    (out / "s12_before_after_summary.json").write_text(json.dumps(summary, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main(*sys.argv[1:])
