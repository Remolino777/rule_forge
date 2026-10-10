"""Short test of stage S1.2 (step 6.7a): stair placed from the main door against the permitted walls, versus the
current S1/S2, on three pilot lots. Not part of the pipeline: a comparison harness over the contracts on disk.

    python tools/spike_s1_2.py CONTRACTS_DIR OUT_DIR [--cells top2] [--lots interior-50x100,...]

CONTRACTS_DIR holds area_matrix.json, lot_capacity_<brief>.json and site_plan_<brief>.json. Writes
spike_cells.csv, spike_summary.json, side-by-side sheets with blind labels and the key of the labels.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np
from shapely.geometry import shape
from shapely.ops import unary_union

from spaceplan.core.lib.catalog import load_catalog
from spaceplan.modules.stacking.lib.access_core import JOINT, entry_door, permitted_walls, site_entry
from spaceplan.modules.stacking.lib.access_rank import rank_stair_candidates
from spaceplan.modules.stacking.lib.access_stair import access_candidates, preselect, with_half_bath
from spaceplan.modules.stacking.lib.cell_geometry import DRAWN, S1Context, draw_cell
from spaceplan.modules.stacking.lib.cell_selection import select_cells
from spaceplan.modules.stacking.lib.lot_plan import lot_plan, strategy_key
from spaceplan.modules.stacking.lib.lot_vertical import lot_envelope
from spaceplan.modules.stacking.lib.stacking_catalog import load_stacking_catalog
from spaceplan.modules.stacking.lib.stair import stair_shape
from spaceplan.modules.stacking.lib.stair_access import load_client_ruleset, relations, u_min_span_ft
from spaceplan.modules.stacking.lib.stair_rules import load_stair_ruleset, stair_limits
from spaceplan.modules.stacking.lib.vertical_rules import load_vertical_ruleset
from spaceplan.modules.stacking.lib.zone_cell import ZONED, s2_context, zone_cell
from spaceplan.modules.stacking.lib.zone_relations import build_matrix
from spaceplan.modules.stacking.lib_aux.plan_geometry import polygon_json
from spaceplan.modules.stacking.lib_aux.zone_grid import largest_rectangle, rasterize
from spaceplan.modules.stacking.main.run_stacking import stack_cell, stage_s2

LOTS = {"interior-50x100": "interior_50x100", "narrow-40x125": "narrow_40x125",
        "fan-cul-de-sac-35-80x100": "fan_cul_de_sac_35_80x100"}


def free_rect_sqft(floor, taken, res=0.5) -> float:
    g = rasterize(floor, [("taken", taken)], res)
    return largest_rectangle(g.free) * g.cell_area


def floor_metrics(s1, plan) -> dict:
    to = lambda geo: plan.frame.to_local(shape(geo)) if geo else None
    ground, upper = to(s1["levels"][0]["polygon"]), to(s1["levels"][1]["polygon"])
    stair = to(s1["stair"]["polygon"])
    garage = to(s1["ground"].get("garage_polygon"))
    void = to((s1.get("access_core") or {}).get("void"))
    g_taken = unary_union([x for x in (stair, garage) if x is not None])
    u_taken = unary_union([x for x in (stair, void) if x is not None])
    return {"free_rect_ground": round(free_rect_sqft(ground, g_taken), 1),
            "free_rect_upper": round(free_rect_sqft(upper, u_taken), 1),
            "upper_sqft": round(upper.area, 1)}


def wall_touch(s1, plan, walls, stair_rs) -> str:
    """Does the drawn stair touch a wall that may have openings (comparable for both versions)?"""
    from spaceplan.modules.stacking.lib.access_core import openings_allowed

    fp = plan.frame.to_local(shape(s1["stair"]["polygon"]))
    for w in walls:
        if w.kind == JOINT:
            continue
        if fp.boundary.intersection(w.line.buffer(1e-3)).length >= 2.0 and \
                openings_allowed(stair_rs, w.fire_separation_ft) != "none":
            return w.kind
    return "none"


def t_in(t, front) -> bool:
    return any(t is f for f in front)


def chosen(s2):
    if s2["status"] != ZONED:
        return None
    return s2["options"][s2["chosen_option"]]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("contracts")
    ap.add_argument("out")
    ap.add_argument("--cells", default="top2")
    ap.add_argument("--lots", default=",".join(LOTS))
    ap.add_argument("--sheets", type=int, default=20)
    args = ap.parse_args(argv)
    cdir, out = Path(args.contracts), Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    am = json.loads((cdir / "area_matrix.json").read_text())
    scat, catalog = load_stacking_catalog(), load_catalog()
    acc = scat.access_core
    vrs, srs, crs = load_vertical_ruleset(), load_stair_ruleset(), load_client_ruleset()
    limits = stair_limits(srs)
    matrix = build_matrix(catalog, relations(crs), scat.s2["pair_default_weights"])
    s2ctx = s2_context(scat, catalog, crs, matrix)
    stair_sqft = float(catalog.space_type(scat.stair_space_type)["area"]["target"])
    required = crs.params("K06-STAIR-NATURAL-LIGHT")["required_by_strategy"]
    preference = crs.params("K07-STAIR-STRATEGY")["preference"]
    design = {**scat.stair_design, "u_well_gap_ft": acc["void"]["well_ft"], "u_min_span_ft": u_min_span_ft(crs)}
    ftf = scat.levels["floor_to_floor_ft"]
    shapes = {t["stair_id"]: stair_shape(t, ftf, limits, design) for t in scat.data["stair"]["types"]}
    top_k = int(acc["comparison"]["top_k_per_strategy"])
    selected = select_cells(am["cells"], scat.selection_k(args.cells))
    lots = {lot["budget"]["lot_id"]: lot for lot in am["lots"]}
    rows, records, t0 = [], [], time.time()
    for lot_id in args.lots.split(","):
        brief = LOTS[lot_id]
        lc = json.loads((cdir / f"lot_capacity_{brief}.json").read_text())
        site = site_entry(json.loads((cdir / f"site_plan_{brief}.json").read_text()))
        plan = lot_plan(lc)
        lot_local = plan.frame.to_local(shape(lc["lot"]["polygon"]))
        ctx = S1Context(scat, limits, srs, vrs, crs, catalog, lot_envelope(vrs, lc),
                        (lc.get("terrain") or {}).get("mean_slope"), stair_sqft)
        for c in selected:
            if c["lot_id"] != lot_id or c["floors"] < 2:
                continue
            s0 = stack_cell(c, lots[lot_id], lc, vrs, scat, stair_sqft)
            if s0["next_stage"] != "S1":
                continue
            strategy = strategy_key(lots[lot_id]["budget"], c.get("strategy_used"))
            # ---------------- baseline: current S1 + S2 (with backtrack), same garage side and door
            out_b = dict(s0)
            s1b = draw_cell(c, s0, plan, strategy, ctx, garage_side=site["garage_side"])
            if s1b["status"] != DRAWN:
                continue
            out_b["s1"] = s1b
            stage_s2(c, out_b, plan, strategy, ctx, s2ctx)
            s1b = out_b["s1"]
            gl, ga = (plan.frame.to_local(shape(s1b["levels"][0]["polygon"])),
                      plan.frame.to_local(shape(s1b["ground"]["garage_polygon"])) if s1b["ground"].get("garage_polygon") else None)
            door_b = entry_door(gl, ga, site["garage_side"], site["deck_offset_ft"], acc)
            if door_b is not None:
                s1b["access_core"] = {"vestibule": polygon_json(plan.to_world(door_b.vestibule)), "fixed": False}
                s2b = zone_cell(c, s1b, plan, s2ctx)
                s2b["backtrack"] = out_b["s2"]["backtrack"]
            else:
                s2b = out_b["s2"]
            ul = plan.frame.to_local(shape(s1b["levels"][1]["polygon"]))
            walls_b = permitted_walls(gl, ul, ga, lot_local, acc)
            base = {"s1": s1b, "s2": s2b, "strategy": "current", "light": wall_touch(s1b, plan, walls_b, srs)}
            # ---------------- new: S1.2 candidates from the door, zoned by S2
            pool: dict[str, list] = {}
            stats: Counter = Counter()
            doors: dict[str, object] = {}

            def collect(placement, upper_cand, ground, garage, cfg):
                door = entry_door(ground, garage, site["garage_side"], site["deck_offset_ft"], acc)
                if door is None:
                    stats["no_door"] += 1
                    return [], None
                walls = permitted_walls(ground, upper_cand.polygon, garage, lot_local, acc)
                found, st = access_candidates(upper_cand.polygon, ground, garage, door, walls, shapes, cfg, acc,
                                              srs, required)
                stats.update(st)
                pool[placement] = with_half_bath(preselect(found, top_k), ground, garage, door, cfg)
                doors[placement] = door
                return [a.cand for a in found], None

            draw_cell(c, s0, plan, strategy, ctx, garage_side=site["garage_side"], picker=collect)
            trials = []
            for placement, picks in pool.items():
                door = doors[placement]
                for a in picks:
                    s1n = draw_cell(c, s0, plan, strategy, ctx, placements=[placement], garage_side=site["garage_side"],
                                    picker=lambda *_, a=a: ([a.cand], a.cand))
                    if s1n["status"] != DRAWN:
                        continue
                    s1n["access_core"] = {
                        "fixed": True, "strategy": a.strategy, **a.summary(),
                        "door": polygon_json(plan.to_world(door.segment.buffer(0.25, cap_style="flat"))),
                        "swing": polygon_json(plan.to_world(door.swing)),
                        "vestibule": polygon_json(plan.to_world(door.vestibule)),
                        "void": polygon_json(plan.to_world(a.well)) if a.well is not None else None}
                    s2n = zone_cell(c, s1n, plan, s2ctx)
                    trials.append({"s1": s1n, "s2": s2n, "strategy": a.strategy, "light": a.light.source,
                                   "occupied": a.occupied_sqft, "placement": placement})
            zoned = [t for t in trials if chosen(t["s2"]) and (chosen(t["s2"]).get("routes") or {}).get("total_ft")]
            for t in zoned:
                opt = chosen(t["s2"])
                t.update({"route_ft": opt["routes"]["total_ft"], "occupied_sqft": t["occupied"],
                          "arrival_kind": t["s2"]["upper"].get("arrival_kind"),
                          "half_bath": opt.get("half_bath") == "under_stair"})
            order = (zoned[0]["s2"].get("arrival") or {}).get("order") if zoned else None
            ranked = rank_stair_candidates(zoned, float(acc["comparison"]["route_tolerance_ft"]), preference, order)
            pick = ranked[0].trial if ranked else None
            front = [r.trial for r in ranked if r.pareto]
            if pick is not None:
                pick["reason"] = ranked[0].reason
            # ---------------- metrics
            def metrics(tag, rec):
                if rec is None:
                    return {f"{tag}_zoned": False}
                s1, s2 = rec["s1"], rec["s2"]
                opt = chosen(s2)
                routes = (opt or {}).get("routes") or {}
                m = {f"{tag}_zoned": s2["status"] == ZONED, f"{tag}_stair": s1["stair"]["stair_id"],
                     f"{tag}_strategy": rec["strategy"], f"{tag}_placement": s1["upper_placement"],
                     f"{tag}_light": rec["light"], f"{tag}_route_ft": routes.get("total_ft"),
                     f"{tag}_route_stair_ft": (routes.get("by_target") or {}).get("stair"),
                     f"{tag}_score": s2.get("score")}
                m.update({f"{tag}_{k}": v for k, v in floor_metrics(s1, plan).items()})
                net = s1["stair_core"]["under_stair"]["net_ground_sqft"]
                void = (s1.get("access_core") or {}).get("void_sqft", 0.0) or 0.0
                m[f"{tag}_occupied_sqft"] = round(net + s1["stair"]["area_sqft"] + void, 1)
                return m

            row = {"lot_id": lot_id, "household_id": c["household_id"], "profile": c["profile"],
                   "scheme_id": c["scheme_id"], "rank": c["rank"], "candidates_kept": len(trials),
                   "zoned_candidates": len(zoned), "pareto": len(front),
                   "strategies_zoned": ",".join(sorted({t["strategy"] for t in zoned})),
                   "pick_reason": (pick or {}).get("reason"),
                   "new_arrival": (pick or {}).get("arrival_kind"), "new_half_bath": (pick or {}).get("half_bath"),
                   "discards": json.dumps({k: v for k, v in sorted(stats.items()) if not k.endswith("placed")})}
            row.update(metrics("cur", base))
            row.update(metrics("new", pick))
            for st in ("A", "B", "C", "D"):
                mine = [t for t in zoned if t["strategy"] == st]
                if mine:
                    best = min(mine, key=lambda t: (chosen(t["s2"])["routes"]["total_ft"], t["occupied"]))
                    fm = floor_metrics(best["s1"], plan)
                    row.update({f"{st}_route_ft": chosen(best["s2"])["routes"]["total_ft"],
                                f"{st}_occupied_sqft": round(best["occupied"], 1), f"{st}_light": best["light"],
                                f"{st}_stair": best["s1"]["stair"]["stair_id"],
                                f"{st}_free_rect_ground": fm["free_rect_ground"],
                                f"{st}_free_rect_upper": fm["free_rect_upper"],
                                f"{st}_in_front": t_in(best, front)})
            rows.append(row)
            records.append((row, base, pick))
    elapsed = time.time() - t0
    fields = sorted({k for r in rows for k in r}, key=lambda k: (not k.startswith(("lot", "house", "prof", "sch", "rank")), k))
    with (out / "spike_cells.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    summary = summarize(rows, elapsed)
    (out / "spike_summary.json").write_text(json.dumps(summary, indent=1))
    sheets(records, out, args.sheets)
    print(json.dumps(summary, indent=1))
    return 0


def summarize(rows, elapsed) -> dict:
    def med(key, sel=None):
        vals = [r[key] for r in rows if r.get(key) is not None and (sel is None or sel(r))]
        return round(float(np.median(vals)), 1) if vals else None

    both = lambda r: r.get("cur_zoned") and r.get("new_zoned")
    return {
        "cells": len(rows), "seconds": round(elapsed, 1),
        "zoned": {"current": sum(bool(r.get("cur_zoned")) for r in rows),
                  "new": sum(bool(r.get("new_zoned")) for r in rows)},
        "stair_mix": {"current": dict(Counter(r.get("cur_stair") for r in rows if r.get("cur_zoned"))),
                      "new": dict(Counter(r.get("new_stair") for r in rows if r.get("new_zoned")))},
        "strategy_new": dict(Counter(r.get("new_strategy") for r in rows if r.get("new_zoned"))),
        "light": {"current": dict(Counter(r.get("cur_light") for r in rows if r.get("cur_zoned"))),
                  "new": dict(Counter(r.get("new_light") for r in rows if r.get("new_zoned")))},
        "median_where_both_zoned": {
            "route_total_ft": [med("cur_route_ft", both), med("new_route_ft", both)],
            "route_to_stair_ft": [med("cur_route_stair_ft", both), med("new_route_stair_ft", both)],
            "free_rect_ground_sqft": [med("cur_free_rect_ground", both), med("new_free_rect_ground", both)],
            "free_rect_upper_sqft": [med("cur_free_rect_upper", both), med("new_free_rect_upper", both)],
            "occupied_sqft": [med("cur_occupied_sqft", both), med("new_occupied_sqft", both)],
            "zoning_score": [med("cur_score", both), med("new_score", both)]},
        "by_strategy": {st: {"zoned": sum(1 for r in rows if r.get(f"{st}_route_ft") is not None),
                             "in_pareto": sum(1 for r in rows if r.get(f"{st}_in_front")),
                             "route_ft": med(f"{st}_route_ft"), "occupied_sqft": med(f"{st}_occupied_sqft"),
                             "free_rect_ground": med(f"{st}_free_rect_ground"),
                             "free_rect_upper": med(f"{st}_free_rect_upper"),
                             "light": dict(Counter(r.get(f"{st}_light") for r in rows if r.get(f"{st}_light"))),
                             "stairs": dict(Counter(r.get(f"{st}_stair") for r in rows if r.get(f"{st}_stair")))}
                        for st in ("A", "B", "C", "D")},
        "by_lot": {lot: {"cells": sum(r["lot_id"] == lot for r in rows),
                         "zoned_current": sum(bool(r.get("cur_zoned")) for r in rows if r["lot_id"] == lot),
                         "zoned_new": sum(bool(r.get("new_zoned")) for r in rows if r["lot_id"] == lot)}
                   for lot in sorted({r["lot_id"] for r in rows})},
    }


# ------------------------------------------------------------------ blind side-by-side sheets


ZONE = {"social": "#ffb74d", "private": "#7986cb", "kitchen": "#e57373", "service": "#a1887f",
        "circulation": "#e0e0e0"}


def _draw(ax, floor_poly, units, extra, title):
    def rings(p):
        if not p:
            return []
        return [p["coordinates"][0]] if p["type"] == "Polygon" else [q[0] for q in p["coordinates"]]

    def fill(p, **kw):
        for r in rings(p):
            xs, ys = zip(*r)
            ax.fill(xs, ys, **kw)

    fill(floor_poly, color="#ffffff", ec="#52514e", lw=0.6)
    for u in units:
        fill(u["polygon"], color=ZONE.get(u["zone"], "#eeeeee"), ec="#ffffff", lw=0.8)
    for p, kw in extra:
        fill(p, **kw)
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_title(title, fontsize=6, loc="left")


def sheets(records, out: Path, n: int) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    both = [r for r in records if r[2] is not None and r[1]["s2"]["status"] == ZONED]
    rnd = random.Random(20261010)
    sample = rnd.sample(both, min(n, len(both)))
    key = []
    per_page = 5
    for page in range(0, len(sample), per_page):
        chunk = sample[page:page + per_page]
        fig, axes = plt.subplots(len(chunk), 4, figsize=(9.5, 2.6 * len(chunk)), squeeze=False)
        for row_axes, (row, base, new) in zip(axes, chunk):
            order = [("X", base), ("Y", new)] if rnd.random() < 0.5 else [("X", new), ("Y", base)]
            key.append({"cell": f"{row['lot_id']} {row['household_id']} {row['profile']} {row['scheme_id']}",
                        "X": "current" if order[0][1] is base else "new",
                        "Y": "current" if order[1][1] is base else "new"})
            for k, (label, rec) in enumerate(order):
                s1, s2 = rec["s1"], rec["s2"]
                opt = s2["options"][s2["chosen_option"]]
                ac = s1.get("access_core") or {}
                stair = [(s1["stair"]["polygon"], {"color": "#0b0b0b"})]
                door = [(ac.get("vestibule"), {"fill": False, "ec": "#008300", "lw": 1.0})] if ac.get("vestibule") else []
                void = [(ac.get("void"), {"color": "#4fc3f7"})] if ac.get("void") else []
                garage = [(s1["ground"].get("garage_polygon"), {"color": "#c9c7c0", "hatch": "///", "ec": "#52514e"})]
                _draw(row_axes[2 * k], s1["levels"][0]["polygon"], opt["ground"]["units"], garage + door + stair,
                      f"{label} · planta baja · {row['household_id']} {row['profile']}")
                _draw(row_axes[2 * k + 1], s1["levels"][1]["polygon"], s2["upper"]["units"], stair + void,
                      f"{label} · planta alta")
        fig.tight_layout()
        fig.savefig(out / f"blind_{page // per_page + 1:02d}.png", dpi=150)
        plt.close(fig)
    (out / "blind_key.json").write_text(json.dumps(key, indent=1))


if __name__ == "__main__":
    sys.exit(main())
