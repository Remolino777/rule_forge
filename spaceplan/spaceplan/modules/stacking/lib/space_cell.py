"""Stage S2.1 of one zoned cell (step 6.7a): spaces and doors inside the S2 zones of both floors.

    per floor  -> options of every zone unit (unit_layout), combinations in ranked order (best local scores first),
                  doors (door_placement), then the floor checks: every space reached, the stair end received by an
                  allowed space (K01 upstairs, the chosen start option of K02 downstairs), the hard pairs of the
                  matrix on the door graph (space_relations, K05 over the base); valid layouts scored;
    cell       -> best pair (ground x upper) by floor scores and the pairs measured through the stair; metrics
                  (depth of the suite from the entry, rooms crossed); traces of the normative (C01, C06, O01-O03, S08)
                  and client (K01, K02, K04, K05) rules, closing what S2 left deferred_to_S2.1.

Only reads the S1 and S2 blocks of the cell, the area matrix's space split and the catalogs.
"""

from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass
from typing import Any

import numpy as np
from shapely.geometry import LineString, Point, box

from spaceplan.core.lib_aux.allocation import ranked_product
from spaceplan.modules.stacking.lib.door_placement import (
    CLOSET_DOOR,
    EXTERIOR,
    FIXED_DOOR,
    GARAGE_DOOR,
    OPENING,
    STAIR_LINK,
    FloorLayout,
    compose,
    place_doors,
)
from spaceplan.modules.stacking.lib.floor_frame import GROUND, UPPER, cell_floors
from spaceplan.modules.stacking.lib.front_yard import front_yard
from spaceplan.modules.stacking.lib.lot_plan import LotPlan
from spaceplan.modules.stacking.lib.space_relations import evaluate_space_floor, space_graph
from spaceplan.modules.stacking.lib.space_rules import (
    ESCAPE_RULE,
    FACADE_RULE,
    GARAGE_OPENINGS_RULE,
    HABITABLE_DIMENSION_RULE,
    HALF_BATH_RULE,
    HALL_WIDTH_RULE,
    TOP_DOOR_RULE,
    SpaceRules,
)
from spaceplan.modules.stacking.lib.stair_access import FAIL, NOT_EVALUATED, PASS, trace
from spaceplan.modules.stacking.lib.unit_frame import (
    CIRCULATION_TYPES,
    OUT,
    SpaceFloor,
    space_floor,
)
from spaceplan.modules.stacking.lib.unit_layout import UnitLayout
from spaceplan.modules.stacking.lib.zone_relations import FloorGraph, ZoneMatrix, vertical_pairs
from spaceplan.modules.stacking.lib_aux.plan_geometry import polygon_json
from spaceplan.modules.stacking.lib_aux.space_grid import exterior_run, mask_polygon

SPACED, NO_VALID_LAYOUT, NOT_EVALUATED_S21 = "spaced", "no_valid_layout", "not_evaluated"
S21_STATUSES = (SPACED, NO_VALID_LAYOUT, NOT_EVALUATED_S21)
TOP_RULE, BOTTOM_RULE, RELATIONS_RULE = "K01-STAIR-TOP-ARRIVAL", "K02-STAIR-BOTTOM-START", "K05-STAIR-RELATIONS"
ARRIVAL_TYPES = {"family_room": ("family_room",), "upper_vestibule": CIRCULATION_TYPES, "hall": CIRCULATION_TYPES}


@dataclass(frozen=True)
class S21Context:
    scat: Any
    catalog: Any
    matrix: ZoneMatrix
    rules: SpaceRules
    crc: Any
    openings: Any
    stairs: Any
    client: Any
    capacity: Any = None                    # SDMC capacity ruleset (Z10, Z11) for the front yard


# ------------------------------------------------------------------ one floor


@dataclass
class FloorResult:
    layout: FloorLayout
    graph: FloorGraph
    relations: dict[str, Any]
    parts: dict[str, float]
    score: float


