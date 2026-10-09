"""Domain-free plan geometry for stage S1: bands cut to an area, joints, rectangles along a line, insets.

Everything works in a local frame where x runs along the front of the lot and y away from the street; no rule,
catalog or contract knowledge lives here.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from shapely.geometry import LineString, MultiLineString, Polygon, box
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

TOL = 1e-6
LOW, HIGH = "low", "high"
OFFSET_DIGITS = 9                # rounding of the offsets that order the candidates (ties broken by position)


def band(geom: BaseGeometry, axis: str, lo: float, hi: float) -> BaseGeometry:
    """Part of `geom` with lo <= coordinate <= hi along `axis` ('x' or 'y')."""
    minx, miny, maxx, maxy = geom.bounds
    if axis == "y":
        return geom.intersection(box(minx - 1.0, lo, maxx + 1.0, hi))
    return geom.intersection(box(lo, miny - 1.0, hi, maxy + 1.0))


def cut_band(geom: BaseGeometry, area: float, axis: str = "y", side: str = LOW, rounds: int = 60,
             tol: float = 1.0) -> tuple[BaseGeometry, float] | None:
    """Band of `geom` starting at its `side` end along `axis` whose area is `area` (bisection on the cut line).

    Returns (band, cut coordinate), or None when `geom` holds less than `area - tol`."""
    if geom.is_empty or area <= 0.0 or geom.area < area - tol:
        return None
    minx, miny, maxx, maxy = geom.bounds
    lo, hi = (miny, maxy) if axis == "y" else (minx, maxx)
    start = lo if side == LOW else hi
    a, b = lo, hi
    for _ in range(rounds):
        mid = 0.5 * (a + b)
        part = band(geom, axis, start, mid) if side == LOW else band(geom, axis, mid, start)
        if (part.area < area) == (side == LOW):
            a = mid
        else:
            b = mid
    cut = 0.5 * (a + b)
    part = band(geom, axis, start, cut) if side == LOW else band(geom, axis, cut, start)
    return part, cut


def lines_of(geom: BaseGeometry, min_length: float = TOL) -> list[LineString]:
    """The line pieces of a geometry (a difference of boundaries), longer than `min_length`."""
    if geom.is_empty:
        return []
    if isinstance(geom, LineString):
        parts = [geom]
    elif isinstance(geom, MultiLineString):
        parts = list(geom.geoms)
    else:
        parts = [g for g in getattr(geom, "geoms", []) if isinstance(g, LineString)]
    return [p for p in parts if p.length > min_length]


def segments_of(line: LineString, tol: float = 1e-6) -> list[LineString]:
    """Straight pieces of a polyline (consecutive collinear segments merged)."""
    coords = list(line.coords)
    out, start = [], 0
    for i in range(1, len(coords) - 1):
        (ax, ay), (bx, by), (cx, cy) = coords[start], coords[i], coords[i + 1]
        if abs((bx - ax) * (cy - ay) - (by - ay) * (cx - ax)) > tol * max(1.0, line.length):
            out.append(LineString([coords[start], coords[i]]))
            start = i
    out.append(LineString([coords[start], coords[-1]]))
    return [s for s in out if s.length > tol]


def joint_lines(part: BaseGeometry, whole: BaseGeometry, tol: float = 1e-3) -> list[LineString]:
    """Straight edges of `part` that do not lie on the boundary of `whole` (where a part of a plan meets the
    rest), longest first."""
    inner = part.boundary.difference(whole.boundary.buffer(tol))
    pieces = [s for line in lines_of(inner, min_length=10 * tol) for s in segments_of(line)]
    return sorted((s for s in pieces if s.length > 10 * tol), key=lambda s: -s.length)


def is_axis_aligned(line: LineString, tol: float = 1e-6) -> str | None:
    """'x' when the line runs along x, 'y' when along y, None otherwise."""
    coords = list(line.coords)
    if all(abs(c[1] - coords[0][1]) <= tol for c in coords):
        return "x"
    if all(abs(c[0] - coords[0][0]) <= tol for c in coords):
        return "y"
    return None


@dataclass(frozen=True)
class Placed:
    """A rectangle placed against a line: its polygon, its offset from the line's middle and its orientation."""

    rect: Polygon
    offset_ft: float
    along_ft: float
    across_ft: float


def rects_along_line(line: LineString, along: float, across: float, step: float,
                     inside: BaseGeometry, tol: float = 1e-3) -> list[Placed]:
    """Rectangles of `along` x `across` touching an axis-aligned `line` on either side, sliding along it every
    `step`, kept when they lie inside `inside`; sorted by distance of their centre to the line's middle."""
    direction = is_axis_aligned(line)
    if direction is None or along > line.length + tol:
        return []
    (x0, y0), (x1, y1) = line.coords[0], line.coords[-1]
    out = []
    if direction == "x":
        a, b = sorted((x0, x1))
        mid = 0.5 * (a + b)
        n = int((b - a - along) // step) if b - a > along else 0
        starts = sorted({a + k * step for k in range(n + 1)} | {b - along, mid - along / 2})
        for s in starts:
            if s < a - tol or s + along > b + tol:
                continue
            for r in (box(s, y0, s + along, y0 + across), box(s, y0 - across, s + along, y0)):
                if inside.buffer(tol).contains(r):
                    out.append(Placed(r, abs(s + along / 2 - mid), along, across))
    else:
        a, b = sorted((y0, y1))
        mid = 0.5 * (a + b)
        n = int((b - a - along) // step) if b - a > along else 0
        starts = sorted({a + k * step for k in range(n + 1)} | {b - along, mid - along / 2})
        for s in starts:
            if s < a - tol or s + along > b + tol:
                continue
            for r in (box(x0, s, x0 + across, s + along), box(x0 - across, s, x0, s + along)):
                if inside.buffer(tol).contains(r):
                    out.append(Placed(r, abs(s + along / 2 - mid), along, across))
    return sorted(out, key=lambda p: (round(p.offset_ft, OFFSET_DIGITS), p.rect.bounds))


def inset_from_lines(geom: BaseGeometry, lines: Iterable[tuple[LineString, float]]) -> BaseGeometry:
    """`geom` without the points closer than each line's distance to that line (Euclidean)."""
    cuts = [line.buffer(d, cap_style="round") for line, d in lines if d > 0.0]
    if not cuts:
        return geom
    return geom.difference(unary_union(cuts))


def overlap_area(a: BaseGeometry | None, b: BaseGeometry | None) -> float:
    if a is None or b is None or a.is_empty or b.is_empty:
        return 0.0
    return a.intersection(b).area


def polygon_json(geom: BaseGeometry | None, ndigits: int = 3) -> dict | None:
    """GeoJSON-like dict of a polygonal geometry with rounded coordinates (None for empty)."""
    if geom is None or geom.is_empty:
        return None
    polys = [geom] if isinstance(geom, Polygon) else [g for g in getattr(geom, "geoms", []) if isinstance(g, Polygon)]
    rings = [[[[round(x, ndigits), round(y, ndigits)] for x, y in p.exterior.coords]] for p in polys if p.area > TOL]
    if not rings:
        return None
    if len(rings) == 1:
        return {"type": "Polygon", "coordinates": rings[0]}
    return {"type": "MultiPolygon", "coordinates": rings}


__all__ = ["HIGH", "LOW", "Placed", "band", "cut_band", "inset_from_lines", "is_axis_aligned", "joint_lines",
           "lines_of", "overlap_area", "polygon_json", "rects_along_line", "segments_of"]
