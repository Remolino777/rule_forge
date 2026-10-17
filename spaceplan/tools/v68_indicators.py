"""Indicators of the V6.8 automated steps (k1b onward) over a pilot directory of stack_plan_<lot>.json files.

    python tools/v68_indicators.py PILOT_DIR [--out PILOT_DIR/v68_indicators.json]

Reads the S2.1 stack_plan contracts that tools/run_pilot.py writes and reports, for the houses (cells spaced by
S2.1) and for every zoned cell: the stair types, the U on the joint, the zone units (S2) and spaces (S2.1) the stair
touches, the use of the space under the stair and what it opens to, the stair position (joint edge and depth fraction
of its centre in the ground floor), the area of the upper floor over the garage, and the garage-to-kitchen route of
the houses (does the door graph reach the kitchen from the garage without crossing living, dining or family rooms;
its length along door centres). Measurement only: no design values live here except the contact tolerance of a
shared wall.
"""

from __future__ import annotations

import argparse
import collections
import json
import statistics
from pathlib import Path

from shapely.geometry import LineString, shape

CONTACT_FT = 1.0          # least shared-wall length that counts as touching (measurement tolerance)
SOCIAL = {"living_room", "dining_room", "living_dining", "family_room"}


def _poly(g):
    return shape(g) if g else None


def _touching(stair, polys) -> int:
    n = 0
    for p in polys:
        if p is None or p.is_empty:
            continue
        if stair.buffer(0.05).intersection(p).area > 1e-6 or \
                stair.boundary.intersection(p.buffer(0.05)).length >= CONTACT_FT:
            n += 1
    return n


def _median(xs):
    return round(statistics.median(xs), 2) if xs else None


def _route(floor: dict) -> dict | None:
    """Garage -> kitchen over the door graph of the ground floor (doors as edges, door centres as points)."""
    spaces = {s["space_id"]: s for s in floor.get("spaces", [])}
    doors = floor.get("doors", [])
    adj = collections.defaultdict(list)
    for d in doors:
        a, b = d.get("a"), d.get("b")
        if a is None or b is None:
            continue
        seg = d.get("segment")
        c = LineString(seg).centroid if seg else None
        adj[a].append((b, c))
        adj[b].append((a, c))
    garage = [k for k, s in spaces.items() if s["space_type"].startswith("garage")]
    if not garage:
        garage = [k for k in adj if str(k).startswith("garage")]
    kitchens = {k for k, s in spaces.items() if s["space_type"] == "kitchen"}
    if not garage or not kitchens:
        return None
    best = None
    for avoid in (True, False):
        stack = [(garage[0], None, 0.0, [garage[0]])]
        seen = {}
        while stack:
            node, at, dist, path = stack.pop()
            if node in kitchens:
                if best is None or dist < best[0]:
                    best = (dist, path, avoid)
                continue
            for nxt, c in adj.get(node, ()):
                if nxt in path:
                    continue
                st = (spaces.get(nxt) or {}).get("space_type", "")
                if avoid and st in SOCIAL:
                    continue
                step = 0.0 if at is None or c is None else at.distance(c)
                nd = dist + step
                if seen.get(nxt, 1e9) <= nd:
                    continue
                seen[nxt] = nd
                stack.append((nxt, c, nd, path + [nxt]))
        if best is not None:
            break
    if best is None:
        return {"reached": False}
    return {"reached": True, "clean": best[2], "length_ft": round(best[0], 1),
            "through": [(spaces.get(p) or {}).get("space_type", p) for p in best[1][1:-1]]}


