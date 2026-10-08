"""Planar geometry helpers.

Pure functions on points and Shapely geometries. No zoning knowledge lives here:
callers pass distances, frames and tolerances explicitly.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from itertools import pairwise

import numpy as np
import shapely
from shapely import affinity
from shapely.geometry import LineString, MultiPolygon, Polygon, box
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from spaceplan.core.lib_aux.tolerances import (
    BISECTION_ITERS,
    BUFFER_QUAD_SEGS,
    COVER_TOL_FT,
    RECT_GRID_STEP_FT,
    RECT_REFINE_ROUNDS,
)

Point = tuple[float, float]


# --------------------------------------------------------------------------- points & polylines


def signed_area(points: Sequence[Point]) -> float:
    """Shoelace area; positive for counter-clockwise rings."""
    total = 0.0
    n = len(points)
    for i in range(n):
        x0, y0 = points[i]
        x1, y1 = points[(i + 1) % n]
        total += x0 * y1 - x1 * y0
    return 0.5 * total


def polyline_length(points: Sequence[Point]) -> float:
    return sum(math.dist(a, b) for a, b in pairwise(points))


def midpoint(a: Point, b: Point) -> Point:
    return ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)


def discretize_arc(p0: Point, p1: Point, radius: float, bulge: str, chord_tol: float) -> list[Point]:
    """Points of the minor circular arc from p0 to p1, endpoints included.

    The ring is assumed counter-clockwise, so the lot interior lies to the left of p0->p1.
    bulge="outward": the arc bulges away from the interior (centre on the interior side).
    bulge="inward":  the arc bulges into the interior (e.g. a lot fronting a cul-de-sac bulb).
    """
    if bulge not in ("inward", "outward"):
        raise ValueError(f"bulge must be 'inward' or 'outward', got {bulge!r}")
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    chord = math.hypot(dx, dy)
    if chord == 0:
        raise ValueError("arc endpoints coincide")
    half = chord / 2.0
    if radius < half - 1e-9:
        raise ValueError(f"radius {radius} is smaller than half the chord ({half:.3f})")
    h = math.sqrt(max(radius**2 - half**2, 0.0))
    left = (-dy / chord, dx / chord)
    mx, my = midpoint(p0, p1)
    side = 1.0 if bulge == "outward" else -1.0
    cx, cy = mx + side * left[0] * h, my + side * left[1] * h
    a0 = math.atan2(p0[1] - cy, p0[0] - cx)
    a1 = math.atan2(p1[1] - cy, p1[0] - cx)
    sweep = (a1 - a0 + math.pi) % (2.0 * math.pi) - math.pi  # minor arc
    if chord_tol >= radius:
        max_step = math.pi / 2.0
    else:
        max_step = 2.0 * math.acos(1.0 - chord_tol / radius)
    n = max(2, math.ceil(abs(sweep) / max_step))
    pts = [
        (cx + radius * math.cos(a0 + sweep * k / n), cy + radius * math.sin(a0 + sweep * k / n))
        for k in range(n + 1)
    ]
    pts[0], pts[-1] = p0, p1
    return pts


def outward_bearing_deg(p0: Point, p1: Point) -> float:
    """Bearing (clockwise from +y) of the outward normal of a CCW ring edge p0->p1."""
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    nx, ny = dy, -dx  # right-hand normal = exterior for CCW rings
    return math.degrees(math.atan2(nx, ny)) % 360.0


# --------------------------------------------------------------------------- frames


@dataclass(frozen=True)
class Frame:
    """Local frame: origin in world coordinates and angle (rad) of the local +x axis."""

    origin: Point
    angle: float

    def to_local(self, geom: BaseGeometry) -> BaseGeometry:
        moved = affinity.translate(geom, -self.origin[0], -self.origin[1])
        return affinity.rotate(moved, -self.angle, origin=(0.0, 0.0), use_radians=True)

    def to_world(self, geom: BaseGeometry) -> BaseGeometry:
        turned = affinity.rotate(geom, self.angle, origin=(0.0, 0.0), use_radians=True)
        return affinity.translate(turned, self.origin[0], self.origin[1])

    def point_to_local(self, p: Point) -> Point:
        dx, dy = p[0] - self.origin[0], p[1] - self.origin[1]
        c, s = math.cos(self.angle), math.sin(self.angle)
        return (c * dx + s * dy, -s * dx + c * dy)


# --------------------------------------------------------------------------- polygons


def polygon_parts(geom: BaseGeometry) -> list[Polygon]:
    if geom.is_empty:
        return []
    if isinstance(geom, Polygon):
        return [geom]
    return [g for g in getattr(geom, "geoms", []) if isinstance(g, Polygon) and not g.is_empty]


def as_area_geometry(parts: Iterable[Polygon], min_area: float = 1e-6) -> BaseGeometry:
    kept = [p for p in parts if p.area > min_area]
    if not kept:
        return Polygon()
    return kept[0] if len(kept) == 1 else MultiPolygon(kept)


def is_convex(poly: Polygon, rel_tol: float = 1e-9) -> bool:
    return poly.convex_hull.area - poly.area <= rel_tol * max(1.0, poly.area)


def setback_envelope(
    lot: Polygon, items: Iterable[tuple[Sequence[Point], float]]
) -> BaseGeometry:
    """Lot minus the union of setback strips.

    Each item is (polyline of one boundary, setback distance). A point survives only if its
    euclidean distance to every boundary polyline is at least that boundary's setback. This is
    the union of one-sided inward strips at straight edges and convex corners, and it stays
    correct at reflex corners and on concave lots, where half-plane intersection fails.
    """
    strips = [
        LineString(points).buffer(
            distance, cap_style="round", join_style="round", quad_segs=BUFFER_QUAD_SEGS
        )
        for points, distance in items
        if distance > 0
    ]
    if not strips:
        return lot
    return as_area_geometry(polygon_parts(lot.difference(unary_union(strips))))


def halfplane_envelope(
    lot: Polygon, items: Iterable[tuple[Sequence[Point], float]]
) -> BaseGeometry:
    """Envelope by intersecting inner half-planes (perpendicular offset of each edge's line).

    Only meaningful for convex lots; used to check whether the distance semantics matter.
    """
    minx, miny, maxx, maxy = lot.bounds
    far = 10.0 * math.hypot(maxx - minx, maxy - miny) + 1.0
    result: BaseGeometry = lot
    for points, distance in items:
        if distance <= 0:
            continue
        for a, b in pairwise(points):
            length = math.dist(a, b)
            if length == 0:
                continue
            ux, uy = (b[0] - a[0]) / length, (b[1] - a[1]) / length
            nx, ny = -uy, ux
            ax, ay = a[0] + nx * distance, a[1] + ny * distance
            half = Polygon(
                [
                    (ax - ux * far, ay - uy * far),
                    (ax + ux * far, ay + uy * far),
                    (ax + ux * far + nx * far, ay + uy * far + ny * far),
                    (ax - ux * far + nx * far, ay - uy * far + ny * far),
                ]
            )
            result = result.intersection(half)
    return as_area_geometry(polygon_parts(result))


def clip_y(geom: BaseGeometry, y_min: float | None = None, y_max: float | None = None) -> BaseGeometry:
    """Part of a (local-frame) geometry between two horizontal lines."""
    if geom.is_empty:
        return Polygon()
    minx, miny, maxx, maxy = geom.bounds
    lo = miny - 1.0 if y_min is None else y_min
    hi = maxy + 1.0 if y_max is None else y_max
    if hi <= lo:
        return Polygon()
    return geom.intersection(box(minx - 1.0, lo, maxx + 1.0, hi))


def chord_length_at_y(geom: BaseGeometry, y: float) -> float:
    """Total length of the horizontal line y=const inside a local-frame geometry."""
    minx, _, maxx, _ = geom.bounds
    return LineString([(minx - 1.0, y), (maxx + 1.0, y)]).intersection(geom).length


# --------------------------------------------------------------------------- inscribed rectangle


@dataclass(frozen=True)
class InscribedRect:
    polygon: Polygon  # world coordinates
    area: float
    width: float  # along the frame's local x
    depth: float  # along the frame's local y


def max_inscribed_rect(
    geom: BaseGeometry,
    frame: Frame,
    step: float = RECT_GRID_STEP_FT,
    rounds: int = RECT_REFINE_ROUNDS,
) -> InscribedRect | None:
    """Largest rectangle aligned with the frame axes that fits inside geom.

    Grid search (maximal rectangle in a binary mask) followed by continuous refinement of each
    side by bisection, so the result is not limited to the grid resolution.
    """
    local = frame.to_local(geom)
    best: tuple[float, float, float, float] | None = None
    for part in polygon_parts(local):
        candidate = _max_rect_axis_aligned(part, step, rounds)
        if candidate is None:
            continue
        if best is None or _rect_area(candidate) > _rect_area(best):
            best = candidate
    if best is None:
        return None
    x0, y0, x1, y1 = best
    return InscribedRect(frame.to_world(box(x0, y0, x1, y1)), _rect_area(best), x1 - x0, y1 - y0)


def _rect_area(rect: tuple[float, float, float, float]) -> float:
    x0, y0, x1, y1 = rect
    return (x1 - x0) * (y1 - y0)


def _max_rect_axis_aligned(
    part: Polygon, step: float, rounds: int
) -> tuple[float, float, float, float] | None:
    minx, miny, maxx, maxy = part.bounds
    nx = max(1, math.ceil((maxx - minx) / step))
    ny = max(1, math.ceil((maxy - miny) / step))
    xs = np.linspace(minx, maxx, nx + 1)
    ys = np.linspace(miny, maxy, ny + 1)
    gx, gy = np.meshgrid(xs, ys)
    cover = part.buffer(COVER_TOL_FT)
    shapely.prepare(cover)
    nodes = shapely.intersects_xy(cover, gx.ravel(), gy.ravel()).reshape(gx.shape)
    cells = nodes[:-1, :-1] & nodes[1:, :-1] & nodes[:-1, 1:] & nodes[1:, 1:]
    found = _largest_true_rectangle(cells)
    if found is None:
        return None
    row, j0, j1, height = found
    x0, x1 = float(xs[j0]), float(xs[j1 + 1])
    y0, y1 = float(ys[row - height + 1]), float(ys[row + 1])
    # A notch narrower than the grid step can slip between nodes: shrink until truly inside.
    for _ in range(64):
        if cover.covers(box(x0, y0, x1, y1)):
            break
        shrink = step / 4.0
        x0, y0, x1, y1 = x0 + shrink, y0 + shrink, x1 - shrink, y1 - shrink
        if x1 <= x0 or y1 <= y0:
            return None
    else:
        return None
    return _refine_rect(cover, (x0, y0, x1, y1), part.bounds, rounds)


def _largest_true_rectangle(mask: np.ndarray) -> tuple[int, int, int, int] | None:
    """Maximal all-True rectangle; returns (last_row, first_col, last_col, height)."""
    rows, cols = mask.shape
    heights = [0] * cols
    best_area = 0
    best: tuple[int, int, int, int] | None = None
    for i in range(rows):
        row = mask[i].tolist()
        heights = [h + 1 if row[j] else 0 for j, h in enumerate(heights)]
        stack: list[tuple[int, int]] = []
        for j in range(cols + 1):
            h = heights[j] if j < cols else 0
            start = j
            while stack and stack[-1][1] >= h:
                s, sh = stack.pop()
                area = sh * (j - s)
                if area > best_area:
                    best_area, best = area, (i, s, j - 1, sh)
                start = s
            stack.append((start, h))
    return best


def _push_side(
    cover: BaseGeometry, make_box: Callable[[float], Polygon], current: float, limit: float
) -> float:
    """Move one rectangle side from `current` (feasible) toward `limit` as far as it stays inside."""
    if cover.covers(make_box(limit)):
        return limit
    lo, hi = current, limit
    for _ in range(BISECTION_ITERS):
        mid = 0.5 * (lo + hi)
        if cover.covers(make_box(mid)):
            lo = mid
        else:
            hi = mid
    return lo


def _refine_rect(
    cover: BaseGeometry,
    rect: tuple[float, float, float, float],
    bounds: tuple[float, float, float, float],
    rounds: int,
) -> tuple[float, float, float, float]:
    x0, y0, x1, y1 = rect
    bx0, by0, bx1, by1 = bounds
    for _ in range(rounds):
        x0 = _push_side(cover, lambda v: box(v, y0, x1, y1), x0, bx0)
        x1 = _push_side(cover, lambda v: box(x0, y0, v, y1), x1, bx1)
        y0 = _push_side(cover, lambda v: box(x0, v, x1, y1), y0, by0)
        y1 = _push_side(cover, lambda v: box(x0, y0, x1, v), y1, by1)
    return _pattern_search(cover, (x0, y0, x1, y1), bounds)


def _fit_x(cover: BaseGeometry, y0: float, y1: float, xc: float, bounds) -> tuple[float, float] | None:
    """Widest x-interval around xc whose rectangle over [y0, y1] stays inside cover."""
    eps = 1e-6
    if y1 <= y0 or not cover.covers(box(xc - eps, y0, xc + eps, y1)):
        return None
    x0 = _push_side(cover, lambda v: box(v, y0, xc + eps, y1), xc - eps, bounds[0])
    x1 = _push_side(cover, lambda v: box(x0, y0, v, y1), xc + eps, bounds[2])
    return x0, x1


def _fit_y(cover: BaseGeometry, x0: float, x1: float, yc: float, bounds) -> tuple[float, float] | None:
    eps = 1e-6
    if x1 <= x0 or not cover.covers(box(x0, yc - eps, x1, yc + eps)):
        return None
    y0 = _push_side(cover, lambda v: box(x0, v, x1, yc + eps), yc - eps, bounds[1])
    y1 = _push_side(cover, lambda v: box(x0, y0, x1, v), yc + eps, bounds[3])
    return y0, y1


def _pattern_search(
    cover: BaseGeometry,
    rect: tuple[float, float, float, float],
    bounds: tuple[float, float, float, float],
    start_step: float = RECT_GRID_STEP_FT * 4,
    min_step: float = 1e-4,
) -> tuple[float, float, float, float]:
    """Move one pair of sides at a time and re-fit the other pair; keep improvements.

    Escapes the greedy optimum of side pushing (e.g. a trapezoid where a slightly narrower but
    deeper rectangle is larger).
    """
    best = rect
    best_area = _rect_area(best)
    step = start_step
    while step >= min_step:
        improved = False
        x0, y0, x1, y1 = best
        candidates = []
        for ny0, ny1 in ((y0 - step, y1), (y0 + step, y1), (y0, y1 - step), (y0, y1 + step)):
            fitted = _fit_x(cover, ny0, ny1, 0.5 * (x0 + x1), bounds)
            if fitted:
                candidates.append((fitted[0], ny0, fitted[1], ny1))
        for nx0, nx1 in ((x0 - step, x1), (x0 + step, x1), (x0, x1 - step), (x0, x1 + step)):
            fitted = _fit_y(cover, nx0, nx1, 0.5 * (y0 + y1), bounds)
            if fitted:
                candidates.append((nx0, fitted[0], nx1, fitted[1]))
        for cand in candidates:
            area = _rect_area(cand)
            if area > best_area + 1e-9:
                best, best_area, improved = cand, area, True
        if not improved:
            step /= 2.0
    return best
