"""Roof of the drawn upper floor against the 131.0444 angled plane (step 6.7a, stage S1).

Stage S0 put the top floor's walls on the side setback line (worst case). Stage S1 knows where the upper floor
is: the roof's key points (eave and parapet corners at their height, the ridge ends at the top) are measured to
each side lot line, and each must sit at least the setback plus the plane offset at its height (131.0444,
read through the S0 height envelope) away. The front plane only applies above its trigger height. The roof is
tried in the catalog's order (default span, ridge turned, flat roof); the first inside the plane is kept.
"""

from __future__ import annotations

from typing import Any

from shapely.geometry import LineString, Point
from shapely.geometry.base import BaseGeometry

from spaceplan.core.lib.rules import RuleSet
from spaceplan.modules.stacking.lib.height_check import EXCEEDS_HEIGHT, PLANE_GOVERNS, WITHIN_PLANE
from spaceplan.modules.stacking.lib.lot_plan import LotPlan
from spaceplan.modules.stacking.lib.vertical_rules import HeightEnvelope, overall_height_limit
from spaceplan.modules.stacking.lib_aux.vertical_geometry import plane_offset, roof_rise

TOL = 1e-6
PLANE_TOL = 1e-3                 # ft: a corner lying on a setback line (drawn to 3 decimals) is not a breach
RIDGE_ALONG_Y, RIDGE_ALONG_X = "ridge_along_depth", "ridge_along_front"


def _ridge(poly: BaseGeometry, along: str) -> LineString | None:
    x0, y0, x1, y1 = poly.bounds
    xc, yc = 0.5 * (x0 + x1), 0.5 * (y0 + y1)
    line = LineString([(xc, y0 - 1), (xc, y1 + 1)]) if along == RIDGE_ALONG_Y else LineString([(x0 - 1, yc), (x1 + 1, yc)])
    cut = line.intersection(poly)
    return cut if isinstance(cut, LineString) and not cut.is_empty else None


def roof_points(poly: BaseGeometry, roof: dict[str, Any], plate_ft: float, ridge: str | None) -> tuple[list, float]:
    """(x, y, z) key points of a roof over `poly` and its top height. A pitched roof spans across its ridge."""
    corners = [(x, y) for x, y in poly.exterior.coords[:-1]] if hasattr(poly, "exterior") else \
        [(x, y) for g in poly.geoms for x, y in g.exterior.coords[:-1]]
    if roof["kind"] == "flat":
        top = plate_ft + roof["parapet_ft"]
        return [(x, y, top) for x, y in corners], top
    x0, y0, x1, y1 = poly.bounds
    span = (x1 - x0) if ridge == RIDGE_ALONG_Y else (y1 - y0)
    top = plate_ft + roof_rise(span, roof["pitch_rise_per_run"])
    points = [(x, y, plate_ft) for x, y in corners]
    line = _ridge(poly, ridge)
    if line is not None:
        points += [(x, y, top) for x, y in (line.coords[0], line.coords[-1])]
    return points, top


def default_ridge(poly: BaseGeometry) -> str:
    """S0's default: the roof spans the short side (ridge along the long side)."""
    x0, y0, x1, y1 = poly.bounds
    return RIDGE_ALONG_Y if (x1 - x0) <= (y1 - y0) else RIDGE_ALONG_X


def plane_margin(points: list, plan: LotPlan, envelope: HeightEnvelope) -> tuple[float, str | None]:
    """Smallest clearance (ft) of the roof points to the side planes (and front planes above their trigger);
    negative when a point pokes through. Also returns the edge that governs."""
    worst, governing = float("inf"), None
    if envelope.angle_deg is None:
        return worst, None
    planes = [(sl, envelope.start_ft) for sl in plan.side_lines]
    if envelope.front_trigger_ft is not None:
        planes += [(sl, envelope.front_trigger_ft) for sl in plan.front_lines]
    for sl, start in planes:
        for x, y, z in points:
            if sl.boundary_class != "side" and z <= start + TOL:
                continue
            need = sl.setback_ft + plane_offset(z - start, envelope.angle_deg)
            margin = Point(x, y).distance(sl.line) - need
            if margin < worst:
                worst, governing = margin, sl.edge_id
    return worst, governing


def check_roof(poly: BaseGeometry, roof: dict[str, Any], ridge: str | None, plate_ft: float, plan: LotPlan,
               envelope: HeightEnvelope, rs: RuleSet, grade_diff_ft: float) -> dict[str, Any]:
    points, top = roof_points(poly, roof, plate_ft, ridge)
    margin, edge = plane_margin(points, plan, envelope)
    limit = overall_height_limit(rs, envelope.overall_max_ft, grade_diff_ft)
    if top > envelope.overall_max_ft + TOL or top + grade_diff_ft > limit + TOL:
        status = EXCEEDS_HEIGHT
    elif margin < -PLANE_TOL:
        status = PLANE_GOVERNS
    else:
        status = WITHIN_PLANE
    return {"roof_id": roof["roof_id"], "ridge": ridge if roof["kind"] == "pitched" else None,
            "status": status, "top_ft": round(top, 4),
            "plane_margin_ft": None if margin == float("inf") else round(margin, 4),
            "inset_needed_ft": round(max(0.0, -margin), 4) if status == PLANE_GOVERNS else 0.0,
            "governing_edge": edge if status == PLANE_GOVERNS else None}


def roof_sequence(poly: BaseGeometry, default_roof: dict[str, Any], flat_roof: dict[str, Any],
                  order: list[str]) -> list[tuple[str, dict[str, Any], str | None]]:
    """(step, roof, ridge) in the catalog's order: default span, ridge turned, flat roof."""
    ridge = default_ridge(poly) if default_roof["kind"] == "pitched" else None
    turned = (RIDGE_ALONG_X if ridge == RIDGE_ALONG_Y else RIDGE_ALONG_Y) if ridge else None
    steps = {"default": (default_roof, ridge), "rotated": (default_roof, turned), "flat": (flat_roof, None)}
    out = []
    for step in order:
        roof, r = steps[step]
        if step == "rotated" and default_roof["kind"] != "pitched":
            continue
        out.append((step, roof, r))
    return out


__all__ = ["RIDGE_ALONG_X", "RIDGE_ALONG_Y", "check_roof", "default_ridge", "plane_margin", "roof_points",
           "roof_sequence"]
