"""Domain-free occupancy grid of a floor for stage S2: rasterized labels, prefix sums, area cuts and contacts.

A floor is rasterized at a fixed cell size in the local frame (x along the front, y away from the street). Each cell
holds a label: 0 outside the floor, 1 free (zonable), >= 2 a fixed object (garage, stair, ...). Rectangles are given
in cell indices as (i0, i1, j0, j1), half-open, i along x and j along y. Free-cell counts of any rectangle come from a
summed-area table, so a cut that gives a band or a column a target area is a binary search, and thousands of
topologies can be realized without building polygons. No rule, catalog or contract knowledge lives here.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import shapely
from shapely.geometry import box
from shapely.geometry.base import BaseGeometry

OUTSIDE, FREE = 0, 1
SIDES = ("low_x", "high_x", "low_y", "high_y")   # facade directions: -x, +x, -y (front), +y (rear)

Rect = tuple[int, int, int, int]                 # (i0, i1, j0, j1), half-open cell indices


@dataclass
class Grid:
    x0: float
    y0: float
    res: float
    labels: np.ndarray                           # (ny, nx) int
    label_ids: dict[str, int]
    free: np.ndarray = field(init=False)
    sat: np.ndarray = field(init=False)          # summed-area table of free cells, (ny + 1, nx + 1)
    isat: np.ndarray = field(init=False)         # summed-area table of cells inside the floor (free or fixed)

    def __post_init__(self) -> None:
        self.free = self.labels == FREE
        self.sat = _summed(self.free)
        self.isat = _summed(self.labels != OUTSIDE)

    @property
    def nx(self) -> int:
        return self.labels.shape[1]

    @property
    def ny(self) -> int:
        return self.labels.shape[0]

    @property
    def cell_area(self) -> float:
        return self.res * self.res

    @property
    def free_cells(self) -> int:
        return int(self.sat[-1, -1])

    def count(self, r: Rect) -> int:
        """Free cells inside a rectangle."""
        return _rect_sum(self.sat, r)

    def inside_count(self, r: Rect) -> int:
        """Cells of the floor (free or fixed) inside a rectangle."""
        return _rect_sum(self.isat, r)

    def profile(self, axis: str, lo: int, hi: int) -> np.ndarray:
        """Free cells per line along `axis` inside the strip lo <= other index < hi: per column (axis 'x') of the
        rows lo..hi, or per row (axis 'y') of the columns lo..hi."""
        s = self.sat
        if axis == "x":
            return np.diff(s[hi, :] - s[lo, :])
        return np.diff(s[:, hi] - s[:, lo])

    def to_box(self, r: Rect) -> BaseGeometry:
        i0, i1, j0, j1 = r
        return box(self.x0 + i0 * self.res, self.y0 + j0 * self.res, self.x0 + i1 * self.res, self.y0 + j1 * self.res)

    def mask_of(self, label: str | int) -> np.ndarray:
        lid = label if isinstance(label, int) else self.label_ids[label]
        return self.labels == lid


def _summed(mask: np.ndarray) -> np.ndarray:
    out = np.zeros((mask.shape[0] + 1, mask.shape[1] + 1), dtype=np.int64)
    out[1:, 1:] = mask.astype(np.int64).cumsum(0).cumsum(1)
    return out


def _rect_sum(s: np.ndarray, r: Rect) -> int:
    i0, i1, j0, j1 = r
    return int(s[j1, i1] - s[j0, i1] - s[j1, i0] + s[j0, i0])


def rasterize(floor: BaseGeometry, fixed: list[tuple[str, BaseGeometry]], res: float, pad: int = 1) -> Grid:
    """Grid of `floor` with the `fixed` objects (first listed wins on overlaps) labelled 2, 3, ... by name; cells
    are classified by their centre. One cell of outside padding surrounds the floor so facades are detectable."""
    minx, miny, maxx, maxy = floor.bounds
    x0, y0 = minx - pad * res, miny - pad * res
    nx = int(np.ceil((maxx - minx) / res)) + 2 * pad
    ny = int(np.ceil((maxy - miny) / res)) + 2 * pad
    xs = x0 + (np.arange(nx) + 0.5) * res
    ys = y0 + (np.arange(ny) + 0.5) * res
    gx, gy = np.meshgrid(xs, ys)
    labels = np.where(shapely.contains_xy(floor, gx, gy), FREE, OUTSIDE).astype(np.int32)
    ids: dict[str, int] = {}
    for k, (name, geom) in enumerate(reversed(fixed)):
        lid = 2 + len(fixed) - 1 - k
        ids[name] = lid
        if geom is None or geom.is_empty:
            continue
        inside = shapely.contains_xy(geom, gx, gy) & (labels != OUTSIDE)
        labels[inside] = lid
    return Grid(x0, y0, res, labels, dict(sorted(ids.items(), key=lambda kv: kv[1])))


def cut_index(cum: np.ndarray, start: int, target: int) -> int:
    """Index k > start such that the cumulative count from `start` up to k reaches `target` (cum = cumsum of a
    profile, cum[k-1] = cells in lines 0..k-1)."""
    base = cum[start - 1] if start > 0 else 0
    k = max(start + 1, min(int(np.searchsorted(cum, base + target, side="left")) + 1, len(cum)))
    if k - 1 > start and abs(cum[k - 2] - base - target) < abs(cum[k - 1] - base - target):
        k -= 1          # the nearer line, not the first one past the target
    return k


def bounding_cells(grid: Grid) -> Rect:
    """Smallest rectangle holding every non-outside cell."""
    inside = grid.labels != OUTSIDE
    cols = np.where(inside.any(0))[0]
    rows = np.where(inside.any(1))[0]
    return int(cols[0]), int(cols[-1]) + 1, int(rows[0]), int(rows[-1]) + 1


def shared_contact(grid: Grid, a: Rect, b: Rect) -> float:
    """Length of wall two rectangles share where both sides are free cells (0 when they do not touch)."""
    ai0, ai1, aj0, aj1 = a
    bi0, bi1, bj0, bj1 = b
    if ai1 == bi0 or bi1 == ai0:
        left, right = (ai1 - 1, bi0) if ai1 == bi0 else (bi1 - 1, ai0)
        lo, hi = max(aj0, bj0), min(aj1, bj1)
        if hi <= lo or left < 0 or right >= grid.nx:
            return 0.0
        both = grid.free[lo:hi, left] & grid.free[lo:hi, right]
        return float(both.sum()) * grid.res
    if aj1 == bj0 or bj1 == aj0:
        low, high = (aj1 - 1, bj0) if aj1 == bj0 else (bj1 - 1, aj0)
        lo, hi = max(ai0, bi0), min(ai1, bi1)
        if hi <= lo or low < 0 or high >= grid.ny:
            return 0.0
        both = grid.free[low, lo:hi] & grid.free[high, lo:hi]
        return float(both.sum()) * grid.res
    return 0.0


def label_contact(grid: Grid, r: Rect, mask: np.ndarray, sides: tuple[str, ...] = SIDES) -> float:
    """Length of wall between the free cells of a rectangle and the cells of `mask` (a boolean grid), counted on
    the given sides of each free cell (low_x: the neighbour at i - 1, ..., high_y: at j + 1)."""
    i0, i1, j0, j1 = r
    lo_i, hi_i, lo_j, hi_j = max(i0 - 1, 0), min(i1 + 1, grid.nx), max(j0 - 1, 0), min(j1 + 1, grid.ny)
    zone = np.zeros((hi_j - lo_j, hi_i - lo_i), dtype=bool)
    zone[j0 - lo_j:j1 - lo_j, i0 - lo_i:i1 - lo_i] = grid.free[j0:j1, i0:i1]
    m = mask[lo_j:hi_j, lo_i:hi_i]
    total = 0
    if "low_x" in sides:
        total += int((zone[:, 1:] & m[:, :-1]).sum())
    if "high_x" in sides:
        total += int((zone[:, :-1] & m[:, 1:]).sum())
    if "low_y" in sides:
        total += int((zone[1:, :] & m[:-1, :]).sum())
    if "high_y" in sides:
        total += int((zone[:-1, :] & m[1:, :]).sum())
    return total * grid.res


def cells_in(points: tuple[np.ndarray, np.ndarray], r: Rect) -> int:
    """How many of the cells (rows, cols) lie inside a rectangle."""
    rows, cols = points
    i0, i1, j0, j1 = r
    return int(((cols >= i0) & (cols < i1) & (rows >= j0) & (rows < j1)).sum())


def cells_of(grid: Grid, geom: BaseGeometry | None) -> tuple[np.ndarray, np.ndarray]:
    """Free cells whose centre lies in `geom` (rows, cols)."""
    if geom is None or geom.is_empty:
        return np.zeros(0, dtype=int), np.zeros(0, dtype=int)
    xs = grid.x0 + (np.arange(grid.nx) + 0.5) * grid.res
    ys = grid.y0 + (np.arange(grid.ny) + 0.5) * grid.res
    gx, gy = np.meshgrid(xs, ys)
    inside = shapely.contains_xy(geom, gx, gy) & grid.free
    return np.nonzero(inside)


__all__ = ["FREE", "OUTSIDE", "SIDES", "Grid", "Rect", "bounding_cells", "cells_in", "cells_of", "cut_index",
           "label_contact", "rasterize", "shared_contact"]