def _patio_nodes(layout: FloorLayout, rules: SpaceRules, garden_side: str) -> set[int]:
    """Spaces of the ground floor with a garden-facade wall at least an opening wide."""
    if layout.floor.level != GROUND:
        return set()
    out = layout.floor.outside
    flags = {"low_x": np.roll(out, 1, axis=1), "high_x": np.roll(out, -1, axis=1),
             "low_y": np.roll(out, 1, axis=0), "high_y": np.roll(out, -1, axis=0)}
    zero = np.zeros_like(out)
    ext = tuple(flags[s] if s == garden_side else zero for s in ("low_x", "high_x", "low_y", "high_y"))
    need = rules.door_ft["opening"] / layout.floor.res
    nodes = set()
    for k, s in enumerate(layout.specs):
        if s.fixed or s.zone == "garage":
            continue
        if exterior_run(layout.labels == k, ext) >= need - 1e-9:
            nodes.add(k)
    return nodes


def _floor_parts(layout: FloorLayout, rel: dict[str, Any], rules: SpaceRules, catalog) -> dict[str, float]:
    opts = layout.options
    specs = layout.specs
    circ = catalog.data["circulation"]
    target, warn = float(circ["target_fraction"]), float(circ["warn_fraction"])
    lab = layout.labels
    habitable_cells = sum(int((lab == k).sum()) for k, s in enumerate(specs)
                          if not s.fixed or s.circulation and s.space_type != "stair")
    circ_cells = sum(int((lab == k).sum()) for k, s in enumerate(specs) if s.circulation and s.space_type != "stair")
    frac = circ_cells / habitable_cells if habitable_cells else 0.0
    circulation = 1.0 if frac <= target else max(0.0, 1.0 - (frac - target) / max(warn - target, 1e-9))
    sleeping = [k for k, s in enumerate(specs) if s.space_type in rules.sleeping_types]
    closet_types = {rules.closet_type, "walk_in_closet"}
    with_closet = sum(1 for k in sleeping if any(specs[j].space_type in closet_types for j in layout.adj.get(k, ())))
    return {"relations": rel["score"],
            "shape": float(np.mean([o.parts.get("shape", 1.0) for o in opts])) if opts else 1.0,
            "exterior": float(np.mean([o.parts.get("exterior", 1.0) for o in opts])) if opts else 1.0,
            "circulation": circulation,
            "closets": with_closet / len(sleeping) if sleeping else 1.0,
            "circulation_fraction": frac}


def _floor_score(parts: dict[str, float], weights: dict[str, float]) -> float:
    keys = [k for k in weights if k != "vertical"]
    total = sum(weights[k] for k in keys) or 1.0
    return sum(weights[k] * parts[k] for k in keys) / total


def search_floor(floor: SpaceFloor, ctx: S21Context) -> tuple[list[FloorResult], dict[str, Any]]:
    rules, s21 = ctx.rules, ctx.rules.s21
    summary: dict[str, Any] = {"units": {}, "combinations": 0, "valid": 0, "first_violations": {}}
    per_unit = []
    for u in floor.units:
        ul = UnitLayout(floor, u, rules, ctx.catalog, ctx.matrix)
        opts = ul.options()
        summary["units"][u.unit_id] = {"options": len(opts),
                                       "first_violations": dict(sorted(ul.first_violations.items()))}
        if not opts:
            top = max(ul.first_violations.items(), key=lambda kv: kv[1])[0] if ul.first_violations else "no option"
            summary["first_violations"][f"unit:{u.unit_id}:{top}"] = 1
            return [], summary
        per_unit.append(opts)
    garden = ctx.scat.s2["facade_sides"]["garden"][0]
    fails: Counter = Counter()
    found: list[FloorResult] = []
    stop = int(s21["search"]["stop_after_valid"])
    for idx in ranked_product([len(o) for o in per_unit], int(s21["search"]["max_combinations_per_floor"])):
        summary["combinations"] += 1
        layout = compose(floor, tuple(o[i] for o, i in zip(per_unit, idx)))
        place_doors(layout, rules, ctx.matrix)
        if not layout.violations:
            land = layout.specs[layout.landing_node]
            if land.space_type not in floor.receiving:
                layout.violations.append(f"landing:{land.space_type}")
        rel = None
        if not layout.violations:
            graph = space_graph(layout, ctx.matrix, _patio_nodes(layout, rules, garden))
            rel = evaluate_space_floor(ctx.matrix, layout, graph)
            if rel["hard_failed"]:
                layout.violations.append(f"matrix:{rel['hard_failed'][0]}")
        if layout.violations:
            fails[layout.violations[0]] += 1
            continue
        parts = _floor_parts(layout, rel, rules, ctx.catalog)
        found.append(FloorResult(layout, graph, rel, parts, _floor_score(parts, s21["weights"])))
        if len(found) >= stop:
            break
    summary["valid"] = len(found)
    summary["first_violations"] = dict(fails.most_common())
    found.sort(key=lambda r: -r.score)
    return found, summary


