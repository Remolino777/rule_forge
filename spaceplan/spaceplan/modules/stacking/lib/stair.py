"""The stair as an object (step 6.7a, stage S1): type, risers and treads, footprint and position at the joint.

The geometry follows the CRC limits (stair_rules) with the catalog's design values: the fewest equal risers at
or below the maximum riser for the floor-to-floor height, treads one fewer than risers per flight, a landing at
the top of each straight run (the bottom one lands on the ground-floor hall). The stair is the same rectangle on
both levels (its opening in the upper floor is its whole footprint, so the headroom holds by construction).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from shapely.geometry.base import BaseGeometry

from spaceplan.modules.stacking.lib.stair_rules import StairLimits
from spaceplan.modules.stacking.lib_aux.plan_geometry import Placed, overlap_area, rects_along_line

INCH_FT = 1.0 / 12.0


@dataclass(frozen=True)
class StairShape:
    """Footprint of one stair type for a floor-to-floor height (length along the run, width across)."""

    stair_id: str
    risers: int
    riser_ft: float
    treads: int
    tread_ft: float
    width_ft: float
    landing_ft: float
    length_ft: float              # bounding rectangle along the run
    span_ft: float                # bounding rectangle across the run
    area_sqft: float              # area the stair takes (L-turn: less than its bounding rectangle)

    def to_dict(self) -> dict[str, Any]:
        return {"stair_id": self.stair_id, "risers": self.risers, "riser_in": round(self.riser_ft / INCH_FT, 3),
                "treads": self.treads, "tread_in": round(self.tread_ft / INCH_FT, 3),
                "width_ft": round(self.width_ft, 3), "landing_ft": round(self.landing_ft, 3),
                "length_ft": round(self.length_ft, 3), "span_ft": round(self.span_ft, 3),
                "area_sqft": round(self.area_sqft, 2)}


def risers_for(floor_to_floor_ft: float, riser_max_ft: float) -> int:
    return max(1, math.ceil(floor_to_floor_ft / riser_max_ft - 1e-9))


def stair_shape(stair_type: dict[str, Any], floor_to_floor_ft: float, limits: StairLimits,
                design: dict[str, Any]) -> StairShape:
    n = risers_for(floor_to_floor_ft, limits.riser_max_ft)
    tread = max(design["tread_in"] * INCH_FT, limits.tread_min_ft)
    width = max(design["width_ft"], limits.width_min_ft)
    landing = max(design["landing_ft"], limits.landing_min_ft, width)
    sid = stair_type["stair_id"]
    if sid == "straight":
        treads = n - 1
        length, span = treads * tread + landing, width
        area = length * span
    elif sid == "u_turn":
        r1 = math.ceil(n / 2)
        treads = (r1 - 1) + (n - r1 - 1)
        run = max(r1 - 1, n - r1 - 1) * tread
        length, span = run + landing, 2 * width + design["u_turn_gap_ft"]
        area = length * span
    elif sid == "l_turn":
        r1 = math.ceil(n / 2)
        t1, t2 = r1 - 1, n - r1 - 1
        treads = t1 + t2
        length, span = t1 * tread + landing, t2 * tread + landing
        area = width * length + width * t2 * tread
    else:
        raise ValueError(f"unknown stair type {sid!r}")
    return StairShape(sid, n, floor_to_floor_ft / n, treads, tread, width, landing, length, span, area)


@dataclass(frozen=True)
class StairPlacement:
    shape: StairShape
    placed: Placed
    joint_index: int
    run_along_joint: bool


def place_stair(shapes: list[StairShape], joints: list, upper: BaseGeometry, ground: BaseGeometry,
                garage: BaseGeometry | None, step: float, tol: float = 1e-3) -> StairPlacement | None:
    """First stair type (in order) that fits against a joint: inside the upper and the ground floor, out of the
    garage. Per type, the run along the joint is tried before the run across it, longer joints first, then the
    position closest to the joint's middle."""
    inside = upper.intersection(ground)
    for shape in shapes:
        for along_joint in (True, False):
            along, across = (shape.length_ft, shape.span_ft) if along_joint else (shape.span_ft, shape.length_ft)
            for j, joint in enumerate(joints):
                for p in rects_along_line(joint, along, across, step, inside, tol):
                    if overlap_area(p.rect, garage) > tol:
                        continue
                    return StairPlacement(shape, p, j, along_joint)
    return None


__all__ = ["StairPlacement", "StairShape", "place_stair", "risers_for", "stair_shape"]