def cell_rows(plan: dict) -> list[dict]:
    rows = []
    for c in plan["cells"]:
        s1, s2, s21 = c.get("s1") or {}, c.get("s2") or {}, c.get("s21") or {}
        if s2.get("status") != "zoned":
            continue
        core = s1.get("stair_core") or {}
        fp = _poly(core.get("footprint"))
        ch = (s2.get("stair_choice") or {}).get("chosen") or {}
        ac = s1.get("access_core") or {}
        ground = _poly(s1["levels"][0]["polygon"]) if s1.get("levels") else None
        upper = _poly(s1["levels"][1]["polygon"]) if len(s1.get("levels") or []) > 1 else None
        garage = _poly((s1.get("ground") or {}).get("garage_polygon"))
        row = {"lot": c["lot_id"], "household": c["household_id"], "profile": c["profile"],
               "spaced": s21.get("status") == "spaced", "first_violation": s21.get("first_violation"),
               "stair": f"{ch.get('strategy')}:{ch.get('stair_id')}:{ch.get('placement')}",
               "stair_id": ch.get("stair_id"), "strategy": ch.get("strategy"), "along": ch.get("along"),
               "placement": ch.get("placement"), "wall": ac.get("wall")}
        if fp is not None and ground is not None:
            y0, y1 = ground.bounds[1], ground.bounds[3]
            row["depth_fraction"] = round((fp.centroid.y - y0) / ((y1 - y0) or 1.0), 3)
            if upper is not None and ch.get("strategy") == "B":
                ux0, uy0, ux1, uy1 = upper.bounds
                fx0, fy0, fx1, fy1 = fp.bounds
                near_rear = min(abs(fy0 - uy0), abs(fy1 - uy1))
                near_side = min(abs(fx0 - ux0), abs(fx1 - ux1))
                row["joint_edge"] = "rear" if near_rear <= near_side else "side"
        if upper is not None and garage is not None:
            row["upper_over_garage_sqft"] = round(upper.intersection(garage).area, 1)
            row["upper_sqft"] = round(upper.area, 1)
        opt = (s2.get("options") or {}).get(s2.get("chosen_option")) or {}
        for key in ("ground", "upper"):
            blk = (opt.get("ground") if key == "ground" else s2.get("upper")) or {}
            if fp is not None and blk.get("units"):
                row[f"s2_units_touched_{key}"] = _touching(fp, [_poly(u.get("polygon")) for u in blk["units"]])
        row["s2_half_bath"] = opt.get("half_bath")
        row["chosen_option"] = s2.get("chosen_option")
        if row["spaced"]:
            for key in ("ground", "upper"):
                f = s21.get(key) or {}
                sp = [x for x in f.get("spaces", []) if x["space_type"] != "stair"]
                if fp is not None and sp:
                    row[f"s21_spaces_touched_{key}"] = _touching(
                        fp, [_poly(x.get("polygon")) for x in sp if not x.get("fixed")])
                if key == "ground":
                    types = {x["space_id"]: x["space_type"] for x in sp}
                    under = [x for x in sp if x["space_type"] == "half_bath" and x.get("fixed")]
                    row["half_bath_present"] = any(x["space_type"] == "half_bath" for x in sp)
                    row["under_stair"] = "half_bath" if under else "pantry"
                    if under:
                        hb_ids = {under[0]["space_id"]} | {k for k, t in types.items() if t == "vestibule"}
                        outs = [types.get(d["b"] if d["a"] in hb_ids else d["a"]) for d in f.get("doors", [])
                                if (d["a"] in hb_ids) != (d["b"] in hb_ids)]
                        row["half_bath_opens_to"] = next((o for o in outs if o and o != "half_bath"), None)
                    row["landing_space_ground"] = types.get(f.get("landing_space"), f.get("landing_space"))
                    row["garage_kitchen"] = _route(f)
                else:
                    row["landing_space_upper"] = {x["space_id"]: x["space_type"] for x in sp}.get(
                        f.get("landing_space"), f.get("landing_space"))
        rows.append(row)
    return rows


