"""Horizontal-section profile of a polygon (no domain knowledge).

A polygon whose every horizontal line meets it in one interval ("horizontally convex": convex
polygons, trapezoids, fans, most lots) has a left boundary xl(y) and a right boundary xr(y) that
are piecewise linear in y. This module integrates over those boundaries exactly:

    strip_area(ya, yb, c0, c1) = integral over [ya, yb] of max(0, min(xr, c1) - max(xl, c0)) dy

The integrand is piecewise linear between the polygon breakpoints and the points where a boundary
crosses c0 or c1, so the trapezoid rule on those points is exact. Every area-driven cut (slab depth,
column cut, stacked-cell cut) is the inverse of a monotone function and is found by bisection.
"""

from __future__ import annotations

import bisect
import math
from dataclasses import dataclass

INF = float("inf")
_TOL = 1e-9


@dataclass(frozen=True)
class _Segment:
    y0: float
    y1: float
    xl0: float
    xl1: float
    xr0: float
    xr1: float

    def xl(self, y: float) -> float:
        t = (y - self.y0) / (self.y1 - self.y0)
        return self.xl0 + t * (self.xl1 - self.xl0)

    def xr(self, y: float) -> float:
        t = (y - self.y0) / (self.y1 - self.y0)
        return self.xr0 + t * (self.xr1 - self.xr0)


def _crossing(y0: float, y1: float, a0: float, a1: float, value: float) -> float | None:
    """y in (y0, y1) where the linear function a (a0 at y0, a1 at y1) equals value."""
    if abs(a1 - a0) < _TOL:
        return None
    t = (value - a0) / (a1 - a0)
    if _TOL < t < 1.0 - _TOL:
        return y0 + t * (y1 - y0)
    return None


