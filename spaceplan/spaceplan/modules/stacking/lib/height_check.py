"""Height budget of a stack of levels (step 6.7, stage S0): plate, roof top and the angled envelope plane.

For each roof type the top floor gets a wall plate and a roof. The side walls meet the plane of 131.0444 that
starts on the required side setback line: the check returns how far inside that line the walls (or the ridge)
must sit, whether the front plane is triggered and whether the overall height is exceeded. The ground floor is
approximated by a rectangle of its area with the street-facing width of the strategy and an upper floor by the
same proportions scaled to its area (S1 draws both).
"""

from __future__ import annotations

from typing import Any

from spaceplan.core.lib.rules import RuleSet
from spaceplan.modules.stacking.lib.vertical_rules import HeightEnvelope, overall_height_limit
from spaceplan.modules.stacking.lib_aux.vertical_geometry import (
    floor_sides,
    plane_offset,
    roof_rise,
    scaled_sides,
)

WITHIN_PLANE, PLANE_GOVERNS, EXCEEDS_HEIGHT = "within_plane", "plane_governs", "exceeds_height"
STATUS_ORDER = (EXCEEDS_HEIGHT, PLANE_GOVERNS, WITHIN_PLANE)
TOL = 1e-6


def roof_profile(roof: dict[str, Any], plate_ft: float, short_side: float, short_is_width: bool) -> dict[str, Any]:
    """Edge height on the side walls, top height and the run from the side wall to the top."""
    if roof["kind"] == "flat":
        top = plate_ft + roof["parapet_ft"]
        return {"side_wall": "parapet", "side_edge_ft": top, "top_ft": top, "run_to_top_ft": 0.0}
    top = plate_ft + roof_rise(short_side, roof["pitch_rise_per_run"])
    if short_is_width:  # ridge parallel to the side lot lines: eaves face the sides
        return {"side_wall": "eave", "side_edge_ft": plate_ft, "top_ft": top, "run_to_top_ft": short_side / 2.0}
    return {"side_wall": "gable", "side_edge_ft": top, "top_ft": top, "run_to_top_ft": 0.0}


def check_height(levels: list[dict[str, Any]], width_ft: float, roof: dict[str, Any], plate_above_floor_ft: float,
                 envelope: HeightEnvelope, rs: RuleSet, slope: float | None) -> dict[str, Any]:
    """Height check of one stack with one roof type."""
    top_level = levels[-1]
    plate = top_level["finish_floor_ft"] + plate_above_floor_ft
    ground_sides = floor_sides(levels[0]["gross_sqft"], width_ft)
    top_sides = scaled_sides(ground_sides, top_level["gross_sqft"])
    profile = roof_profile(roof, plate, top_sides.short, top_sides.short_is_width)
    top = profile["top_ft"]
    if envelope.angle_deg is None:
        inset = 0.0
    else:
        inset = max(plane_offset(profile["side_edge_ft"] - envelope.start_ft, envelope.angle_deg),
                    plane_offset(top - envelope.start_ft, envelope.angle_deg) - profile["run_to_top_ft"], 0.0)
    grade_diff = (slope or 0.0) * ground_sides.depth
    overall = top + grade_diff
    overall_limit = overall_height_limit(rs, envelope.overall_max_ft, grade_diff)
    if top > envelope.overall_max_ft + TOL or overall > overall_limit + TOL:
        status = EXCEEDS_HEIGHT
    elif inset > TOL:
        status = PLANE_GOVERNS
    else:
        status = WITHIN_PLANE
    front = envelope.front_trigger_ft is not None and top > envelope.front_trigger_ft + TOL
    return {
        "roof_id": roof["roof_id"],
        "status": status,
        "plate_ft": round(plate, 4),
        "top_ft": round(top, 4),
        "side_wall": profile["side_wall"],
        "side_inset_ft": round(inset, 4),
        "front_plane_required": front,
        "top_floor_width_ft": round(top_sides.width, 4),
        "top_floor_depth_ft": round(top_sides.depth, 4),
        "grade_differential_ft": round(grade_diff, 4),
        "overall_height_ft": round(overall, 4),
        "overall_limit_ft": round(overall_limit, 4),
        "headroom_ft": round(envelope.overall_max_ft - top, 4),
    }


def worst_status(statuses: list[str]) -> str:
    return min(statuses, key=STATUS_ORDER.index)


def best_status(statuses: list[str]) -> str:
    return max(statuses, key=STATUS_ORDER.index)


__all__ = ["EXCEEDS_HEIGHT", "PLANE_GOVERNS", "STATUS_ORDER", "WITHIN_PLANE", "best_status", "check_height",
           "roof_profile", "worst_status"]
