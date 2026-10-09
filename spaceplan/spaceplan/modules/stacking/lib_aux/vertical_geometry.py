"""Domain-free vertical geometry: plane offsets, roof rise and the sides of a floor.

Pure arithmetic on lengths; no rule, catalog or contract knowledge.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


def plane_offset(height_above_start: float, angle_from_vertical_deg: float) -> float:
    """Horizontal distance a point at `height_above_start` must sit inside a plane that leans inward at
    `angle_from_vertical_deg` from its starting line (0 when the point is below the start)."""
    if height_above_start <= 0.0:
        return 0.0
    return height_above_start * math.tan(math.radians(angle_from_vertical_deg))


def roof_rise(span: float, rise_per_run: float) -> float:
    """Rise of a symmetric pitched roof over `span` (ridge in the middle)."""
    return max(span, 0.0) / 2.0 * rise_per_run


@dataclass(frozen=True)
class FloorSides:
    """Width (street-facing), depth and short side of a floor approximated by a rectangle."""

    width: float
    depth: float

    @property
    def short(self) -> float:
        return min(self.width, self.depth)

    @property
    def short_is_width(self) -> bool:
        return self.width <= self.depth


def floor_sides(area: float, width: float) -> FloorSides:
    """Rectangle of `area` with the given street-facing `width` (the width is capped so depth >= 0)."""
    if width <= 0.0 or area <= 0.0:
        return FloorSides(max(width, 0.0), 0.0)
    return FloorSides(width, area / width)


def scaled_sides(base: FloorSides, area: float) -> FloorSides:
    """Rectangle of `area` with the proportions of `base` (an upper floor over a ground floor, before S1 draws it)."""
    base_area = base.width * base.depth
    if base_area <= 0.0 or area <= 0.0:
        return FloorSides(0.0, 0.0)
    k = math.sqrt(area / base_area)
    return FloorSides(base.width * k, base.depth * k)


__all__ = ["FloorSides", "floor_sides", "plane_offset", "roof_rise", "scaled_sides"]
