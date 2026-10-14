"""Stage S2 of one drawn cell (step 6.7a): zoning of both floors around the stair core and the A/B/C start portfolio.

    upper floor  -> receiving space at the top (K01: family room / vestibule / hall), search, best realizations
    ground floor -> per use of the space under the stair (half bath with its vestibule, or storage with the half bath
                    relocated into the circulation zone), search; each start option (K02: A vestibulated, B living,
                    C kitchen) keeps the best realization whose bottom landing falls in a space it allows
    cell         -> per option: best pair (ground x upper) by floor scores and the pairs measured through the stair;
                    the preferred option when it is feasible, else the first feasible; traces K01-K05

Structural frame (step S2.2g, `structure.frame.enabled`): the cell's frame variants (lib/structural_frame) are
built first; both floors are zoned on the same frame (lib/frame_bands) and a ground floor pairs only with uppers of
its own frame. When no frame zones the cell, the free zoning of S2.2f runs instead if the frame rule is soft (the
cell says so); a hard frame rule leaves the cell not zoned.

Only reads the S1 block, the space split of the area matrix and the catalogs: no lotcap, site or areas code runs.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

import numpy as np
from shapely.geometry.base import BaseGeometry

from spaceplan.modules.stacking.lib.core_zoning import (
    FloorRules,
    FloorSearch,
    FrameGuide,
    Realization,
    StructureGuide,
    zone_labels,
)
from spaceplan.modules.stacking.lib.floor_frame import (
    CIRCULATION,
    GROUND,
    HALF_BATH_USE,
    STORAGE_USE,
    UPPER,
    FloorFrame,
    arrival_of,
    cell_floors,
    floor_units,
    ground_frame,
    upper_arrival,
    upper_frame,
)
from spaceplan.modules.stacking.lib.frame_bands import ROOF
from spaceplan.modules.stacking.lib.frame_positions import optimize_pair, positions_settings
from spaceplan.modules.stacking.lib.lot_plan import LotPlan
from spaceplan.modules.stacking.lib.routes import route_lengths, stair_walk_ft, two_floor_routes
from spaceplan.modules.stacking.lib.stair_access import (
    DEFERRED_S21,
    FAIL,
    NOT_EVALUATED,
    PASS,
    trace,
)
from spaceplan.modules.stacking.lib.structural_frame import (
    SPINE,
    Frame,
    build_frames,
    frame_settings,
)
from spaceplan.modules.stacking.lib.zone_relations import ZoneMatrix, vertical_pairs
from spaceplan.modules.stacking.lib_aux.plan_geometry import polygon_json
from spaceplan.modules.stacking.lib_aux.structure_grid import edge_walls, grid_offset, window
from spaceplan.modules.stacking.lib_aux.zone_grid import OUTSIDE, bounding_cells

ZONED, UPPER_NOT_ZONED, GROUND_NOT_ZONED, NOT_ZONED, NO_SPACE_SPLIT = (
    "zoned", "upper_not_zoned", "ground_not_zoned", "not_zoned", "no_space_split")
S2_STATUSES = (ZONED, UPPER_NOT_ZONED, GROUND_NOT_ZONED, NOT_ZONED, NO_SPACE_SPLIT)
NEXT_STAGE = "S2.1"
TOP_RULE, BOTTOM_RULE, UNDER_KITCHEN_RULE, HALF_BATH_RULE, RELATIONS_RULE = (
    "K01-STAIR-TOP-ARRIVAL", "K02-STAIR-BOTTOM-START", "K03-UNDER-STAIR-KITCHEN", "K04-HALF-BATH-VESTIBULE",
    "K05-STAIR-RELATIONS")


@dataclass(frozen=True)
class S2Context:
    scat: Any
    catalog: Any
    client_rs: Any
    matrix: ZoneMatrix
    ground_rules: FloorRules
    upper_rules: FloorRules
    routes: dict[str, Any] | None = None       # stage S1.2: route targets and passable zones (client step 7)
    stair_flights: dict[str, int] = field(default_factory=dict)   # stair_id -> flights (stair walk of the routes)
    alternatives: int = 0                      # stage S2.1: zonings of each floor kept in memory (0: none)
    structure: dict[str, Any] | None = None    # S2.2f: structure settings (structure_settings); None: off


def floor_rules(catalog, s2: dict[str, Any], floor: str, stair_hall: dict[str, Any] | None = None) -> FloorRules:
    prof = catalog.data["zoning_profiles"]["house"]
    topo = s2["topology"][floor]
    return FloorRules(
        door_contact_ft=float(catalog.data["circulation"]["door_contact_ft"]),
        area_tolerance=float(s2["area_tolerance_fraction"]),
        receiving_min_share=float(s2["receiving_min_share"]),
        private_opens_to=frozenset(s2["zone_doors"]["private_opens_to"]),
        garage_opens_to=frozenset(s2["zone_doors"]["garage_opens_to"]),
        entry_zone=prof["entry"]["zone"], entry_min_overlap_ft=float(prof["entry"]["min_overlap_ft"]),
        anchors=tuple(prof["anchors"]),
        facade_sides={k: tuple(v) for k, v in s2["facade_sides"].items() if isinstance(v, list)},
        max_aspect=float(catalog.data["zoning"]["max_aspect_ratio"]),
        weights={k: float(v) for k, v in s2["weights"].items()},
        axes=tuple(topo["axes"]), max_bands=int(topo["max_bands"]),
        max_topologies=int(s2["topology"]["max_topologies_per_floor"]), stair_hall=stair_hall)


def s2_context(scat, catalog, client_rs, matrix: ZoneMatrix) -> S2Context:
    s2 = scat.s2
    access = scat.data.get("access_core") or {}
    hall = access.get("stair_hall")
    return S2Context(scat, catalog, client_rs, matrix, floor_rules(catalog, s2, "ground", hall),
                     floor_rules(catalog, s2, "upper", hall), access.get("comparison"),
                     {t["stair_id"]: int(t["flights"]) for t in scat.data["stair"]["types"]})


def structure_settings(values: dict[str, Any], s2: dict[str, Any],
                       kinds: dict[str, str] | None = None) -> dict[str, Any] | None:
    """S2.2f settings from the design registry values (None when the structure check is off); S2.2g adds the frame
    (`frame`: None when off; `frame_hard`: no free zoning when no frame zones the cell)."""
    if not values.get("structure.enabled"):
        return None
    res = float(s2["grid_ft"])
    frame = frame_settings(values, float(values["circulation.hall.design_width_ft"]), res)
    return {"frame": frame, "positions": positions_settings(values, s2) if frame is not None else None,
            "frame_hard": (kinds or {}).get("structure.frame.enabled", "hard") == "hard",
            "surplus_min_cells": round(float(values.get("structure.frame.surplus_min_sqft", 0.0)) / (res * res)),
            "ground_surplus": str(values.get("structure.frame.ground_surplus", "either")),
            "line_bonus": float(values.get("structure.frame.line_wall_bonus", 0.0)),
            "min_fraction": float(values["structure.support_min_fraction"]),
            "beam_max_ft": float(values["structure.beam_span_max_ft"]),
            "joist_span_max_ft": float(values["structure.joist_span_max_ft"]),
            "snap_cells": int(round(float(values["structure.snap_max_ft"]) / res)),
            "node_cells": int(round(float(values["circulation.arrival.node_short_side_max_ft"]) / res)),
            "pair_candidates": max(1, int(values["structure.pair_candidates"])),
            "family_loft": bool(values.get("circulation.arrival.family_loft", True))}


def _upper_guide(uframe: FloorFrame, g_rz: Realization, st: dict[str, Any]) -> StructureGuide:
    """Upper cuts snap to the ground zone walls; how the zones stand on them is scored (the ground rooms of S2.1 add
    walls, so the hard check waits for them)."""
    g, u = g_rz.frame.grid, uframe.grid
    labels = zone_labels(g, g_rz.rects)
    gv, gh = edge_walls(labels, OUTSIDE)
    di, dj = grid_offset(u.x0, u.y0, g.x0, g.y0, g.res)
    ny, nx = u.labels.shape
    return StructureGuide(window(gv, (ny, nx + 1), di, dj), window(gh, (ny + 1, nx), di, dj), st["snap_cells"],
                          st["min_fraction"], labels, di, dj, st["min_fraction"], st["beam_max_ft"], st["node_cells"],
                          hard=False)       # scored here; the hard check runs in S2.1 on the final ground walls


# ------------------------------------------------------------------ output helpers


def _unit_box(frame: FloorFrame, r) -> BaseGeometry:
    """The unit's rectangle, pushed out to the floor's outline on the sides where it meets the grid's bounding
    cells (cells are classified by their centre, so a sliver of floor thinner than half a cell lies outside)."""
    from shapely.geometry import box

    g = frame.grid
    i0, i1, j0, j1 = bounding_cells(g)
    x0, y0, x1, y1 = g.to_box(r).bounds
    fx0, fy0, fx1, fy1 = frame.polygon.bounds
    return box(fx0 - g.res if r[0] == i0 else x0, fy0 - g.res if r[2] == j0 else y0,
               fx1 + g.res if r[1] == i1 else x1, fy1 + g.res if r[3] == j1 else y1)


def _unit_blocks(frame: FloorFrame, rz: Realization, plan: LotPlan, nd: int) -> list[dict[str, Any]]:
    g = frame.grid
    out = []
    for k, (u, r) in enumerate(zip(frame.units, rz.rects)):
        poly: BaseGeometry = _unit_box(frame, r).intersection(frame.free_polygon)
        target = rz.targets[k] if rz.targets is not None else frame.targets[k]
        out.append({"unit_id": u.unit_id, "zone": u.zone, "space_ids": list(u.space_ids),
                    "target_sqft": round(target * g.cell_area, 1),
                    "area_sqft": round(poly.area, 1),
                    "width_ft": round((r[1] - r[0]) * g.res, 2), "depth_ft": round((r[3] - r[2]) * g.res, 2),
                    "polygon": polygon_json(plan.to_world(poly), nd)})
    return out


def _floor_block(frame: FloorFrame, rz: Realization, summary: dict[str, Any], plan: LotPlan, nd: int,
                 alternatives: list[Realization]) -> dict[str, Any]:
    units = frame.units
    axis, bands = rz.topology[0], rz.topology[1]
    topology: dict[str, Any] = {"axis": axis, "bands": [[units[u].unit_id for u in band] for band in bands]}
    if len(rz.topology) == 4:                              # S2.2g: bands on the structural frame
        g = frame.grid
        origin = g.x0 if axis == "x" else g.y0
        topology.update({"framed": True, "cuts_ft": [round(origin + c * g.res, 3) for c in rz.topology[2]],
                         "split_bay": rz.topology[3]})
    block = {
        "level": frame.level,
        "variant": frame.variant,
        "units": _unit_blocks(frame, rz, plan, nd),
        "topology": topology,
        "landing_unit": units[rz.landing_unit].unit_id,
        "arrival_kind": arrival_of(units[rz.landing_unit], list(frame.arrival_order)) if frame.level else None,
        "landing_share": round(rz.landing_share, 3),
        "entry_unit": units[rz.entry_unit].unit_id if rz.entry_unit is not None else None,
        "entry_fallback": rz.entry_fallback,
        "links": sorted([units[a].unit_id, units[b].unit_id] for a, b in rz.links),
        "score": round(rz.score, 4),
        "score_parts": {k: round(v, 4) for k, v in sorted(rz.parts.items())},
        "matrix_deferred": rz.relations.get("deferred", []),
        "scale": round(frame.scale, 4),
        "notes": list(frame.notes),
        "search": summary,
        "alternatives": [{"topology": {"axis": a.topology[0],
                                       "bands": [[a.frame.units[u].unit_id for u in band] for band in a.topology[1]]},
                          "score": round(a.score, 4)} for a in alternatives[1:]],
    }
    if len(rz.topology) == 4:
        block["open_air"] = _open_air_blocks(frame, rz, plan, nd)
        if rz.carried is not None and frame.level == GROUND:
            block["frame_lines_carried"] = round(rz.carried, 3)
    return block


def _open_air_blocks(frame: FloorFrame, rz: Realization, plan: LotPlan, nd: int) -> list[dict[str, Any]]:
    """S2.2g: the open ends of the bands (roof upstairs, porch or unbuilt downstairs)."""
    out = []
    for r, kind in rz.open_air:
        poly = _unit_box(frame, r).intersection(frame.free_polygon)
        if poly.is_empty:
            continue
        out.append({"kind": kind, "area_sqft": round(poly.area, 1), "polygon": polygon_json(plan.to_world(poly), nd)})
    return out


# ------------------------------------------------------------------ receiving predicates


def _receives(unit, types: list[str], hall_types: set[str], forbidden: list[str]) -> bool:
    """Can the stair start land in this unit (K02)? A circulation unit holding a merged closet (laundry) is still a
    hall: the closet is kept off the landing at the door level (S2.1), as on the upper floor."""
    if unit.zone != CIRCULATION and unit.hosts(forbidden):
        return False
    return unit.hosts(types) or (unit.zone == CIRCULATION and bool(set(types) & hall_types))


def frame_guide(frame: Frame, floor: FloorFrame, st: dict[str, Any], ground_bands: int = 2) -> FrameGuide | None:
    """The guide of a structural frame in one floor's grid: band cuts on the frame's lines (upper floor: its
    interior axes, the central hall's two lines a hall width apart, the circulation strip; ground floor: the axes and
    the joint over the ground floor, at most the catalog's bands). None when an upper axis falls outside the floor."""
    axis, g = frame.axis, floor.grid
    i0, i1, j0, j1 = bounding_cells(g)
    lo, hi = (i0, i1) if axis == "x" else (j0, j1)
    origin = g.x0 if axis == "x" else g.y0
    smin = st["surplus_min_cells"]
    if floor.level != GROUND:
        if not frame.axes:
            return FrameGuide(axis, (), surplus=ROOF, surplus_min_cells=smin, max_cuts=0, free_cut=True, strip=True,
                              line_bonus=st["line_bonus"], ref=frame)
        first = round((frame.axes[0].pos - origin) / g.res)
        lines = (first,) if frame.pattern != SPINE else (first, first + round(frame.hall_ft / g.res))
        if not all(lo < k < hi for k in lines):
            return None
        return FrameGuide(axis, lines, spine=lines if frame.pattern == SPINE else None, surplus=ROOF,
                          surplus_min_cells=smin, max_cuts=len(lines), free_cut=True, strip=True,
                          line_bonus=st["line_bonus"], ref=frame)
    lines = tuple(sorted({k for c in frame.ground_lines() if lo < (k := round((c - origin) / g.res)) < hi}))
    return FrameGuide(axis, lines, surplus=st["ground_surplus"], surplus_min_cells=smin,
                      max_cuts=max(0, ground_bands - 1), free_cut=True, line_bonus=st["line_bonus"], free=True,
                      ref=frame)


def _search(frames: list[FloorFrame], rules: FloorRules, matrix: ZoneMatrix, pins_of, guide_of=None,
            fguide_of=None):
    """One search per frame (unit set) and pinned unit, merged: valid realizations (best first; each knows its
    frame) and the summary of all runs. `guide_of(frame)`: the structure guide of S2.2f (None: none);
    `fguide_of(frame)`: the structural frame guide of S2.2g (None: free band cuts)."""
    valid: list[Realization] = []
    summary: dict[str, Any] = {"unit_sets": [], "topologies_tried": 0, "valid": 0, "truncated": False,
                               "first_violations": {}}
    for frame in frames:
        for pin in pins_of(frame):
            fg = fguide_of(frame) if fguide_of else None
            if fguide_of and fg is None:
                continue                              # S2.2g: the frame does not fit this floor
            search = FloorSearch(frame, rules, matrix, pin, guide_of(frame) if guide_of else None, fg)
            found = search.run()
            valid += found
            one = search.summary(found)
            summary["unit_sets"].append({"units": [u.unit_id for u in frame.units],
                                         "pin": frame.units[pin].unit_id if pin is not None else None,
                                         "valid": one["valid"]})
            summary["topologies_tried"] += one["topologies_tried"]
            summary["valid"] += one["valid"]
            summary["truncated"] |= one["truncated"]
            for k, v in one["first_violations"].items():
                summary["first_violations"][k] = summary["first_violations"].get(k, 0) + v
    valid.sort(key=lambda x: (-x.score, x.topology, [u.unit_id for u in x.frame.units]))
    return valid, summary


def _combine(ctx: S2Context, ground: list[Realization], upper: list[Realization], k: int):
    w = ctx.ground_rules.weights
    wv = w["vertical"] / (sum(w.values()) or 1.0)
    best = None
    for g in ground[:k]:
        for u in upper[:k]:
            v = vertical_pairs(ctx.matrix, g.graph, u.graph, g.landing_unit, u.landing_unit,
                               ctx.scat.s2["vertical_depth_ok"])
            total = (1.0 - wv) * 0.5 * (g.score + u.score) + wv * v["score"]
            if best is None or total > best[0] + 1e-12:
                best = (total, g, u, v)
    return best


# ------------------------------------------------------------------ one cell


def zone_cell(cell: dict[str, Any], s1: dict[str, Any], plan: LotPlan, ctx: S2Context) -> dict[str, Any]:
    """Stage S2 block of a cell drawn by S1 (`cell` is the area-matrix cell with its space split); with the
    structural frame of S2.2g, the block says how the frame went (`frame`)."""
    st = ctx.structure
    if st is None or st.get("frame") is None or not cell.get("space_split"):
        return _zone_cell(cell, s1, plan, ctx, [])
    frames = build_frames(cell_floors(s1, plan), st["frame"])
    if not frames:
        out = _zone_cell(cell, s1, plan, ctx, [])
        out["frame"] = {"status": "none", "reason": "upper floor deeper than two joist spans and a hall"}
        return out
    out = _zone_cell(cell, s1, plan, ctx, frames)
    if out["status"] == ZONED:
        return out
    variants = [f.to_dict() for f in frames]
    if st["frame_hard"]:
        out["frame"] = {"status": "failed", "variants": variants}
        return out
    free = _zone_cell(cell, s1, plan, ctx, [])
    free["warnings"].append("S2.2g: no structural frame zones the cell; free zoning (frame rule soft)")
    free["frame"] = {"status": "fallback", "variants": variants}
    return free


def _interleave(rzs: list[Realization]) -> list[Realization]:
    """S2.2g: the ground floors on the frame's lines and the S2 ones (lines inside zones) taken in turn, each kind in
    its own order: stage S2.1 gets both."""
    framed = [r for r in rzs if len(r.topology) == 4]
    free = [r for r in rzs if len(r.topology) != 4]
    out = []
    for k in range(max(len(framed), len(free))):
        out += [x[k] for x in (framed, free) if k < len(x)]
    return out


def _same_frame(a: Realization, b: Realization) -> bool:
    """S2.2g: both zoned on the same frame variant with its axes at the same positions."""
    fa, fb = a.sframe, b.sframe
    return fa is not None and fb is not None and fa.variant == fb.variant and \
        [x.pos for x in fa.axes] == [x.pos for x in fb.axes]


def _round_robin(pairs: list, fit: list[Realization]) -> list:
    """Pairs in rounds over the ground floors (in their own order), each one's uppers best first."""
    rank = {id(g_rz): k for k, g_rz in enumerate(fit)}
    pairs = sorted(pairs, key=lambda p: (rank[id(p[1])], -p[0]))
    nth: dict[int, int] = {}
    order = []
    for p in pairs:
        nth[id(p[1])] = nth.get(id(p[1]), -1) + 1
        order.append((nth[id(p[1])], rank[id(p[1])], p))
    return [p for _, _, p in sorted(order, key=lambda x: (x[0], x[1]))]


def _merge(summary: dict[str, Any], one: dict[str, Any]) -> None:
    summary["topologies_tried"] += one["topologies_tried"]
    summary["valid"] += one["valid"]
    summary["truncated"] |= one["truncated"]
    summary["unit_sets"] += one["unit_sets"]
    for k, v in one["first_violations"].items():
        summary["first_violations"][k] = summary["first_violations"].get(k, 0) + v


def _empty_summary() -> dict[str, Any]:
    return {"unit_sets": [], "topologies_tried": 0, "valid": 0, "truncated": False, "first_violations": {}}


def _zone_cell(cell: dict[str, Any], s1: dict[str, Any], plan: LotPlan, ctx: S2Context,
               frames: list[Frame]) -> dict[str, Any]:
    """`frames`: the structural frame variants both floors are zoned on (S2.2g; []: free zoning)."""
    scat, catalog, client = ctx.scat, ctx.catalog, ctx.client_rs
    s2 = scat.s2
    nd = int(scat.geometry["round_ft"])
    keep = max(1, int(s2["keep_alternatives"]))
    out: dict[str, Any] = {"stage": "S2", "warnings": []}
    rows = cell.get("space_split")
    if not rows:
        return {**out, "status": NO_SPACE_SPLIT, "next_stage": None,
                "warnings": ["area-matrix cell without space_split (area matrix older than step 6.7a S2)"]}
    floors = cell_floors(s1, plan)
    st = ctx.structure
    core = s1["stair_core"]
    stair_type = scat.stair_space_type
    hall_types = set(catalog.data["circulation"]["derived_space_types"])
    res = float(s2["grid_ft"])
    n_floors = 1 + max(r["floor"] for r in rows)

    # upper floor
    arrival = upper_arrival(catalog, s2, scat.stair_access, rows, client.params(TOP_RULE))
    if st is not None and not st["family_loft"] and len(arrival["order"]) > 1:   # S2.2f: no family-room arrival
        order = [k for k in arrival["order"] if k != "family_room"]
        arrival = {**arrival, "order": order, "receiving": order[0]}
    u_frames = [upper_frame(floors, units, res, notes, anchored=st is not None) for _, units, notes in
                floor_units(catalog, s2, rows, UPPER, n_floors, stair_type, False, arrival["receiving"])]
    for f in u_frames:
        f.arrival_order = tuple(arrival["order"])
    u_rules = replace(ctx.upper_rules, arrival=arrival["receiving"], arrival_order=tuple(arrival["order"]))

    def arrival_pins(frame: FloorFrame) -> list[int | None]:
        pins = [k for k, u in enumerate(frame.units) if arrival_of(u, arrival["order"]) is not None]
        return pins or [None]

    upper_cache: dict[int, tuple[list[Realization], dict[str, Any]]] = {}

    def upper_for(g_rz: Realization | None) -> tuple[list[Realization], dict[str, Any]]:
        """The upper floor's valid zonings, standing on `g_rz` (S2.2f) or free (structure off)."""
        key = id(g_rz) if g_rz is not None else 0
        if key not in upper_cache:
            if g_rz is not None:
                guide = lambda f: _upper_guide(f, g_rz, st)
            elif st is not None:                     # free zonings keep the compact arrival node (S2.2f)
                none = np.zeros((1, 1), dtype=bool)
                guide = lambda f: StructureGuide(none, none, 0, 1.0, node_cells=st["node_cells"])
            else:
                guide = None
            upper_cache[key] = _search(u_frames, u_rules, ctx.matrix, arrival_pins, guide)
        return upper_cache[key]

    framed = bool(frames)
    u_by: dict[int, list[Realization]] = {}
    optimized: dict[tuple[int, int], tuple] = {}         # S2.2g: (ground, upper) -> (pair, positions report)

    def optimize(p):
        """S2.2g: the pair on its best axis position with its zone walls aligned across floors."""
        key = (id(p[1]), id(p[2]))
        if key not in optimized:
            g2, u2, report = optimize_pair(p[1], p[2], st["positions"])
            q = p if (g2 is p[1] and u2 is p[2]) else _combine(ctx, [g2], [u2], 1)
            optimized[key] = (q, report)
            optimized[(id(q[1]), id(q[2]))] = (q, report)
        return optimized[key][0]
    if framed:                                       # S2.2g: one upper search per frame variant
        u_valid, u_summary = [], _empty_summary()
        none = np.zeros((1, 1), dtype=bool)
        for fr in frames:
            found, one = _search(u_frames, u_rules, ctx.matrix, arrival_pins,
                                 lambda f: StructureGuide(none, none, 0, 1.0, node_cells=st["node_cells"]),
                                 lambda f, fr=fr: frame_guide(fr, f, st))
            u_by[id(fr)] = found
            u_valid += found
            _merge(u_summary, one)
        u_valid.sort(key=lambda x: -x.score)
    elif st is None:
        u_valid, u_summary = upper_for(None)
    else:
        u_valid, u_summary = [], {"unit_sets": [], "topologies_tried": 0, "valid": 0, "truncated": False,
                                  "first_violations": {}, "ground_candidates": 0}

    # ground floor: one search per use of the space under the stair, pinned on every unit that can receive a start
    us = core["under_stair"]
    receiving = core["bottom_end"]["receiving"]
    has_hb = any(r["space_type"] == HALF_BATH_USE and r["floor"] == GROUND for r in rows)
    variants = [HALF_BATH_USE, STORAGE_USE] if (us["half_bath_fit"] and has_hb) else [STORAGE_USE]

    def start_pins(frame: FloorFrame) -> list[int | None]:
        pins = [k for k, u in enumerate(frame.units)
                if any(_receives(u, o["receiving"], hall_types, receiving["forbidden"]) for o in receiving["options"])]
        return pins or [None]

    g_runs: dict[str, tuple[dict[str, Any], list[Realization]]] = {}
    for v in variants:
        g_frames = [ground_frame(floors, units, res, v, notes) for _, units, notes in
                  floor_units(catalog, s2, rows, GROUND, n_floors, stair_type, v == HALF_BATH_USE, None)]
        if framed:                                   # S2.2g: the ground floor on each frame variant
            valid, summary = [], _empty_summary()
            for fr in frames:
                found, one = _search(g_frames, ctx.ground_rules, ctx.matrix, start_pins, None,
                                     lambda f, fr=fr: frame_guide(fr, f, st, ctx.ground_rules.max_bands))
                valid += found
                _merge(summary, one)
            valid.sort(key=lambda x: -x.score)
        else:
            valid, summary = _search(g_frames, ctx.ground_rules, ctx.matrix, start_pins)
        g_runs[v] = (summary, valid)

    options = [o["option"] for o in receiving["options"]]
    preferred = receiving["preferred"]
    uses = us.get("use_by_bottom_option") or {}
    portfolio: dict[str, Any] = {}
    chosen = None
    for o in receiving["options"]:
        opt = o["option"]
        use = uses.get(opt, STORAGE_USE) if has_hb else STORAGE_USE
        order = [use] + ([STORAGE_USE] if use == HALF_BATH_USE else [])
        entry: dict[str, Any] = {"option": opt, "label": o["label"], "receiving": list(o["receiving"]),
                                 "under_stair_use": use, "feasible": False}
        for v in order:
            if v not in g_runs:
                continue
            summary, valid = g_runs[v]
            fit = [rz for rz in valid if _receives(rz.frame.units[rz.landing_unit], o["receiving"], hall_types,
                                                   receiving["forbidden"])]
            if not fit:
                continue
            if st is None:
                if not u_valid:
                    continue
                total, g_best, u_best, vert = _combine(ctx, fit, u_valid, keep)
                pairs = None
            elif framed:                                 # S2.2g: a ground floor pairs with uppers of its frame
                pairs, picked = [], []
                for fr in frames:
                    for g_rz in _interleave([g for g in fit if g.sframe is fr])[:st["pair_candidates"]]:
                        picked.append(g_rz)
                        pairs += [_combine(ctx, [g_rz], [u2], 1) for u2 in u_by[id(fr)][:keep]]
                if not pairs:
                    continue
                pairs = [optimize(p) for p in _round_robin(pairs, picked)]
                total, g_best, u_best, vert = pairs[0]
            else:                                    # S2.2f: the upper floor stands on each candidate ground floor
                pairs = []
                for g_rz in fit[:st["pair_candidates"]]:
                    fresh = id(g_rz) not in upper_cache
                    uv, summ = upper_for(g_rz)
                    if fresh:                          # S2.2f: the upper searches of every ground candidate
                        u_summary["ground_candidates"] += 1
                        u_summary["topologies_tried"] += summ["topologies_tried"]
                        u_summary["valid"] += summ["valid"]
                        u_summary["truncated"] |= summ["truncated"]
                        u_summary["unit_sets"] += summ["unit_sets"]
                        for kk, vv in summ["first_violations"].items():
                            u_summary["first_violations"][kk] = u_summary["first_violations"].get(kk, 0) + vv
                    free, _ = upper_for(None)          # the free zonings too: S2.1 decides on the final walls
                    cands = uv[:keep] + [f for f in free[:keep] if all(f is not x for x in uv[:keep])]
                    if cands:
                        u_valid = u_valid or cands
                        pairs += [_combine(ctx, [g_rz], [u2], 1) for u2 in cands]
                if not pairs:
                    continue
                pairs = _round_robin(pairs, fit)
                total, g_best, u_best, vert = pairs[0]
            entry.update({"feasible": True, "variant": v,
                          "half_bath": None if not has_hb else ("under_stair" if v == HALF_BATH_USE else "relocated"),
                          "score": round(total, 4), "vertical": {"score": round(vert["score"], 4),
                                                                 "pairs": vert["pairs"]},
                          "ground": _floor_block(g_best.frame, g_best, summary, plan, nd, [g_best] + [
                              rz for rz in fit if rz is not g_best][: keep - 1]),
                          "_upper": u_best, "_ground": g_best, "_pairs": pairs,
                          "_fit": [g for g in fit if _same_frame(g, g_best)] if framed else fit,
                          "_u_valid": (u_by[id(frames[g_best.sframe.variant])] if framed
                                       else upper_for(g_best)[0] if st is not None
                                       else u_valid)})
            if ctx.routes is not None and floors.door_area is not None:
                routes = route_lengths(g_best.frame, g_best.rects, ctx.matrix.roles, ctx.routes, floors.door_area)
                if routes.get("absent"):          # a target lives upstairs: walk the stair and the upper floor
                    up = route_lengths(u_best.frame, u_best.rects, ctx.matrix.roles, ctx.routes, from_landing=True)
                    flights = ctx.stair_flights.get(s1["stair"]["stair_id"], 1)
                    routes = two_floor_routes(routes, up, stair_walk_ft(s1["stair"], flights))
                entry["routes"] = routes
            break
        if not entry["feasible"]:
            summary, valid = g_runs[order[0]] if order[0] in g_runs else next(iter(g_runs.values()))
            entry["reason"] = ("upper floor not zoned" if not u_valid else
                               "no ground realization lands the stair start in " + "/".join(o["receiving"])
                               if valid else "ground floor not zoned")
            entry["ground_search"] = summary
        portfolio[opt] = entry
    feasible = [opt for opt in options if portfolio[opt]["feasible"]]
    if feasible:
        chosen = preferred if preferred in feasible else feasible[0]

    status = (ZONED if chosen else NOT_ZONED if not u_valid and not any(r[1] for r in g_runs.values())
              else UPPER_NOT_ZONED if not u_valid else GROUND_NOT_ZONED)
    out.update({"status": status, "next_stage": NEXT_STAGE if status == ZONED else None,
                "arrival": arrival, "preferred_option": preferred, "chosen_option": chosen,
                "feasible_options": feasible})
    if chosen:
        best = portfolio[chosen]
        u_best = best["_upper"]
        u_list = best["_u_valid"]
        out["upper"] = _floor_block(u_best.frame, u_best, u_summary, plan, nd,
                                    [u_best] + [rz for rz in u_list if rz is not u_best][: keep - 1])
        if u_best.structure is not None:
            out["structure"] = {**u_best.structure, "upper_standing_on": best["ground"]["topology"]}
        if framed:
            g_best = best["_ground"]
            u_best = best["_upper"]
            out["frame"] = {"status": "framed", **g_best.sframe.to_dict(), "variants": len(frames),
                            "ground_lines_carried": g_best.carried, "upper_lines_carried": u_best.carried,
                            "positions": optimized.get((id(g_best), id(u_best)), (None, {}))[1]}
        out["score"] = best["score"]
        out["vertical"] = best["vertical"]
    else:
        out["upper_search"] = u_summary
    if chosen and ctx.alternatives:
        # in memory only (stage S2.1 tries them in order; never written to the contract)
        best = portfolio[chosen]
        k = ctx.alternatives
        if best["_pairs"] is not None:             # S2.2f: S2.1 crosses the grounds and the uppers (hard check there)
            grounds, uppers = [best["_ground"]], [best["_upper"]]
            for _, g_rz, u_rz, _ in best["_pairs"]:
                if framed and not (_same_frame(g_rz, best["_ground"]) and _same_frame(u_rz, best["_ground"])):
                    continue                          # S2.2g: S2.1 crosses floors of the chosen frame only
                if all(g_rz is not x for x in grounds):
                    grounds.append(g_rz)
                if all(u_rz is not x for x in uppers):
                    uppers.append(u_rz)
            if not framed:
                free, _ = upper_for(None)             # the best uppers standing on nothing in particular, last
                uppers += [u_rz for u_rz in free[:k] if all(u_rz.rects != x.rects or u_rz.frame is not x.frame
                                                             for x in uppers)]
            out["_alternatives"] = {
                "cross": True,
                "upper": [out["upper"]] + [_floor_block(u.frame, u, u_summary, plan, nd, []) for u in uppers[1:2 * k]],
                "ground": [best["ground"]] + [_floor_block(g.frame, g, {}, plan, nd, []) for g in grounds[1:k]]}
        else:
            out["_alternatives"] = {
                "upper": [out["upper"]] + [_floor_block(rz.frame, rz, u_summary, plan, nd, [])
                                           for rz in u_valid if rz is not best["_upper"]][: k - 1],
                "ground": [best["ground"]] + [_floor_block(rz.frame, rz, {}, plan, nd, [])
                                              for rz in best["_fit"] if rz is not best["_ground"]][: k - 1]}
    for e in portfolio.values():
        e.pop("_upper", None)
        e.pop("_ground", None)
        e.pop("_fit", None)
        e.pop("_pairs", None)
        e.pop("_u_valid", None)
    out["options"] = portfolio
    out["matrix_overrides"] = list(ctx.matrix.overrides)
    out["rule_traces"] = _traces(client, out, arrival, portfolio, chosen, u_valid, u_summary, has_hb, us)
    return out


def _traces(client, out, arrival, portfolio, chosen, u_valid, u_summary, has_hb, us) -> list[dict[str, Any]]:
    traces = []
    kind = arrival["receiving"]
    if u_valid:
        got = out["upper"]["arrival_kind"] if chosen else kind
        traces.append(trace(client, TOP_RULE, PASS,
                            f"the stair arrives into the {got} ({out['upper']['landing_unit'] if chosen else 'upper'}); "
                            f"preference {arrival['order']}" + ("" if got == kind else " (not the first: scored)")))
    elif u_summary["first_violations"].get("K01"):
        traces.append(trace(client, TOP_RULE, FAIL, f"no upper zoning lands the stair in a {kind}"))
    else:
        traces.append(trace(client, TOP_RULE, NOT_EVALUATED, "upper floor not zoned"))
    if chosen:
        e = portfolio[chosen]
        traces.append(trace(client, BOTTOM_RULE, PASS,
                            f"option {chosen} ({e['label']}): the start lands in {e['ground']['landing_unit']}; "
                            f"feasible options {out['feasible_options']}"))
        if has_hb and e["under_stair_use"] == STORAGE_USE and us["half_bath_fit"]:
            traces.append(trace(client, UNDER_KITCHEN_RULE, PASS, f"option {chosen}: storage under the stair"))
        if has_hb:
            detail = ("vestibule of the half bath under the stair opens onto circulation" if e["variant"] == HALF_BATH_USE
                      else "half bath relocated into the circulation zone (vestibulated)")
            traces.append(trace(client, HALF_BATH_RULE, PASS, detail))
        deferred = sorted({p for f in (e["ground"], out["upper"]) for p in f["matrix_deferred"]})
        traces.append(trace(client, RELATIONS_RULE, PASS,
                            f"zone-level pairs met; {len(out['matrix_overrides'])} base pairs overridden by K05"))
        if deferred:
            traces.append(trace(client, RELATIONS_RULE, DEFERRED_S21,
                                f"door-level pairs (no direct door): {', '.join(deferred)}"))
    else:
        traces.append(trace(client, BOTTOM_RULE, FAIL if u_valid else NOT_EVALUATED,
                            "no start option feasible" if u_valid else "upper floor not zoned"))
    return traces


__all__ = [
    "GROUND_NOT_ZONED",
    "NEXT_STAGE",
    "NOT_ZONED",
    "NO_SPACE_SPLIT",
    "S2_STATUSES",
    "UPPER_NOT_ZONED",
    "ZONED",
    "S2Context",
    "floor_rules",
    "s2_context",
    "structure_settings",
    "zone_cell",
]
