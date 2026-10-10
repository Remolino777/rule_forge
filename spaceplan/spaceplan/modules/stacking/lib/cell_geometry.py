"""Stage S1 of one two-floor cell (step 6.7a, S1 + S1.1): ground floor, garage, upper floor, stair core,
plane-limited polygons and roof, composed from the plan libraries.

    realizable footprint of the strategy -> ground floor (front band of the ground gross area)
    -> stand-in garage -> upper-floor placements in the catalog's order, each with its joint
    -> stair: every configuration, direction and hand at the joint whose arrival zones fit (bottom in the ground
       floor out of the garage, top in the upper floor: hall, or vestibule in a small house); chosen by net ground
       cost (footprint - usable space under it), half bath under it, bottom closest to the entry, joint middle
    -> stair core for S2: footprint, ends with their receiving spaces (client rules), space under the stair and
       its use per bottom option (toward the kitchen: storage), D/I/N extension; rule traces (normative / client)
    -> allowed polygon per level (envelope minus the 131.0444 plane at the level's wall height)
    -> roof of the drawn upper floor against the plane (default, ridge turned, flat)
    -> containment, room over the garage (R302.6), stair area against the catalog target
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from shapely.geometry.base import BaseGeometry

from spaceplan.core.lib.rules import RuleSet
from spaceplan.modules.stacking.lib.height_check import WITHIN_PLANE
from spaceplan.modules.stacking.lib.lot_plan import LotPlan
from spaceplan.modules.stacking.lib.plan_levels import (
    garage_area,
    garage_rect,
    ground_floor,
    upper_floor,
)
from spaceplan.modules.stacking.lib.roof_plane import check_roof, roof_sequence
from spaceplan.modules.stacking.lib.stacking_catalog import StackingCatalog
from spaceplan.modules.stacking.lib.stair import best_by_type, candidates, choose, stair_shape
from spaceplan.modules.stacking.lib.stair_access import (
    DEFERRED,
    FAIL,
    PASS,
    access_side,
    bottom_receiving,
    relations,
    top_receiving,
    trace,
    under_stair_use,
    upper_rooms,
    uses_by_bottom_option,
)
from spaceplan.modules.stacking.lib.stair_rules import (
    FIXTURE_HEADROOM_RULE,
    FLIGHT_RISE_RULE,
    GARAGE_SEPARATION_RULE,
    HALF_BATH_CLEARANCE_RULE,
    HEADROOM_RULE,
    LANDING_RULE,
    RISER_RULE,
    TREAD_RULE,
    UNDER_STAIR_RULE,
    WIDTH_RULE,
    StairLimits,
    fixture_headroom_ft,
    flight_rise_max_ft,
    garage_separation,
    half_bath_width_min_ft,
    under_stair_protection,
)
from spaceplan.modules.stacking.lib.vertical_rules import HeightEnvelope
from spaceplan.modules.stacking.lib_aux.plan_geometry import (
    inset_from_lines,
    overlap_area,
    polygon_json,
    segments_of,
)
from spaceplan.modules.stacking.lib_aux.vertical_geometry import plane_offset

DRAWN = "drawn"
GROUND_NOT_REALIZED = "ground_not_realized"
STAIR_DOES_NOT_FIT = "stair_does_not_fit"
NOT_CONTAINED = "upper_not_contained"
S1_STATUSES = (DRAWN, GROUND_NOT_REALIZED, STAIR_DOES_NOT_FIT, NOT_CONTAINED)


def allowed_polygon(plan: LotPlan, envelope: HeightEnvelope, wall_top_ft: float) -> BaseGeometry:
    """Envelope of the lot limited by the 131.0444 plane at a wall height (equal to the envelope below the
    plane's start)."""
    if envelope.angle_deg is None:
        return plan.envelope
    extra = plane_offset(wall_top_ft - envelope.start_ft, envelope.angle_deg)
    if extra <= 0.0:
        return plan.envelope
    return inset_from_lines(plan.envelope, [(sl.line, sl.setback_ft + extra) for sl in plan.side_lines])


def _contained(inner: BaseGeometry | None, outer: BaseGeometry, tol: float) -> bool:
    return inner is not None and inner.difference(outer).area <= tol


@dataclass(frozen=True)
class S1Context:
    """Rules, catalogs and lot facts every cell of a lot shares in stage S1."""

    scat: StackingCatalog
    limits: StairLimits
    stair_rs: RuleSet
    vertical_rs: RuleSet
    client_rs: RuleSet
    catalog: Any
    envelope: HeightEnvelope
    slope: float | None
    stair_target_sqft: float


def _stair_cfg(ctx: S1Context, receiving: str) -> dict[str, Any]:
    us, pl, acc = ctx.scat.under_stair, ctx.scat.stair_placement, ctx.scat.stair_access
    hb_spec = ctx.catalog.space_type("half_bath")
    zone = acc["top_zone"][receiving]
    storage = next(b for b in us["bands"] if b["band"] == us["usable_from_band"])["min_ft"]
    return {"step": float(pl["search_step_ft"]), "max_positions": int(pl["max_positions"]), "choice": pl["choice"],
            "half_bath_trials": int(pl["half_bath_trials"]),
            "bucket_sqft": float(pl["net_ground_bucket_sqft"]),
            "landing_ft": max(ctx.scat.stair_design["landing_ft"], ctx.limits.landing_min_ft),
            "top_depth_ft": max(zone["depth_ft"], ctx.limits.landing_min_ft), "top_width_ft": zone["width_ft"],
            "storage_ft": float(storage), "half_bath_ft": fixture_headroom_ft(ctx.stair_rs),
            "half_bath_sqft": float(hb_spec["area"]["min"]),
            "half_bath_side_ft": max(float(hb_spec.get("min_side_ft", 0.0)), half_bath_width_min_ft(ctx.stair_rs)),
            "extension_ft": float(us["half_bath_extension_max_ft"]), "vestibule_ft": float(us["vestibule_ft"])}


def draw_cell(cell: dict[str, Any], s0: dict[str, Any], plan: LotPlan, strategy: tuple[str | None, int | None],
              ctx: S1Context, placements: list[str] | None = None,
              stair_ids: list[str] | None = None, picker=None, garage_side: str | None = None) -> dict[str, Any]:
    """Stage S1 of one cell. `placements` overrides the catalog's order of upper-floor placements and `stair_ids`
    restricts the stair configurations compared (stage S2 uses both to redraw a cell it cannot zone).

    `picker(placement, upper, ground, garage, cfg) -> (candidates, chosen)` replaces the search at the joint (stage
    S1.2 places the stair against the permitted walls from the main door); `garage_side` overrides the catalog's
    stand-in side (S1.2 reads it from the site's driveway)."""
    scat, limits, stair_rs, vertical_rs = ctx.scat, ctx.limits, ctx.stair_rs, ctx.vertical_rs
    envelope, slope, stair_target_sqft = ctx.envelope, ctx.slope, ctx.stair_target_sqft
    geo = scat.geometry
    tol, nd = geo["area_tolerance_sqft"], int(geo["round_ft"])
    levels = s0["levels"]
    lv = scat.levels
    out: dict[str, Any] = {"stage": "S1", "strategy": strategy[0], "steps": strategy[1], "warnings": []}

    footprint = plan.footprint_for(*strategy)
    if footprint is None:
        footprint = plan.footprint_for("A_inscribed_rectangle", None)
        out["warnings"].append("cell has no strategy: ground floor cut from the strategy-A rectangle")
    ground = ground_floor(footprint, levels[0]["gross_sqft"], geo) if footprint is not None else None
    if ground is None:
        return {**out, "status": GROUND_NOT_REALIZED, "next_stage": None}

    g_area = garage_area(cell, plan.far_base_sqft)
    g_cfg = scat.garage if garage_side is None else {**scat.garage, "side": garage_side}
    garage = garage_rect(ground, g_area, g_cfg)
    shapes = [stair_shape(t, lv["floor_to_floor_ft"], limits, scat.stair_design) for t in scat.stair_types
              if stair_ids is None or t["stair_id"] in stair_ids]
    rooms = upper_rooms(list(cell.get("split", {}).get("upper_spaces") or s0.get("upper_spaces") or []),
                        ctx.catalog, scat.stair_access)
    top = top_receiving(ctx.client_rs, rooms, scat.stair_access["small_house_upper_rooms_max"])
    cfg = _stair_cfg(ctx, top["receiving"])

    upper_cands, chosen, stair, valid = [], None, None, []
    for placement in (placements or scat.upper_placements(cell.get("scheme_id"))):
        cand = upper_floor(placement, ground, levels[1]["gross_sqft"], garage, g_cfg["side"], geo,
                           scat.data["upper_floor"]["compact_min_depth_ft"])
        found, cands = None, []
        if cand.polygon is not None and picker is not None:
            cands, found = picker(placement, cand, ground, garage, cfg)
        elif cand.polygon is not None:
            joints = list(cand.joints) or [s for s in segments_of(cand.polygon.exterior)]
            cands = candidates(shapes, joints, cand.polygon, ground, garage, cfg)
            found = choose(cands)
        upper_cands.append({"placement": placement, "drawn": cand.polygon is not None,
                            "stair_fits": found is not None, "reason": cand.reason,
                            "joint_ft": round(sum(j.length for j in cand.joints), 3),
                            "over_garage_sqft": round(overlap_area(cand.polygon, garage), 2),
                            "stair_candidates": len(cands)})
        if found is not None and chosen is None:
            chosen, stair, valid = cand, found, cands
    candidates_out = upper_cands
    if chosen is None:
        drawn = next((c for c in candidates_out if c["drawn"]), None)
        out.update({"status": STAIR_DOES_NOT_FIT, "next_stage": None, "upper_candidates": candidates_out,
                    "ground": _ground_block(plan, ground, garage, g_area, nd)})
        if drawn is None:
            out["warnings"].append("no upper-floor placement could be drawn")
        return out

    upper = chosen.polygon
    plate = levels[-1]["finish_floor_ft"] + lv["top_floor_plate_ft"]
    wall_tops = [levels[k + 1]["finish_floor_ft"] for k in range(len(levels) - 1)] + [plate]
    level_polys = [ground, upper]
    level_blocks = []
    contained_all = True
    for k, (poly, wall_top) in enumerate(zip(level_polys, wall_tops)):
        allowed = allowed_polygon(plan, envelope, wall_top)
        ok = _contained(poly, allowed, tol)
        contained_all &= ok
        level_blocks.append({"level": k, "wall_top_ft": round(wall_top, 4), "area_sqft": round(poly.area, 2),
                             "polygon": polygon_json(plan.to_world(poly), nd),
                             "allowed_polygon": polygon_json(plan.to_world(allowed), nd),
                             "within_allowed": ok})
    upper_in_ground = _contained(upper, ground, tol)

    default_roof = scat.roof(scat.default_roof)
    flat_roof = scat.roof(scat.flat_roof_id)
    grade_diff = (slope or 0.0) * (ground.bounds[3] - ground.bounds[1])
    roofs = []
    for step, roof, ridge in roof_sequence(upper, default_roof, flat_roof, scat.roof_order):
        r = check_roof(upper, roof, ridge, plate, plan, envelope, vertical_rs, grade_diff)
        roofs.append({"step": step, **r})
    kept = next((r for r in roofs if r["status"] == WITHIN_PLANE), None)
    default = roofs[0]

    over_garage = overlap_area(upper, garage)
    shape = stair.shape
    status = DRAWN if contained_all and upper_in_ground else NOT_CONTAINED
    core, traces = _stair_core(cell, stair, valid, top, ctx, plan, nd, over_garage > tol, garage is not None)
    out.update({
        "status": status,
        "next_stage": "S2" if status == DRAWN else None,
        "upper_placement": chosen.placement,
        "upper_candidates": candidates_out,
        "ground": _ground_block(plan, ground, garage, g_area, nd),
        "levels": level_blocks,
        "stair": {**shape.to_dict(), "polygon": polygon_json(plan.to_world(stair.geom.footprint), nd),
                  "offset_from_joint_middle_ft": round(stair.offset_ft, 3),
                  "on_joint": bool(chosen.joints), "same_position_all_levels": True,
                  "headroom_ok": True, "catalog_target_sqft": stair_target_sqft,
                  "area_delta_sqft": round(shape.area_sqft - stair_target_sqft, 2),
                  "net_ground_sqft": core["under_stair"]["net_ground_sqft"],
                  "net_ground_delta_sqft": round(core["under_stair"]["net_ground_sqft"] - stair_target_sqft, 2),
                  "rules": limits.to_dict()},
        "stair_core": core,
        "rule_traces": traces,
        "containment": {"upper_in_ground": upper_in_ground, "levels_within_allowed": contained_all,
                        "over_garage_sqft": round(over_garage, 2),
                        "room_over_garage": over_garage > tol,
                        "garage_separation": garage_separation(stair_rs, over_garage > tol) if garage is not None else None},
        "roof": {"default": default["status"], "default_ridge": default["ridge"],
                 "kept": None if kept is None else kept["step"],
                 "kept_roof_id": None if kept is None else kept["roof_id"],
                 "kept_ridge": None if kept is None else kept["ridge"],
                 "inset_needed_ft": 0.0 if kept is not None else min(r["inset_needed_ft"] for r in roofs),
                 "checks": roofs},
    })
    return out


def _stair_core(cell, stair, valid, top, ctx: S1Context, plan: LotPlan, nd: int, room_over_garage: bool,
                has_garage: bool) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """The stair as the fixed core stage S2 zones around, and the rule traces of the cell (normative and client)."""
    scat, client, srs = ctx.scat, ctx.client_rs, ctx.stair_rs
    shape, g, under = stair.shape, stair.geom, stair.under
    options, preferred = scat.bottom_options(cell.get("scheme_id"))
    bottom = bottom_receiving(client, options, preferred)
    hb = stair.half_bath
    side = access_side(hb, stair.bottom_zone)
    uses = uses_by_bottom_option(client, bottom, side, hb is not None)
    net = under["footprint_sqft"] - under["recovered_sqft"]
    ups = under_stair_use(client, None, hb is not None)

    def end(e, zone, receiving):
        return {"edge": [[round(c, nd) for c in plan.frame.to_world(_pt(p)).coords[0]] for p in e.edge],
                "zone": polygon_json(plan.to_world(zone), nd), "receiving": receiving}

    alternatives = {sid: {"net_ground_sqft": round(c.under["footprint_sqft"] - c.under["recovered_sqft"], 2),
                          "footprint_sqft": round(c.under["footprint_sqft"], 2),
                          "recovered_sqft": round(c.under["recovered_sqft"], 2),
                          "half_bath_fit": c.half_bath is not None,
                          "entry_distance_ft": round(c.entry_distance_ft, 2)}
                    for sid, c in sorted(best_by_type(valid).items())}
    core = {
        "fixed": True,
        "stair_id": shape.stair_id,
        "footprint": polygon_json(plan.to_world(g.footprint), nd),
        "bottom_end": {**end(g.bottom, stair.bottom_zone, bottom), "entry_distance_ft": round(stair.entry_distance_ft, 2)},
        "top_end": end(g.top, stair.top_zone, top),
        "under_stair": {
            "low_sqft": round(under["low_sqft"], 2), "storage_sqft": round(under["storage_sqft"], 2),
            "half_bath_band_sqft": round(under["half_bath_band_sqft"], 2),
            "recovered_sqft": round(under["recovered_sqft"], 2), "net_ground_sqft": round(net, 2),
            "half_bath_fit": hb is not None,
            "half_bath": polygon_json(plan.to_world(hb["half_bath"]), nd) if hb else None,
            "vestibule": polygon_json(plan.to_world(hb["vestibule"]), nd) if hb else None,
            "half_bath_extension_ft": round(hb["extension_ft"], 3) if hb else None,
            "access_side": side,
            "use_default": ups["use"],
            "use_by_bottom_option": uses,
            "protection": under_stair_protection(srs)},
        "alternatives": alternatives,
        "valid_candidates": len(valid),
        "relations": relations(client),
    }
    rise_ok = shape.max_flight_rise_ft <= flight_rise_max_ft(srs) + 1e-9
    traces = [trace(srs, RISER_RULE, PASS, f"{shape.risers} risers of {shape.riser_ft * 12:.2f} in"),
              trace(srs, TREAD_RULE, PASS, f"tread {shape.tread_ft * 12:.2f} in"),
              trace(srs, WIDTH_RULE, PASS, f"width {shape.width_ft:.2f} ft"),
              trace(srs, HEADROOM_RULE, PASS, "the whole footprint is open to the upper floor"),
              trace(srs, LANDING_RULE, PASS, "arrival zones at both ends fit"),
              trace(srs, FLIGHT_RISE_RULE, PASS if rise_ok else FAIL, f"largest flight {shape.max_flight_rise_ft:.2f} ft")]
    if has_garage:
        traces.append(trace(srs, GARAGE_SEPARATION_RULE, PASS,
                            "Type X ceiling required" if room_over_garage else "1/2 in gypsum on the garage side"))
    if hb is not None:
        traces += [trace(srs, FIXTURE_HEADROOM_RULE, PASS, "half bath in the band of fixture headroom"),
                   trace(srs, HALF_BATH_CLEARANCE_RULE, PASS, "room width >= water-closet clearance")]
    traces.append(trace(srs, UNDER_STAIR_RULE, PASS, "applies if the space under the stair is enclosed"))
    traces.append(trace(client, "K01-STAIR-TOP-ARRIVAL", DEFERRED,
                        f"arrival zone fits a {top['receiving']}; the receiving space is assigned in S2"))
    traces.append(trace(client, "K02-STAIR-BOTTOM-START", DEFERRED,
                        f"options {options}, preferred {preferred}; the receiving space is assigned in S2"))
    if "C" in uses and uses["C"] != uses.get("A"):
        traces.append(trace(client, "K03-UNDER-STAIR-KITCHEN", PASS, "bottom from the kitchen -> storage under it"))
    if ups["trace"] is not None:
        traces.append(ups["trace"])
    return core, traces


def _pt(p):
    from shapely.geometry import Point

    return Point(p)


def _ground_block(plan: LotPlan, ground: BaseGeometry, garage: BaseGeometry | None, garage_sqft: float,
                  nd: int) -> dict[str, Any]:
    x0, y0, x1, y1 = ground.bounds
    return {"area_sqft": round(ground.area, 2), "width_ft": round(x1 - x0, 3), "depth_ft": round(y1 - y0, 3),
            "garage_sqft": round(garage_sqft, 2),
            "garage_polygon": polygon_json(plan.to_world(garage), nd) if garage is not None else None}


__all__ = ["DRAWN", "GROUND_NOT_REALIZED", "NOT_CONTAINED", "S1_STATUSES", "STAIR_DOES_NOT_FIT", "S1Context",
           "allowed_polygon", "draw_cell"]
