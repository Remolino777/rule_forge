"""Geometry of a structural frame (step 6.7a S2.2g): extents, edge lines and the windows where axes may stand.
Domain-free: lengths in feet, polygons from shapely; the rules (spans, bay sizes) come from the caller.

An "axis direction" follows stage S2's band convention: 'x' means the axes are vertical lines x = c (the bands are
column ranges), 'y' means horizontal lines y = c (the bands are row ranges).
"""

from __future__ import annotations

from itertools import pairwise

from shapely.geometry.base import BaseGeometry

EPS = 1e-6


def extent(poly: BaseGeometry, axis: str) -> tuple[float, float]:
    """(lo, hi) of a polygon across its axes: the x range for axis 'x', the y range for 'y'."""
    x0, y0, x1, y1 = poly.bounds
    return (x0, x1) if axis == "x" else (y0, y1)


def length_along(poly: BaseGeometry, axis: str) -> float:
    """Length of a polygon along its axes (the y range for axis 'x')."""
    x0, y0, x1, y1 = poly.bounds
    return (y1 - y0) if axis == "x" else (x1 - x0)


def edge_lines(poly: BaseGeometry | None, axis: str, min_len: float = 0.0) -> list[float]:
    """Coordinates of the polygon's edges that run along the axes (x of vertical edges for 'x'), longest first."""
    if poly is None or poly.is_empty:
        return []
    out: dict[float, float] = {}
    polys = getattr(poly, "geoms", [poly])
    for p in polys:
        cs = list(p.exterior.coords)
        for (ax, ay), (bx, by) in pairwise(cs):
            if axis == "x" and abs(ax - bx) < EPS:
                out[round(ax, 3)] = out.get(round(ax, 3), 0.0) + abs(by - ay)
            elif axis == "y" and abs(ay - by) < EPS:
                out[round(ay, 3)] = out.get(round(ay, 3), 0.0) + abs(bx - ax)
    return [c for c, n in sorted(out.items(), key=lambda kv: -kv[1]) if n + EPS >= min_len]


def snap(value: float, step: float, origin: float = 0.0) -> float:
    """`value` on the lattice origin + k * step."""
    return origin + round((value - origin) / step) * step


def axis_window(lo: float, hi: float, bay_min: float, bay_max: float, hall: float = 0.0) -> tuple[float, float] | None:
    """Positions p of the first axis such that the bays (lo, p) and (p + hall, hi) are within [bay_min, bay_max];
    None when there is none."""
    span = hi - lo - hall
    a = lo + max(bay_min, span - bay_max)
    b = lo + min(bay_max, span - bay_min)
    return (a, b) if a <= b + EPS else None


def inside(value: float, window: tuple[float, float]) -> bool:
    return window[0] - EPS <= value <= window[1] + EPS


__all__ = ["axis_window", "edge_lines", "extent", "inside", "length_along", "snap"]
