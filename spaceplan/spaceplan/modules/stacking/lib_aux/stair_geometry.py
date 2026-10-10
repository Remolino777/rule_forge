"""Domain-free geometry of a stair made of rectangular parts: clear height under each part, bands by height and the
eight placements (directions and hands) of a shape that keep its bounding box.

A shape lives in its own frame (u, v) with bounding box [0, L] x [0, S]. Each part is an axis-aligned rectangle with a
clear height under it that grows linearly along an axis (a flight) or is constant (a landing). Ends are segments with
the direction a person faces when stepping off the stair there. No rule, catalog or contract knowledge lives here.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from functools import cached_property

from shapely.geometry import LineString, Polygon, box
from shapely.ops import unary_union

Rect = tuple[float, float, float, float]  # (x0, y0, x1, y1)
Vec = tuple[float, float]
TOL = 1e-9

# The 8 symmetries of the square as 2x2 matrices (a, b, c, d): (x, y) -> (a x + b y, c x + d y).
KEEP_BOX = ((1, 0, 0, 1), (-1, 0, 0, 1), (1, 0, 0, -1), (-1, 0, 0, -1))
SWAP_BOX = ((0, 1, 1, 0), (0, -1, 1, 0), (0, 1, -1, 0), (0, -1, -1, 0))


@dataclass(frozen=True)
class Part:
    """A rectangle of the stair; clear height under it: h0 + slope * s, with s measured along `axis` ('u'/'v' or
    'x'/'y' once placed) from `origin` in the direction `sign` (+1/-1). A landing has slope 0."""

    kind: str
    rect: Rect
    axis: str
    sign: int
    origin: float
    h0: float
    slope: float

    def height_at(self, coord: float) -> float:
        return self.h0 + self.slope * self.sign * (coord - self.origin)

    @property
    def polygon(self) -> Polygon:
        return box(*self.rect)


@dataclass(frozen=True)
class End:
    """An end of the stair: the edge a person crosses there and the direction they face stepping off."""

    edge: tuple[tuple[float, float], tuple[float, float]]
    outward: Vec

    @property
    def line(self) -> LineString:
        return LineString(self.edge)


@dataclass(frozen=True)
class StairGeometry:
    parts: tuple[Part, ...]
    bottom: End
    top: End

    @cached_property
    def footprint(self):
        if len(self.parts) == 1:
            return self.parts[0].polygon
        return unary_union([p.polygon for p in self.parts])

    @property
    def bounds(self) -> Rect:
        return self.footprint.bounds


def _axis_index(axis: str) -> int:
    return 0 if axis in ("u", "x") else 1


def band_rect(part: Part, lo: float, hi: float | None = None) -> Rect | None:
    """Sub-rectangle of a part where lo <= clear height (< hi); None when empty."""
    x0, y0, x1, y1 = part.rect
    if part.slope == 0.0:
        ok = part.h0 >= lo - TOL and (hi is None or part.h0 < hi - TOL)
        return part.rect if ok else None
    i = _axis_index(part.axis)
    a, b = (x0, x1) if i == 0 else (y0, y1)

    def coord_at(h: float) -> float:
        return part.origin + part.sign * (h - part.h0) / part.slope

    c_lo = coord_at(lo)
    c_hi = coord_at(hi) if hi is not None else (b if part.sign > 0 else a)
    lo_c, hi_c = sorted((c_lo, c_hi))
    lo_c, hi_c = max(lo_c, a), min(hi_c, b)
    if hi_c - lo_c <= TOL:
        return None
    return (lo_c, y0, hi_c, y1) if i == 0 else (x0, lo_c, x1, hi_c)


def band_area(geom: StairGeometry, lo: float, hi: float | None = None) -> float:
    total = 0.0
    for p in geom.parts:
        r = band_rect(p, lo, hi)
        if r is not None:
            total += (r[2] - r[0]) * (r[3] - r[1])
    return total


def _apply(m, p):
    a, b, c, d = m
    return (a * p[0] + b * p[1], c * p[0] + d * p[1])


def transforms_for(size: tuple[float, float], target: Rect, tol: float = 1e-6) -> list[tuple]:
    """Symmetries that map a shape of bounding box `size` (L, S) onto the rectangle `target` (same dimensions,
    possibly turned 90 degrees)."""
    L, S = size
    w, h = target[2] - target[0], target[3] - target[1]
    out = []
    if abs(w - L) <= tol and abs(h - S) <= tol:
        out += list(KEEP_BOX)
    if abs(w - S) <= tol and abs(h - L) <= tol:
        out += list(SWAP_BOX)
    return out


def place(geom: StairGeometry, size: tuple[float, float], m: tuple, target: Rect) -> StairGeometry:
    """The shape moved by symmetry `m` and translated so its bounding box lands on `target`."""
    L, S = size
    corners = [_apply(m, c) for c in ((0, 0), (L, 0), (0, S), (L, S))]
    dx = target[0] - min(c[0] for c in corners)
    dy = target[1] - min(c[1] for c in corners)

    def pt(p):
        q = _apply(m, p)
        return (q[0] + dx, q[1] + dy)

    def rect(r):
        a, b = pt((r[0], r[1])), pt((r[2], r[3]))
        return (min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1]))

    parts = []
    for p in geom.parts:
        axis_vec = (1, 0) if p.axis == "u" else (0, 1)
        new_vec = _apply(m, axis_vec)
        new_axis = "x" if new_vec[0] != 0 else "y"
        new_sign = p.sign * (new_vec[0] if new_vec[0] != 0 else new_vec[1])
        origin_pt = (p.origin, 0.0) if p.axis == "u" else (0.0, p.origin)
        o = pt(origin_pt)
        parts.append(replace(p, rect=rect(p.rect), axis=new_axis, sign=int(new_sign),
                             origin=o[0] if new_axis == "x" else o[1]))

    def end(e: End) -> End:
        return End((pt(e.edge[0]), pt(e.edge[1])), _apply(m, e.outward))

    return StairGeometry(tuple(parts), end(geom.bottom), end(geom.top))


ALIGNS = ("centre", "start", "end")


def zone_beyond(end: End, depth: float, width: float, align: str = "centre") -> Polygon:
    """Rectangle of `depth` x `width` in front of an end, on the side it faces; when wider than the edge it is
    centred on it or aligned with its start or its end (lowest coordinate or highest)."""
    (x0, y0), (x1, y1) = end.edge
    ox, oy = end.outward
    if abs(ox) > abs(oy):  # facing +-x: the edge runs along y
        lo, hi = sorted((y0, y1))
        a, b = _span(lo, hi, width, align)
        xa, xb = (x0, x0 + depth) if ox > 0 else (x0 - depth, x0)
        return box(xa, a, xb, b)
    lo, hi = sorted((x0, x1))
    a, b = _span(lo, hi, width, align)
    ya, yb = (y0, y0 + depth) if oy > 0 else (y0 - depth, y0)
    return box(a, ya, b, yb)


def _span(lo: float, hi: float, width: float, align: str) -> tuple[float, float]:
    w = max(width, hi - lo)
    if align == "start":
        return lo, lo + w
    if align == "end":
        return hi - w, hi
    c = 0.5 * (lo + hi)
    return c - w / 2.0, c + w / 2.0


def extend_rect(rect: Rect, axis: str, sign: int, length: float) -> Rect:
    """`rect` grown by `length` along `axis` in direction `sign`."""
    x0, y0, x1, y1 = rect
    if axis in ("x", "u"):
        return (x0, y0, x1 + length, y1) if sign > 0 else (x0 - length, y0, x1, y1)
    return (x0, y0, x1, y1 + length) if sign > 0 else (x0, y0 - length, x1, y1)


__all__ = ["ALIGNS", "KEEP_BOX", "SWAP_BOX", "End", "Part", "StairGeometry", "band_area", "band_rect", "extend_rect", "place",
           "transforms_for", "zone_beyond"]
