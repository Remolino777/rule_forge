"""Geometry of roof pieces (step 6.7a S2.2g): polygon parts, the wall a lean-to roof leans on, its fall direction and
depth, the long direction of a gable. Domain-free: lengths in feet, shapely polygons; no numbers of the domain."""

from __future__ import annotations

from itertools import pairwise

import numpy as np
from shapely.geometry import LineString, MultiPolygon, Polygon
from shapely.geometry.base import BaseGeometry

EPS = 1e-6


def parts(geom: BaseGeometry | None, min_area: float = 0.0) -> list[Polygon]:
    """The polygons of a geometry at least `min_area`, largest first."""
    if geom is None or geom.is_empty:
        return []
    polys = list(geom.geoms) if isinstance(geom, MultiPolygon) else [geom] if isinstance(geom, Polygon) else [
        g for g in getattr(geom, "geoms", []) if isinstance(g, Polygon)]
    return sorted((p for p in polys if p.area + EPS >= min_area), key=lambda p: -p.area)


def edges(poly: Polygon) -> list[LineString]:
    cs = list(poly.exterior.coords)
    return [LineString([a, b]) for a, b in pairwise(cs) if np.hypot(b[0] - a[0], b[1] - a[1]) > EPS]


def leaning_edge(piece: Polygon, wall: BaseGeometry | None, tol: float = 1e-3) -> LineString | None:
    """The longest edge of `piece` lying on the outline of `wall` (where a lean-to roof leans); None when none."""
    if wall is None or wall.is_empty:
        return None
    line = wall.boundary.buffer(tol)
    best, best_len = None, 0.0
    for e in edges(piece):
        on = e.intersection(line).length
        if on > best_len + EPS and on >= 0.5 * e.length:
            best, best_len = e, on
    return best


def fall(piece: Polygon, edge: LineString) -> tuple[tuple[float, float], float]:
    """(unit direction away from `edge` into the piece, depth of the piece along it)."""
    (ax, ay), (bx, by) = edge.coords[0], edge.coords[-1]
    n = np.array([-(by - ay), bx - ax], dtype=float)
    n /= np.linalg.norm(n) or 1.0
    c = np.array(piece.centroid.coords[0])
    if np.dot(c - np.array([ax, ay]), n) < 0:
        n = -n
    pts = np.array(piece.exterior.coords)
    d = (pts - np.array([ax, ay])) @ n
    return (float(n[0]), float(n[1])), float(d.max() - min(0.0, d.min()))


def long_axis(piece: Polygon) -> tuple[tuple[float, float], float, float]:
    """(unit direction of the long side of the piece's least rectangle, its length, its width)."""
    rect = piece.minimum_rotated_rectangle
    cs = list(rect.exterior.coords) if isinstance(rect, Polygon) else list(piece.exterior.coords)
    a, b, c = np.array(cs[0]), np.array(cs[1]), np.array(cs[2])
    u, v = b - a, c - b
    lu, lv = float(np.linalg.norm(u)), float(np.linalg.norm(v))
    if lu >= lv:
        return (float(u[0] / (lu or 1.0)), float(u[1] / (lu or 1.0))), lu, lv
    return (float(v[0] / (lv or 1.0)), float(v[1] / (lv or 1.0))), lv, lu


def split_on(geom: BaseGeometry, cutter: Polygon) -> list[Polygon]:
    """The polygons of `geom` cut by the lines of the bounding box of `cutter` (an L around a block becomes one
    rectangle per side of the block, and the corners)."""
    from shapely.geometry import box as _box

    if geom is None or geom.is_empty:
        return []
    gx0, gy0, gx1, gy1 = geom.bounds
    cx0, cy0, cx1, cy1 = cutter.bounds
    xs = sorted({gx0, gx1, *(x for x in (cx0, cx1) if gx0 < x < gx1)})
    ys = sorted({gy0, gy1, *(y for y in (cy0, cy1) if gy0 < y < gy1)})
    out = []
    for xa, xb in pairwise(xs):
        for ya, yb in pairwise(ys):
            out += parts(geom.intersection(_box(xa, ya, xb, yb)))
    return out


def far_edge(piece: Polygon, direction: tuple[float, float]) -> LineString:
    """The edge of the piece farthest along `direction` (the eave of a lean-to)."""
    n = np.array(direction)
    return max(edges(piece), key=lambda e: float(np.dot(np.array(e.centroid.coords[0]), n)))


__all__ = ["edges", "fall", "far_edge", "leaning_edge", "long_axis", "parts", "split_on"]