def summarize(rows: list[dict]) -> dict:
    houses = [r for r in rows if r["spaced"]]
    by_lot = collections.Counter(r["lot"] for r in houses)
    u_joint = [r for r in rows if r["strategy"] == "B" and (r["stair_id"] or "").startswith("u_")]
    out = {
        "zoned_cells": len(rows),
        "houses": len(houses),
        "houses_by_lot": dict(sorted(by_lot.items())),
        "stairs_of_houses": dict(collections.Counter(r["stair"] for r in houses).most_common()),
        "u_on_joint": {"zoned": len(u_joint), "spaced": sum(r["spaced"] for r in u_joint),
                       "along_spaced": sum(r["spaced"] and bool(r["along"]) for r in u_joint),
                       "first_violations": dict(collections.Counter(
                           ":".join(str(r["first_violation"]).split(":")[:3]) for r in u_joint
                           if not r["spaced"]).most_common(10))},
        "s2_units_touched": {k: dict(sorted(collections.Counter(r.get(f"s2_units_touched_{k}") for r in rows
                                                                if f"s2_units_touched_{k}" in r).items()))
                             for k in ("ground", "upper")},
        "s2_units_touched_houses": {k: dict(sorted(collections.Counter(r.get(f"s2_units_touched_{k}") for r in houses
                                                                       if f"s2_units_touched_{k}" in r).items()))
                                    for k in ("ground", "upper")},
        "s21_spaces_touched_houses": {k: dict(sorted(collections.Counter(r.get(f"s21_spaces_touched_{k}")
                                                                         for r in houses
                                                                         if f"s21_spaces_touched_{k}" in r).items()))
                                      for k in ("ground", "upper")},
        "under_stair_houses": dict(collections.Counter(r.get("under_stair") for r in houses)),
        "half_bath_under_stair_opens_to": dict(collections.Counter(
            r.get("half_bath_opens_to") for r in houses if r.get("under_stair") == "half_bath")),
        "landing_spaces": {"ground": dict(collections.Counter(r.get("landing_space_ground") for r in houses)),
                           "upper": dict(collections.Counter(r.get("landing_space_upper") for r in houses))},
        "joint_edge_houses": dict(collections.Counter(r.get("joint_edge") for r in houses if r["strategy"] == "B")),
        "joint_edge_zoned_over_garage": dict(collections.Counter(r.get("joint_edge") for r in rows
                                                                 if r["strategy"] == "B"
                                                                 and r["placement"] == "over_garage")),
        "depth_fraction_houses": {"median": _median([r["depth_fraction"] for r in houses if "depth_fraction" in r]),
                                  "min": min((r["depth_fraction"] for r in houses if "depth_fraction" in r),
                                             default=None),
                                  "max": max((r["depth_fraction"] for r in houses if "depth_fraction" in r),
                                             default=None)},
        "over_garage_upper_sqft_houses": _median([r["upper_sqft"] for r in houses
                                                  if r["placement"] == "over_garage" and "upper_sqft" in r]),
        "garage_kitchen_houses": {
            "with_route": sum(1 for r in houses if (r.get("garage_kitchen") or {}).get("reached")),
            "clean": sum(1 for r in houses if (r.get("garage_kitchen") or {}).get("clean")),
            "median_ft": _median([r["garage_kitchen"]["length_ft"] for r in houses
                                  if (r.get("garage_kitchen") or {}).get("reached")])},
        "first_violations": dict(collections.Counter(":".join(str(r["first_violation"]).split(":")[:3])
                                                     for r in rows if not r["spaced"]).most_common(20)),
    }
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pilot")
    ap.add_argument("--out")
    a = ap.parse_args()
    d = Path(a.pilot)
    rows = []
    for fn in sorted(d.glob("stack_plan_*.json")):
        rows += cell_rows(json.load(open(fn)))
    res = {"summary": summarize(rows), "rows": rows}
    out = Path(a.out) if a.out else d / "v68_indicators.json"
    out.write_text(json.dumps(res, indent=2, default=str))
    print(json.dumps(res["summary"], indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
