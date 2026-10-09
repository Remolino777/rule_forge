"""Stage S1 of one two-floor cell (step 6.7a): ground floor, garage, upper floor, stair, plane-limited polygons
and roof, composed from the plan libraries.

    realizable footprint of the strategy -> ground floor (front band of the ground gross area)
    -> stand-in garage -> upper-floor placements in the catalog's order, each with its joint
    -> stair (first type that fits at the joint, same rectangle on both levels) -> first placement with a stair
    -> allowed polygon per level (envelope minus the 131.0444 plane at the level's wall height)
    -> roof of the drawn upper floor against the plane (default, ridge turned, flat)
    -> containment, room over the garage (R302.6), stair area against the catalog target
"""

from __future__ import annotations

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
from spaceplan.modules.stacking.lib.stair import place_stair, stair_shape
from spaceplan.modules.stacking.lib.stair_rules import StairLimits, garage_separation
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


def draw_cell(cell: dict[str, Any], s0: dict[str, Any], plan: LotPlan, strategy: tuple[str | None, int | None],
              scat: StackingCatalog, limits: StairLimits, stair_rs: RuleSet, vertical_rs: RuleSet,
              envelope: HeightEnvelope, slope: float | None, stair_target_sqft: float) -> dict[str, Any]:
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
    garage = garage_rect(ground, g_area, scat.garage)
    shapes = [stair_shape(t, lv["floor_to_floor_ft"], limits, scat.stair_design) for t in scat.stair_types]

    candidates, chosen, stair = [], None, None
    for placement in scat.upper_placements(cell.get("scheme_id")):
        cand = upper_floor(placement, ground, levels[1]["gross_sqft"], garage, scat.garage["side"], geo)
        found = None
        if cand.polygon is not None:
            joints = list(cand.joints) or [s for s in segments_of(cand.polygon.exterior)]
            found = place_stair(shapes, joints, cand.polygon, ground, garage, scat.stair_search_step)
        candidates.append({"placement": placement, "drawn": cand.polygon is not None,
                           "stair_fits": found is not None, "reason": cand.reason,
                           "joint_ft": round(sum(j.length for j in cand.joints), 3),
                           "over_garage_sqft": round(overlap_area(cand.polygon, garage), 2)})
        if found is not None and chosen is None:
            chosen, stair = cand, found
    if chosen is None:
        drawn = next((c for c in candidates if c["drawn"]), None)
        out.update({"status": STAIR_DOES_NOT_FIT, "next_stage": None, "upper_candidates": candidates,
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
    out.update({
        "status": status,
        "next_stage": "S2" if status == DRAWN else None,
        "upper_placement": chosen.placement,
        "upper_candidates": candidates,
        "ground": _ground_block(plan, ground, garage, g_area, nd),
        "levels": level_blocks,
        "stair": {**shape.to_dict(), "polygon": polygon_json(plan.to_world(stair.placed.rect), nd),
                  "run_along_joint": stair.run_along_joint, "offset_from_joint_middle_ft": round(stair.placed.offset_ft, 3),
                  "on_joint": bool(chosen.joints), "same_position_all_levels": True,
                  "headroom_ok": True, "catalog_target_sqft": stair_target_sqft,
                  "area_delta_sqft": round(shape.area_sqft - stair_target_sqft, 2),
                  "rules": limits.to_dict()},
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


def _ground_block(plan: LotPlan, ground: BaseGeometry, garage: BaseGeometry | None, garage_sqft: float,
                  nd: int) -> dict[str, Any]:
    x0, y0, x1, y1 = ground.bounds
    return {"area_sqft": round(ground.area, 2), "width_ft": round(x1 - x0, 3), "depth_ft": round(y1 - y0, 3),
            "garage_sqft": round(garage_sqft, 2),
            "garage_polygon": polygon_json(plan.to_world(garage), nd) if garage is not None else None}


__all__ = ["DRAWN", "GROUND_NOT_REALIZED", "NOT_CONTAINED", "S1_STATUSES", "STAIR_DOES_NOT_FIT", "allowed_polygon",
           "draw_cell"]