# ------------------------------------------------------------------ the cell


def _receiving(s2: dict[str, Any], option: dict[str, Any]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    ground = tuple(option["receiving"]) + tuple(t for t in CIRCULATION_TYPES if set(option["receiving"]) & {"hall", "foyer"})
    upper = tuple(t for kind in (s2.get("arrival") or {}).get("order", ["hall"]) for t in ARRIVAL_TYPES.get(kind, ()))
    return tuple(dict.fromkeys(ground)), tuple(dict.fromkeys(upper))


def _depths(g: FloorResult, u: FloorResult) -> dict[str, Any]:
    """Doors from the main-door vestibule to each space of both floors (the stair counted as one step)."""
    gl, ul = g.layout, u.layout
    nodes = {("g", k) for k in range(len(gl.specs))} | {("u", k) for k in range(len(ul.specs))}
    adj: dict = {n: set() for n in nodes}
    for tag, lay in (("g", gl), ("u", ul)):
        for a, bs in lay.adj.items():
            for b in bs:
                adj[(tag, a)].add((tag, b))
    gs = next((k for k, s in enumerate(gl.specs) if s.space_type == "stair"), None)
    us = next((k for k, s in enumerate(ul.specs) if s.space_type == "stair"), None)
    if gs is not None and us is not None:
        adj[("g", gs)].add(("u", us))
        adj[("u", us)].add(("g", gs))
    root = ("g", gl.root)
    dist = {root: 0}
    queue = deque([root])
    while queue:
        x = queue.popleft()
        for y in adj[x]:
            if y not in dist:
                dist[y] = dist[x] + 1
                queue.append(y)
    out = {}
    for tag, lay in (("g", gl), ("u", ul)):
        for k, s in enumerate(lay.specs):
            if not s.fixed:
                out[s.space_id] = dist.get((tag, k))
    suite = [v for sid, v in out.items() if v is not None and any(
        s.space_id == sid and s.space_type == "primary_suite" for s in gl.specs + ul.specs)]
    return {"by_space": out, "primary_suite_from_entry": min(suite) if suite else None}


def _combine(ctx: S21Context, ground: list[FloorResult], upper: list[FloorResult]):
    w = ctx.rules.s21["weights"]
    wv = w["vertical"] / (sum(w.values()) or 1.0)
    keep = int(ctx.rules.s21["search"]["keep_alternatives"])
    best = None
    for g in ground[:keep]:
        for u in upper[:keep]:
            v = vertical_pairs(ctx.matrix, g.graph, u.graph, g.layout.landing_node, u.layout.landing_node,
                               ctx.rules.s21["vertical_depth_ok"])
            total = (1.0 - wv) * 0.5 * (g.score + u.score) + wv * v["score"]
            if best is None or total > best[0] + 1e-12:
                best = (total, g, u, v)
    return best


def _exterior(s1: dict[str, Any], plan: LotPlan, lot_local, site_plan: dict | None, ctx: S21Context) -> dict:
    """What the secondary door needs outside: the lot (local), the rear deck of the site plan, S13 and R311.3."""
    from shapely.geometry import shape as _shape

    deck = None
    if site_plan:
        part = site_plan.get("site_partition") or {}
        opts = [o for o in part.get("options", []) if o.get("backyard")]
        opt = next((o for o in opts if o.get("option_id") == part.get("selected_option_id")), None) or \
            (opts[0] if opts else None)
        for e in ((opt or {}).get("backyard") or {}).get("elements", []):
            if e.get("element") == "rear_deck" and e.get("status") == "placed" and e.get("polygon"):
                deck = plan.frame.to_local(_shape(e["polygon"]))
    s13 = ctx.stairs.params("S13-EXTERIOR-WALL-OPENINGS")
    return {"lot": lot_local, "deck": deck, "no_openings_below_ft": float(s13["not_permitted_below_ft"]),
            "landing_ft": float(ctx.openings.params("O05-EXTERIOR-LANDING")["min_depth_in"]) / 12.0}


def space_cell(rows: list[dict[str, Any]], s1: dict[str, Any], s2: dict[str, Any], plan: LotPlan,
               profile: str | None, ctx: S21Context, lot_local=None, site_plan: dict | None = None) -> dict[str, Any]:
    """Stage S2.1 block of a cell zoned by S2 (`rows` = the area-matrix space split of the cell, after the program
    adjustment of stage S2.1; `lot_local` and `site_plan` give the secondary door its outside)."""
    out: dict[str, Any] = {"stage": "S2.1", "warnings": []}
    if not s2 or s2.get("status") != "zoned" or not rows:
        return {**out, "status": NOT_EVALUATED_S21, "rule_traces": []}
    option = s2["options"][s2["chosen_option"]]
    floors = cell_floors(s1, plan)
    res = float(ctx.scat.s2["grid_ft"])
    g_recv, u_recv = _receiving(s2, option)
    alts = s2.get("_alternatives") or {"upper": [s2["upper"]], "ground": [option["ground"]]}

    exterior = _exterior(s1, plan, lot_local, site_plan, ctx)

    def search(level: int, blocks: list[dict[str, Any]], recv, variant_of):
        tried = []
        for k, block in enumerate(blocks):
            fl = space_floor(level, floors, block, rows, plan, ctx.catalog, ctx.rules, ctx.matrix, res, profile, recv,
                             variant_of(block), exterior if level == GROUND else None)
            found, summary = search_floor(fl, ctx)
            summary["s2_alternative"] = k
            tried.append(summary)
            if found:
                return found, summary, k, fl.notes, tried
        return [], tried[0] if tried else {}, None, [], tried

    u_found, u_summary, u_alt, u_notes, u_tried = search(UPPER, alts["upper"], u_recv, lambda b: "upper")
    if u_found:
        g_found, g_summary, g_alt, g_notes, g_tried = search(GROUND, alts["ground"], g_recv, lambda b: b["variant"])
    else:
        g_found, g_summary, g_alt, g_notes, g_tried = [], {"skipped": "upper floor not spaced"}, None, [], []
    out["warnings"] += u_notes + g_notes
    out["search"] = {"ground": g_summary, "upper": u_summary,
                     "s2_alternatives_tried": {"upper": len(u_tried), "ground": len(g_tried)}}
    out["s2_alternative"] = {"upper": u_alt, "ground": g_alt}
    if not u_found or not g_found:
        summary = u_summary if not u_found else g_summary
        first = next(iter(summary.get("first_violations", {})), "no layout")
        out.update({"status": NO_VALID_LAYOUT, "failed_floor": "upper" if not u_found else "ground",
                    "first_violation": first})
        out["rule_traces"] = _fail_traces(ctx, first)
        return out
    total, g, u, vert = _combine(ctx, g_found, u_found)
    nd = int(ctx.scat.geometry["round_ft"])
    out.update({
        "status": SPACED,
        "score": round(total, 4),
        "score_parts": {"ground": {k: round(v, 4) for k, v in g.parts.items()},
                        "upper": {k: round(v, 4) for k, v in u.parts.items()},
                        "vertical": round(vert["score"], 4)},
        "ground": _floor_block(g, plan, ctx, nd),
        "upper": _floor_block(u, plan, ctx, nd),
        "vertical": {"score": round(vert["score"], 4), "pairs": vert["pairs"]},
        "depth": _depths(g, u),
    })
    if lot_local is not None and ctx.capacity is not None:
        out["site"] = front_yard(s1, plan, lot_local, ctx.capacity, ctx.openings, ctx.catalog, ctx.scat)
    out["k10"] = _k10_summary(g, u, rows)
    out["rule_traces"] = _traces(ctx, g, u, s2, out)
    return out


def _k10_summary(g: FloorResult, u: FloorResult, rows: list[dict[str, Any]]) -> dict[str, Any]:
    en_suite, shared = {}, []
    for lay in (g.layout, u.layout):
        for s in lay.specs:
            if s.between:
                shared.append({"bath": s.space_id, "bedrooms": list(s.between)})
            elif s.host and s.space_type in ("bathroom", "primary_bath"):
                en_suite[s.space_id] = s.host
    beds = [r["space_id"] for r in rows if r["space_type"] in ("bedroom", "primary_suite")]
    return {"bedrooms": len(beds), "en_suite": en_suite, "shared": shared}


# ------------------------------------------------------------------ contract blocks


def _wall_point(floor: SpaceFloor, run, t: float) -> tuple[float, float]:
    g = floor.grid
    if run.vertical:
        return g.x0 + run.k * g.res, g.y0 + t * g.res
    return g.x0 + t * g.res, g.y0 + run.k * g.res


def _door_block(layout: FloorLayout, d, plan: LotPlan, nd: int) -> dict[str, Any]:
    f, specs = layout.floor, layout.specs
    block: dict[str, Any] = {"a": specs[d.a].space_id, "b": "exterior" if d.b == EXTERIOR else specs[d.b].space_id,
                             "kind": d.kind}
    if d.run is None:
        return block
    p0, p1 = _wall_point(f, d.run, d.t0), _wall_point(f, d.run, d.t1)
    seg = plan.to_world(LineString([p0, p1]))
    block.update({"clear_width_in": round(d.clear_ft * 12.0, 1),
                  "segment": [[round(c, nd) for c in xy] for xy in seg.coords]})
    if d.hinge_t is not None and d.kind not in (OPENING, STAIR_LINK):
        hx, hy = _wall_point(f, d.run, d.hinge_t)
        r = d.leaf_cells * f.res
        if d.run.vertical:
            qx = (hx, hx + r) if d.into_high else (hx - r, hx)
            qy = (hy, hy + r) if d.toward_plus else (hy - r, hy)
        else:
            qx = (hx, hx + r) if d.toward_plus else (hx - r, hx)
            qy = (hy, hy + r) if d.into_high else (hy - r, hy)
        swing = Point(hx, hy).buffer(r, 16).intersection(box(qx[0], qy[0], qx[1], qy[1]))
        hinge = plan.to_world(Point(hx, hy))
        block.update({"swing_into": specs[d.a].space_id, "leaf_ft": round(r, 3),
                      "hinge": [round(hinge.x, nd), round(hinge.y, nd)],
                      "swing": polygon_json(plan.to_world(swing), nd)})
        if d.kind == GARAGE_DOOR:
            block["self_closing"] = True
    return block


def _floor_block(r: FloorResult, plan: LotPlan, ctx: S21Context, nd: int) -> dict[str, Any]:
    lay, f = r.layout, r.layout.floor
    ca = f.res * f.res
    spaces = []
    for k, s in enumerate(lay.specs):
        if s.space_type == "stair":
            continue
        m = lay.labels == k
        n = int(m.sum())
        if not n:
            continue
        ext = (np.roll(lay.labels, 1, 1) == OUT, np.roll(lay.labels, -1, 1) == OUT,
               np.roll(lay.labels, 1, 0) == OUT, np.roll(lay.labels, -1, 0) == OUT)
        spaces.append({"space_id": s.space_id, "space_type": s.space_type, "zone": s.zone, "unit_id": s.unit_id,
                       "area_sqft": round(n * ca, 1), "target_sqft": round(s.target_sqft, 1),
                       "exterior_ft": round(exterior_run(m, ext) * f.res, 2), "host": s.host,
                       "fixed": s.fixed, "synthetic": s.synthetic,
                       "polygon": polygon_json(plan.to_world(mask_polygon(m, f.grid)), nd)})
    return {"level": f.level, "variant": f.variant,
            "root": lay.specs[lay.root].space_id, "landing_space": lay.specs[lay.landing_node].space_id,
            "hall_sides": {lay.floor.units[[u.index for u in f.units].index(o.unit)].unit_id: o.hall_side
                           for o in lay.options},
            "spaces": spaces,
            "closets_in_rooms": sorted(c for o in lay.options for c in o.parts.get("closets_in_rooms", [])),
            "patio_exit": None if not lay.patio_exit else {
                k: (polygon_json(plan.to_world(v), nd) if k == "landing" else v)
                for k, v in lay.patio_exit.items() if k != "door"},
            "doors": [_door_block(lay, d, plan, nd) for d in lay.doors],
            "score": round(r.score, 4),
            "relations": {"hard_failed": r.relations["hard_failed"],
                          "met": sorted(p for p, v in r.relations["results"].items() if v == "met")}}


# ------------------------------------------------------------------ traces


def _fail_traces(ctx: S21Context, first: str) -> list[dict[str, Any]]:
    """The rule that stopped the search first (when it maps to one), the rest not evaluated."""
    rule = None
    kind = first.split(":")[0] if ":" in first else first
    if first.startswith("unit:"):
        reason = first.split(":")[2] if first.count(":") >= 2 else ""
        rule = (FACADE_RULE, ctx.openings) if reason.startswith("facade") else (
            HABITABLE_DIMENSION_RULE, ctx.crc) if reason.startswith(("min_side", "min_area")) else None
    elif kind == "landing":
        rule = (TOP_RULE, ctx.client)
    elif kind == "matrix":
        rule = (RELATIONS_RULE, ctx.client)
    elif kind == "door" and "half_bath" in first:
        rule = (HALF_BATH_RULE, ctx.client)
    elif kind == "door" and "garage" in first:
        rule = (GARAGE_OPENINGS_RULE, ctx.openings)
    elif kind == "exit":
        rule = ("O05-EXTERIOR-LANDING", ctx.openings)
    elif kind == "k10":
        rule = ("K10-BATHS-PER-BEDROOM", ctx.client)
    out = []
    if rule is not None:
        out.append(trace(rule[1], rule[0], FAIL, f"first violation: {first}"))
    for rid, rs in ((RELATIONS_RULE, ctx.client),):
        if rule is None or rule[0] != rid:
            out.append(trace(rs, rid, NOT_EVALUATED, "no valid space layout"))
    return out


def _traces(ctx: S21Context, g: FloorResult, u: FloorResult, s2: dict[str, Any],
            block: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    rules = ctx.rules
    out = []
    block = block or {}
    ex = g.layout.patio_exit
    if ex:
        out.append(trace(ctx.openings, "O05-EXTERIOR-LANDING", PASS,
                         f"secondary door ({ex['kind']}, {ex['width_in']:g} in) from {ex['space']} on the {ex['facade']} "
                         f"facade with a landing outside" + (" on the rear deck" if ex["on_deck"] else "")))
    site = block.get("site") or {}
    for c in site.get("checks", []):
        rs = ctx.openings if c["rule_id"].startswith("O0") else ctx.capacity
        out.append(trace(rs, c["rule_id"], PASS if c["passes"] else FAIL,
                         f"main entry and front yard: value {c['value']} against {c['limit']}"))
    k10 = block.get("k10") or {}
    if k10:
        out.append(trace(ctx.client, "K10-BATHS-PER-BEDROOM", PASS,
                         f"{len(k10['en_suite'])} baths en suite (onto their room only), {len(k10['shared'])} shared "
                         f"between two bedrooms (onto the hall)"))
    layouts = (g.layout, u.layout)
    specs = [s for lay in layouts for s in lay.specs]
    out.append(trace(ctx.crc, HABITABLE_DIMENSION_RULE, PASS,
                     f"every habitable room has a rectangle of at least {rules.habitable_min_side_ft:g} ft and "
                     f"{rules.habitable_min_sqft:g} sq ft (kitchen exempt as in C01)"))
    out.append(trace(ctx.crc, HALL_WIDTH_RULE, PASS,
                     f"halls {rules.hall_width_accessible_ft if g.layout.floor.accessible else rules.hall_width_ft:g} "
                     f"ft wide (normative {rules.hall_min_ft:g} ft)"))
    sleeping = [s.space_id for s in specs if s.space_type in rules.sleeping_types]
    out.append(trace(ctx.openings, ESCAPE_RULE, PASS,
                     f"{len(sleeping)} sleeping rooms on an exterior wall long enough for the escape opening"))
    habitable = [s.space_id for s in specs if s.habitable and not s.fixed]
    out.append(trace(ctx.openings, FACADE_RULE, PASS,
                     f"{len(habitable)} habitable rooms with the exterior wall C03 glazing needs"))
    garage_doors = [d for d in g.layout.doors if d.kind == GARAGE_DOOR]
    if any(s.zone == "garage" or s.space_type.startswith("garage") for s in g.layout.specs):
        to = [g.layout.specs[d.a].space_type for d in garage_doors]
        out.append(trace(ctx.openings, GARAGE_OPENINGS_RULE, PASS,
                         f"garage door onto {', '.join(to)}; self-closing and self-latching; no sleeping room"))
    out.append(trace(ctx.stairs, TOP_DOOR_RULE, PASS, "no door swings over the stair or its landings"))
    out.append(trace(ctx.client, TOP_RULE, PASS,
                     f"the stair arrives into {u.layout.specs[u.layout.landing_node].space_id}"))
    out.append(trace(ctx.client, BOTTOM_RULE, PASS,
                     f"option {s2['chosen_option']}: the start lands in {g.layout.specs[g.layout.landing_node].space_id}"))
    hb = [(lay, d) for lay in layouts for d in lay.doors if d.b != EXTERIOR and (
          lay.specs[d.a].space_type in rules.half_bath_types or lay.specs[d.b].space_type in rules.half_bath_types)]
    if hb:
        to = sorted({lay.specs[d.b if lay.specs[d.a].space_type in rules.half_bath_types else d.a].space_type
                     for lay, d in hb})
        out.append(trace(ctx.client, HALF_BATH_RULE, PASS, f"half bath door onto {', '.join(to)} only"))
    closed = sorted({p for f in (s2.get("upper") or {}, s2["options"][s2["chosen_option"]]["ground"])
                     for p in f.get("matrix_deferred", [])})
    out.append(trace(ctx.client, RELATIONS_RULE, PASS,
                     "space-level pairs met on the door graph" + (f"; closes {', '.join(closed)}" if closed else "")))
    return out


__all__ = [
    "CLOSET_DOOR",
    "FIXED_DOOR",
    "NOT_EVALUATED_S21",
    "NO_VALID_LAYOUT",
    "S21_STATUSES",
    "SPACED",
    "S21Context",
    "search_floor",
    "space_cell",
]
