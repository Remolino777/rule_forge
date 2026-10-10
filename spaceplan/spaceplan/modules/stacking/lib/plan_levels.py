"""Ground floor, stand-in garage and upper-floor placements of a cell (step 6.7a, stage S1).

The ground floor is the band of the strategy's realizable footprint that starts on the front setback line and
holds the ground-floor gross area (the front-anchored footprint the site layer measures). The upper floor is a
band of the ground floor (rear or front) or a rectangle anchored on the garage corner, so it is contained in
the ground floor by construction. The joint is the part of the upper floor's outline that is not on the ground
floor's outline: where the two-story part meets the one-story part, and where the stair goes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from shapely.geometry import box
from shapely.geometry.base import BaseGeometry

from spaceplan.modules.stacking.lib_aux.plan_geometry import HIGH, LOW, cut_band, joint_lines

REAR, FRONT, OVER_GARAGE, COMPACT = "rear", "front", "over_garage", "compact"


def ground_floor(footprint: BaseGeometry, gross_sqft: float, geometry: dict[str, Any]) -> BaseGeometry | None:
    cut = cut_band(footprint, gross_sqft, "y", LOW, int(geometry["bisection_rounds"]),
                   geometry["area_tolerance_sqft"])
    return None if cut is None else cut[0]


def garage_area(cell: dict[str, Any], far_base_sqft: float) -> float:
    """Garage gross area of a cell: the area matrix's IC minus its garage-excluded IC, times the FAR base area
    (0 when the alternative is missing: no garage, or the garage never counted)."""
    alt = (cell.get("IC_alternatives") or {}).get("garage_excluded") or {}
    if alt.get("IC") is None or cell.get("IC") is None:
        return 0.0
    return max(0.0, (float(cell["IC"]) - float(alt["IC"])) * far_base_sqft)


def garage_rect(ground: BaseGeometry, area: float, cfg: dict[str, Any]) -> BaseGeometry | None:
    """Stand-in garage: a rectangle on the front line of the ground floor, on the configured side (no deeper than
    the ground floor: a shallow floor gets a wider garage of the same area)."""
    if area <= 0.0:
        return None
    x0, y0, x1, y1 = ground.bounds
    width = cfg["double_width_ft"] if area >= cfg["double_from_sqft"] else cfg["single_width_ft"]
    if width > cfg["max_width_fraction"] * (x1 - x0):
        width = cfg["single_width_ft"]
    depth = area / width
    if depth > y1 - y0:                    # shallow ground floor: the garage widens to keep its area
        depth = y1 - y0
        width = min(area / depth, x1 - x0)
    rect = box(x1 - width, y0, x1, y0 + depth) if cfg["side"] == "right" else box(x0, y0, x0 + width, y0 + depth)
    return rect.intersection(ground)


@dataclass(frozen=True)
class UpperCandidate:
    placement: str
    polygon: BaseGeometry | None
    joints: tuple
    reason: str | None = None


def upper_floor(placement: str, ground: BaseGeometry, gross_sqft: float, garage: BaseGeometry | None,
                garage_side: str, geometry: dict[str, Any], compact_min_depth_ft: float = 0.0) -> UpperCandidate:
    rounds, tol = int(geometry["bisection_rounds"]), geometry["area_tolerance_sqft"]
    if gross_sqft > ground.area + tol:
        return UpperCandidate(placement, None, (), "upper floor larger than the ground floor")
    if placement in (REAR, FRONT):
        cut = cut_band(ground, gross_sqft, "y", HIGH if placement == REAR else LOW, rounds, tol)
        if cut is None:
            return UpperCandidate(placement, None, (), "band does not hold the area")
        poly = cut[0]
    elif placement == OVER_GARAGE:
        if garage is None or garage.is_empty:
            return UpperCandidate(placement, None, (), "no garage")
        gx0, gy0, gx1, gy1 = garage.bounds
        depth = gy1 - gy0
        x0, _, x1, _ = ground.bounds
        width = gross_sqft / depth
        rect = box(gx1 - width, gy0, gx1, gy1) if garage_side == "right" else box(gx0, gy0, gx0 + width, gy1)
        poly = rect.intersection(ground)
        if width > x1 - x0 + 1e-6 or poly.area < gross_sqft - tol:
            return UpperCandidate(placement, None, (), "garage-anchored rectangle leaves the ground floor")
    elif placement == COMPACT:
        x0, y0, x1, y1 = ground.bounds
        depth = min(y1 - y0, max(compact_min_depth_ft, gross_sqft ** 0.5))
        width = gross_sqft / depth
        cx = 0.5 * (x0 + x1)
        poly = box(cx - width / 2, y1 - depth, cx + width / 2, y1).intersection(ground)
        if poly.area < gross_sqft - tol:
            return UpperCandidate(placement, None, (), "compact rectangle leaves the ground floor")
    else:
        raise ValueError(f"unknown upper-floor placement {placement!r}")
    return UpperCandidate(placement, poly, tuple(joint_lines(poly, ground)))


__all__ = ["COMPACT", "FRONT", "OVER_GARAGE", "REAR", "UpperCandidate", "garage_area", "garage_rect", "ground_floor",
           "upper_floor"]
