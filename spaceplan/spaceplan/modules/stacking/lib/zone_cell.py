"""Stage S2 of one drawn cell (step 6.7a): zoning of both floors around the stair core and the A/B/C start portfolio.

    upper floor  -> receiving space at the top (K01: family room / vestibule / hall), search, best realizations
    ground floor -> per use of the space under the stair (half bath with its vestibule, or storage with the half bath
                    relocated into the circulation zone), search; each start option (K02: A vestibulated, B living,
                    C kitchen) keeps the best realization whose bottom landing falls in a space it allows
    cell         -> per option: best pair (ground x upper) by floor scores and the pairs measured through the stair;
                    the preferred option when it is feasible, else the first feasible; traces K01-K05

Only reads the S1 block, the space split of the area matrix and the catalogs: no lotcap, site or areas code runs.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from shapely.geometry.base import BaseGeometry

from spaceplan.modules.stacking.lib.core_zoning import FloorRules, FloorSearch, Realization
from spaceplan.modules.stacking.lib.floor_frame import (
    CIRCULATION,
    FAMILY_ROOM,
    arrival_of,
    GROUND,
    HALF_BATH_USE,
    STORAGE_USE,
    UPPER,
    FloorFrame,
    cell_floors,
    floor_units,
    ground_frame,
    upper_arrival,
    upper_frame,
)
from spaceplan.modules.stacking.lib.lot_plan import LotPlan
from spaceplan.modules.stacking.lib.routes import route_lengths
from spaceplan.modules.stacking.lib.stair_access import DEFERRED_S21, FAIL, NOT_EVALUATED, PASS, trace
from spaceplan.modules.stacking.lib.zone_relations import ZoneMatrix, vertical_pairs
from spaceplan.modules.stacking.lib_aux.plan_geometry import polygon_json
from spaceplan.modules.stacking.lib_aux.zone_grid import bounding_cells

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
                     floor_rules(catalog, s2, "upper", hall), access.get("comparison"))


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
        out.append({"unit_id": u.unit_id, "zone": u.zone, "space_ids": list(u.space_ids),
                    "target_sqft": round(frame.targets[k] * g.cell_area, 1),
                    "area_sqft": round(poly.area, 1),
                    "width_ft": round((r[1] - r[0]) * g.res, 2), "depth_ft": round((r[3] - r[2]) * g.res, 2),
                    "polygon": polygon_json(plan.to_world(poly), nd)})
    return out


def _floor_block(frame: FloorFrame, rz: Realization, summary: dict[str, Any], plan: LotPlan, nd: int,
                 alternatives: list[Realization]) -> dict[str, Any]:
    units = frame.units
    axis, bands = rz.topology
    return {
        "level": frame.level,
        "variant": frame.variant,
        "units": _unit_blocks(frame, rz, plan, nd),
        "topology": {"axis": axis, "bands": [[units[u].unit_id for u in band] for band in bands]},
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


# ------------------------------------------------------------------ receiving predicates


def _receives(unit, types: list[str], hall_types: set[str], forbidden: list[str]) -> bool:
    """Can the stair start land in this unit (K02)? A circulation unit holding a merged closet (laundry) is still a
    hall: the closet is kept off the landing at the door level (S2.1), as on the upper floor."""
    if unit.zone != CIRCULATION and unit.hosts(forbidden):
        return False
    return unit.hosts(types) or (unit.zone == CIRCULATION and bool(set(types) & hall_types))


def _search(frames: list[FloorFrame], rules: FloorRules, matrix: ZoneMatrix, pins_of):
    """One search per frame (unit set) and pinned unit, merged: valid realizations (best first; each knows its
    frame) and the summary of all runs."""
    valid: list[Realization] = []
    summary: dict[str, Any] = {"unit_sets": [], "topologies_tried": 0, "valid": 0, "truncated": False,
                               "first_violations": {}}
    for frame in frames:
        for pin in pins_of(frame):
            search = FloorSearch(frame, rules, matrix, pin)
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
    """Stage S2 block of a cell drawn by S1 (`cell` is the area-matrix cell with its space split)."""
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
    core = s1["stair_core"]
    stair_type = scat.stair_space_type
    hall_types = set(catalog.data["circulation"]["derived_space_types"])
    res = float(s2["grid_ft"])
    n_floors = 1 + max(r["floor"] for r in rows)

    # upper floor
    arrival = upper_arrival(catalog, s2, scat.stair_access, rows, client.params(TOP_RULE))
    u_frames = [upper_frame(floors, units, res, notes) for _, units, notes in
                floor_units(catalog, s2, rows, UPPER, n_floors, stair_type, False, arrival["receiving"])]
    for f in u_frames:
        f.arrival_order = tuple(arrival["order"])
    u_rules = replace(ctx.upper_rules, arrival=arrival["receiving"], arrival_order=tuple(arrival["order"]))

    def arrival_pins(frame: FloorFrame) -> list[int | None]:
        pins = [k for k, u in enumerate(frame.units) if arrival_of(u, arrival["order"]) is not None]
        return pins or [None]

    u_valid, u_summary = _search(u_frames, u_rules, ctx.matrix, arrival_pins)

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
        frames = [ground_frame(floors, units, res, v, notes) for _, units, notes in
                  floor_units(catalog, s2, rows, GROUND, n_floors, stair_type, v == HALF_BATH_USE, None)]
        valid, summary = _search(frames, ctx.ground_rules, ctx.matrix, start_pins)
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
            if not fit or not u_valid:
                continue
            total, g_best, u_best, vert = _combine(ctx, fit, u_valid, keep)
            entry.update({"feasible": True, "variant": v,
                          "half_bath": None if not has_hb else ("under_stair" if v == HALF_BATH_USE else "relocated"),
                          "score": round(total, 4), "vertical": {"score": round(vert["score"], 4),
                                                                 "pairs": vert["pairs"]},
                          "ground": _floor_block(g_best.frame, g_best, summary, plan, nd, [g_best] + [
                              rz for rz in fit if rz is not g_best][: keep - 1]),
                          "_upper": u_best, "_ground": g_best})
            if ctx.routes is not None and floors.door_area is not None:
                entry["routes"] = route_lengths(g_best.frame, g_best.rects, ctx.matrix.roles, ctx.routes,
                                                floors.door_area)
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
        out["upper"] = _floor_block(u_best.frame, u_best, u_summary, plan, nd,
                                    [u_best] + [rz for rz in u_valid if rz is not u_best][: keep - 1])
        out["score"] = best["score"]
        out["vertical"] = best["vertical"]
    else:
        out["upper_search"] = u_summary
    for e in portfolio.values():
        e.pop("_upper", None)
        e.pop("_ground", None)
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


__all__ = ["GROUND_NOT_ZONED", "NEXT_STAGE", "NOT_ZONED", "NO_SPACE_SPLIT", "S2Context", "S2_STATUSES",
           "UPPER_NOT_ZONED", "ZONED", "floor_rules", "s2_context", "zone_cell"]