class SectionProfile:
    """Left/right boundaries of a horizontally convex polygon given by its vertices (any orientation)."""

    def __init__(self, vertices: list[tuple[float, float]]):
        pts = [tuple(map(float, p)) for p in vertices]
        if len(pts) > 1 and pts[0] == pts[-1]:
            pts = pts[:-1]
        if len(pts) < 3:
            raise ValueError("a section profile needs a polygon with at least 3 vertices")
        self.vertices = pts
        ys = []
        for y in sorted({p[1] for p in pts}):
            if not ys or y - ys[-1] > 1e-7:  # merge breakpoints closer than the tolerance
                ys.append(y)
        self.ymin, self.ymax = ys[0], ys[-1]
        edges = [(pts[i], pts[(i + 1) % len(pts)]) for i in range(len(pts))]
        segments = []
        for y0, y1 in zip(ys, ys[1:]):
            ym = 0.5 * (y0 + y1)
            xs0 = []
            for (ax, ay), (bx, by) in edges:
                lo, hi = min(ay, by), max(ay, by)
                if hi - lo < 1e-7 or not (lo - 1e-7 <= ym <= hi + 1e-7):
                    continue

                def at(y, ax=ax, ay=ay, bx=bx, by=by):
                    return ax + (y - ay) * (bx - ax) / (by - ay)

                xs0.append((at(ym), at(y0), at(y1)))
            if len(xs0) != 2:
                raise ValueError(f"polygon is not horizontally convex between y={y0:.3f} and y={y1:.3f}")
            left, right = sorted(xs0)
            segments.append(_Segment(y0, y1, left[1], left[2], right[1], right[2]))
        self.segments: tuple[_Segment, ...] = tuple(segments)
        self._starts = [s.y0 for s in segments]
        self._cache: dict = {}
        self.area = self.strip_area(self.ymin, self.ymax)

    def _memo(self, key, fn):
        hit = self._cache.get(key)
        if hit is None and key not in self._cache:
            if len(self._cache) > 200_000:
                self._cache.clear()
            hit = self._cache[key] = fn()
        return hit

    # ------------------------------------------------------------------ point queries

    def _segment_at(self, y: float) -> _Segment:
        i = bisect.bisect_right(self._starts, y) - 1
        return self.segments[min(max(i, 0), len(self.segments) - 1)]

    def interval(self, y: float) -> tuple[float, float]:
        """Section at y (clamped to the polygon's y-range)."""
        y = min(max(y, self.ymin), self.ymax)
        s = self._segment_at(y)
        return s.xl(y), s.xr(y)

    def width(self, y: float) -> float:
        lo, hi = self.interval(y)
        return max(0.0, hi - lo)

    def _pieces(self, ya: float, yb: float):
        """(segment, clipped y0, clipped y1) over [ya, yb]."""
        for s in self.segments:
            lo, hi = max(ya, s.y0), min(yb, s.y1)
            if hi - lo > _TOL:
                yield s, lo, hi

    def slab_interval(self, ya: float, yb: float) -> tuple[float, float]:
        """Widest x-interval contained in the polygon over the whole slab [ya, yb] (may be empty: hi < lo)."""
        return self._memo(("s", round(ya, 9), round(yb, 9)), lambda: self._slab_interval(ya, yb))

    def _slab_interval(self, ya: float, yb: float) -> tuple[float, float]:
        if ya < self.ymin - _TOL or yb > self.ymax + _TOL:
            return 0.0, -1.0
        lo, hi = -INF, INF
        pieces = list(self._pieces(ya, yb))
        if not pieces:
            x0, x1 = self.interval(ya)
            return x0, x1
        for s, y0, y1 in pieces:
            lo = max(lo, s.xl(y0), s.xl(y1))
            hi = min(hi, s.xr(y0), s.xr(y1))
        return lo, hi

    # ------------------------------------------------------------------ integrals

    def strip_area(self, ya: float, yb: float, c0: float = -INF, c1: float = INF) -> float:
        """Area of the polygon between y=ya..yb and x=c0..c1 (exact)."""
        if yb <= ya:
            return 0.0
        total = 0.0
        for s, y0, y1 in self._pieces(ya, yb):
            cuts = {y0, y1}
            for a0, a1 in ((s.xl0, s.xl1), (s.xr0, s.xr1)):
                for value in (c0, c1):
                    if math.isfinite(value):
                        y = _crossing(s.y0, s.y1, a0, a1, value)
                        if y is not None and y0 < y < y1:
                            cuts.add(y)
            ordered = sorted(cuts)

            def f(y, s=s):
                return max(0.0, min(s.xr(y), c1) - max(s.xl(y), c0))

            for u, v in zip(ordered, ordered[1:]):
                total += 0.5 * (f(u) + f(v)) * (v - u)
        return total

    def boundary_length(self, side: str, ya: float, yb: float, c: float | None = None) -> float:
        """Length of the left or right boundary over [ya, yb]; with c, only where it lies beyond x=c."""
        total = 0.0
        for s, y0, y1 in self._pieces(ya, yb):
            a = (s.xl if side == "left" else s.xr)
            cuts = [y0, y1]
            if c is not None:
                a0, a1 = (s.xl0, s.xl1) if side == "left" else (s.xr0, s.xr1)
                y = _crossing(s.y0, s.y1, a0, a1, c)
                if y is not None and y0 < y < y1:
                    cuts.insert(1, y)
            for u, v in zip(cuts, cuts[1:]):
                xm = a(0.5 * (u + v))
                if c is not None and not ((side == "left" and xm < c) or (side == "right" and xm > c)):
                    continue
                total += math.hypot(v - u, a(v) - a(u))
        return total

    # ------------------------------------------------------------------ inverse cuts

    @staticmethod
    def _bisect(fn, lo: float, hi: float, target: float, iters: int = 60) -> float:
        for _ in range(iters):
            mid = 0.5 * (lo + hi)
            if fn(mid) < target:
                lo = mid
            else:
                hi = mid
        return hi

    def depth_for_area(self, ya: float, area: float, mode: str) -> float | None:
        return self._memo(("d", round(ya, 9), round(area, 9), mode), lambda: self._depth_for_area(ya, area, mode))

    def _depth_for_area(self, ya: float, area: float, mode: str) -> float | None:
        """Depth d of a slab starting at ya that holds area.

        mode "polygonal": the slab follows the boundaries (strip area).
        mode "rectangle": the slab is the widest rectangle fitting the whole slab (width x depth);
                          the smallest such depth is returned.
        None when the polygon cannot hold it behind ya.
        """
        room = self.ymax - ya
        if room <= _TOL or area <= 0:
            return 0.0 if area <= 0 else None
        if mode == "polygonal":
            if self.strip_area(ya, self.ymax) < area - 1e-6:
                return None
            return self._bisect(lambda d: self.strip_area(ya, ya + d), 0.0, room, area)

        def held(d: float) -> float:
            lo, hi = self.slab_interval(ya, ya + d)
            return d * max(0.0, hi - lo)

        steps = 96
        prev = 0.0
        for i in range(1, steps + 1):
            d = room * i / steps
            if held(d) >= area - 1e-9:
                return self._bisect(held, prev, d, area)
            prev = d
        return None

    def x_for_area(self, ya: float, yb: float, area: float, c0: float = -INF, c1: float = INF) -> float:
        """x such that the strip [ya, yb] x [c0, x] holds area."""
        key = ("x", round(ya, 9), round(yb, 9), round(area, 9), round(c0, 9) if math.isfinite(c0) else c0,
               round(c1, 9) if math.isfinite(c1) else c1)
        return self._memo(key, lambda: self._x_for_area(ya, yb, area, c0, c1))

    def _x_for_area(self, ya: float, yb: float, area: float, c0: float, c1: float) -> float:
        lo = max(c0, min(min(s.xl0, s.xl1) for s, _, _ in self._pieces(ya, yb)))
        hi = min(c1, max(max(s.xr0, s.xr1) for s, _, _ in self._pieces(ya, yb)))
        return self._bisect(lambda x: self.strip_area(ya, yb, c0, x), lo, hi, area)

    def y_for_area(self, ya: float, yb: float, area: float, c0: float = -INF, c1: float = INF) -> float:
        """y in [ya, yb] such that the strip [ya, y] x [c0, c1] holds area."""
        key = ("y", round(ya, 9), round(yb, 9), round(area, 9), round(c0, 9) if math.isfinite(c0) else c0,
               round(c1, 9) if math.isfinite(c1) else c1)
        return self._memo(key, lambda: self._y_for_area(ya, yb, area, c0, c1))

    def _y_for_area(self, ya: float, yb: float, area: float, c0: float, c1: float) -> float:
        return self._bisect(lambda y: self.strip_area(ya, y, c0, c1), ya, yb, area)

    # ------------------------------------------------------------------ stepped capacity

    def best_steps(self, ya: float, k: int, grid: int = 48) -> tuple[float, list[tuple[float, float, float, float]]]:
        """Largest union of k stacked rectangles (each the widest fitting its slab) from ya to ymax.

        Coarse grid over the break positions refined around the best cell; returns (area, rects).
        """
        span = self.ymax - ya
        if span <= _TOL or k < 1:
            return 0.0, []

        def rects_for(breaks: list[float]):
            ys = [ya, *breaks, self.ymax]
            out = []
            for y0, y1 in zip(ys, ys[1:]):
                lo, hi = self.slab_interval(y0, y1)
                if hi > lo and y1 > y0:
                    out.append((lo, y0, hi, y1))
            return out

        def area_of(breaks: list[float]) -> float:
            return sum((r[2] - r[0]) * (r[3] - r[1]) for r in rects_for(breaks))

        best_breaks: list[float] = []
        best = area_of(best_breaks)
        if k >= 2:
            import itertools

            ticks = [ya + span * i / grid for i in range(1, grid)]
            for combo in itertools.combinations(ticks, k - 1):
                a = area_of(list(combo))
                if a > best:
                    best, best_breaks = a, list(combo)
            step = span / grid
            for _ in range(30):
                improved = False
                for i in range(len(best_breaks)):
                    for delta in (-step, step):
                        trial = list(best_breaks)
                        trial[i] = min(max(trial[i] + delta, ya), self.ymax)
                        trial.sort()
                        a = area_of(trial)
                        if a > best + 1e-9:
                            best, best_breaks, improved = a, trial, True
                if not improved:
                    step /= 2.0
                    if step < 1e-3:
                        break
        return best, rects_for(best_breaks)

    def y_for_width(self, width: float, ya: float, yb: float | None = None) -> float | None:
        """Smallest y >= ya where the section is at least width wide (None if never within [ya, yb])."""
        yb = self.ymax if yb is None else yb
        if self.width(ya) >= width - 1e-9:
            return ya
        n = 200
        prev = ya
        for i in range(1, n + 1):
            y = ya + (yb - ya) * i / n
            if self.width(y) >= width - 1e-9:
                return self._bisect(lambda t: self.width(t), prev, y, width)
            prev = y
        return None


def profile_of_largest(geom) -> SectionProfile:
    """Section profile of the largest polygon part of a shapely geometry."""
    from spaceplan.lib_aux.geometry import polygon_parts

    parts = polygon_parts(geom)
    if not parts:
        raise ValueError("empty geometry has no section profile")
    poly = max(parts, key=lambda g: g.area)
    return SectionProfile(list(poly.exterior.coords))


__all__ = ["INF", "SectionProfile", "profile_of_largest"]
