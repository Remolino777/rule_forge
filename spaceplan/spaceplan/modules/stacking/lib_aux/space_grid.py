"""Domain-free helpers of stage S2.1 on a labelled grid: guillotine cuts inside a mask, rectangles, wall runs,
quarter-disc swings and connected parts.

A floor is the grid of stage S2 (cell size `res`, i along x, j along y, half-open rectangles (i0, i1, j0, j1)).
Here every cell carries a node label (>= 0) or a negative code (outside, void, ...). No rule, catalog or contract
knowledge lives here: callers pass target cell counts, minimum lengths in cells and boolean masks.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from itertools import pairwise

import numpy as np

from spaceplan.core.lib_aux.allocation import fit_lengths

Rect = tuple[int, int, int, int]                 # (i0, i1, j0, j1), half-open cell indices


# ------------------------------------------------------------------ masks and rectangles


def mask_bounds(mask: np.ndarray) -> Rect | None:
    """Smallest rectangle holding every True cell (None for an empty mask)."""
    cols = np.where(mask.any(0))[0]
    rows = np.where(mask.any(1))[0]
    if not len(cols):
        return None
    return int(cols[0]), int(cols[-1]) + 1, int(rows[0]), int(rows[-1]) + 1


def rect_mask(shape: tuple[int, int], r: Rect) -> np.ndarray:
    out = np.zeros(shape, dtype=bool)
    i0, i1, j0, j1 = r
    out[j0:j1, i0:i1] = True
    return out


def largest_rect(mask: np.ndarray) -> tuple[int, Rect | None]:
    """Largest axis-aligned rectangle of True cells: (cells, rect). Histogram method, O(rows x cols)."""
    r = mask_bounds(mask)
    if r is None:
        return 0, None
    i0, i1, j0, j1 = r
    sub = mask[j0:j1, i0:i1]
    if sub.all():
        return int(sub.size), r
    best, best_rect = 0, None
    heights = np.zeros(sub.shape[1], dtype=np.int64)
    for row_k, row in enumerate(sub):
        heights = np.where(row, heights + 1, 0)
        stack: list[int] = []
        hs = heights.tolist() + [0]
        for k, h in enumerate(hs):
            while stack and hs[stack[-1]] >= h:
                top = hs[stack.pop()]
                left = stack[-1] + 1 if stack else 0
                area = top * (k - left)
                if area > best:
                    best = area
                    best_rect = (i0 + left, i0 + k, j0 + row_k - top + 1, j0 + row_k + 1)
            stack.append(k)
    return int(best), best_rect


def components(mask: np.ndarray) -> list[np.ndarray]:
    """4-connected parts of a mask, largest first."""
    seen = np.zeros(mask.shape, dtype=bool)
    out = []
    ny, nx = mask.shape
    for j, i in zip(*np.nonzero(mask)):
        if seen[j, i]:
            continue
        part = np.zeros(mask.shape, dtype=bool)
        queue = deque([(j, i)])
        seen[j, i] = True
        while queue:
            y, x = queue.popleft()
            part[y, x] = True
            for yy, xx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
                if 0 <= yy < ny and 0 <= xx < nx and mask[yy, xx] and not seen[yy, xx]:
                    seen[yy, xx] = True
                    queue.append((yy, xx))
        out.append(part)
    return sorted(out, key=lambda m: -int(m.sum()))


def fill_unassigned(labels: np.ndarray, free: np.ndarray, unassigned: int = -2) -> np.ndarray:
    """Give every free cell still `unassigned` the label of a 4-neighbour, repeatedly (thin slivers)."""
    out = labels.copy()
    for _ in range(max(out.shape)):
        todo = free & (out == unassigned)
        if not todo.any():
            break
        for dj, di in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            src = np.roll(out, (dj, di), axis=(0, 1))
            take = todo & (src >= 0)
            out[take] = src[take]
            todo &= ~take
    return out


# ------------------------------------------------------------------ guillotine cuts inside a mask


def _cuts(counts: np.ndarray, targets: list[float]) -> list[int]:
    """Line indices that split a profile of free cells (per line) into consecutive parts of the target counts."""
    cum = np.cumsum(counts)
    total = float(cum[-1]) if len(cum) else 0.0
    want = np.cumsum(np.asarray(targets, dtype=float))
    want = want / (want[-1] or 1.0) * total
    edges = [0]
    for w in want[:-1]:
        k = int(np.searchsorted(cum, w, side="left")) + 1
        if k > 1 and abs(cum[k - 2] - w) <= abs(cum[min(k - 1, len(cum) - 1)] - w):
            k -= 1
        edges.append(max(edges[-1], min(k, len(counts))))
    edges.append(len(counts))
    return edges


def _fit(edges: list[int], mins: list[int]) -> list[int] | None:
    """Move the cut lines so every part is at least its minimum length (None when they cannot all fit)."""
    spans = [float(b - a) for a, b in pairwise(edges)]
    if all(s >= m for s, m in zip(spans, mins)):
        return edges
    fitted = fit_lengths(spans, [float(m) for m in mins])
    if fitted is None:
        return None
    out = [edges[0]]
    acc = float(edges[0])
    for s in fitted:
        acc += s
        out.append(round(acc))
    out[-1] = edges[-1]
    if any(b - a < m for a, b, m in zip(out, out[1:], mins)):
        return None
    return out


@dataclass(frozen=True)
class Guillotine:
    """Columns along one axis of a rectangle, each a stack of parts along the other axis. A part is a name, or a
    tuple of names that share its slot side by side (cut along the column's axis): three levels of cuts."""

    along_x: bool                                # columns side by side along x (each spans y)
    columns: tuple[tuple, ...]


def _names(part) -> tuple[str, ...]:
    return part if isinstance(part, tuple) else (part,)


def _snap_edges(edges: list[int], mins: list[int], lines, offset: int, reach: int) -> list[int]:
    """Interior edges moved to the nearest of `lines` (absolute indices; edges are relative to `offset`) within
    `reach` cells, keeping every part at least its minimum (S2.2f: walls over the walls below)."""
    if not lines or reach <= 0 or len(edges) < 3:
        return edges
    out = list(edges)
    for k in range(1, len(out) - 1):
        best = None
        for c in lines:
            e = c - offset
            d = abs(e - out[k])
            if d > reach or e - out[k - 1] < mins[k - 1] or out[k + 1] - e < mins[k]:
                continue
            if best is None or d < best[0]:
                best = (d, e)
        if best is not None:
            out[k] = best[1]
    return out


def realize(mask: np.ndarray, box: Rect, g: Guillotine, targets: dict[str, float],
            min_cells: dict[str, int], snap: tuple | None = None) -> dict[str, Rect] | None:
    """Rectangles of a guillotine arrangement inside `box`, cut where the free cells of `mask` match the targets;
    every part keeps at least its minimum length (cells) in both directions when the box allows it. `snap`
    (S2.2f): (x lines, y lines, reach) the cuts move to when near, keeping the minimums."""
    i0, i1, j0, j1 = box
    sub = mask[j0:j1, i0:i1]
    main_counts = sub.sum(0) if g.along_x else sub.sum(1)
    col_targets = [sum(targets[n] for part in col for n in _names(part)) for col in g.columns]
    col_mins = []
    for col in g.columns:                        # a side-by-side part needs the sum of its members' sides
        col_mins.append(max(sum(min_cells[n] for n in _names(part)) for part in col))
    edges = _fit(_cuts(main_counts, col_targets), col_mins)
    if edges is None:
        return None
    if snap is not None:
        xs, ys, reach = snap
        edges = _snap_edges(edges, col_mins, xs if g.along_x else ys, i0 if g.along_x else j0, reach)
    out: dict[str, Rect] = {}
    for col, a, b in zip(g.columns, edges, edges[1:]):
        part_mask = sub[:, a:b] if g.along_x else sub[a:b, :]
        cross_counts = part_mask.sum(1) if g.along_x else part_mask.sum(0)
        stack = _cuts(cross_counts, [sum(targets[n] for n in _names(p)) for p in col])
        stack_mins = [max(min_cells[n] for n in _names(p)) for p in col]
        stack = _fit(stack, stack_mins)
        if stack is None:
            return None
        if snap is not None:
            stack = _snap_edges(stack, stack_mins, snap[1] if g.along_x else snap[0], j0 if g.along_x else i0,
                                snap[2])
        for part, c, d in zip(col, stack, stack[1:]):
            names = _names(part)
            if len(names) == 1:
                cuts = [a, b]
            else:                                # side by side inside the slot, along the column's axis
                slot = sub[c:d, a:b] if g.along_x else sub[a:b, c:d]
                counts = slot.sum(0) if g.along_x else slot.sum(1)
                cuts = _fit(_cuts(counts, [targets[n] for n in names]), [min_cells[n] for n in names])
                if cuts is None:
                    return None
                cuts = [a + x for x in cuts]
            for n, e, f in zip(names, cuts, cuts[1:]):
                out[n] = (i0 + e, i0 + f, j0 + c, j0 + d) if g.along_x else (i0 + c, i0 + d, j0 + e, j0 + f)
    return out


# ------------------------------------------------------------------ walls between labels


@dataclass(frozen=True)
class WallRun:
    """A straight run of wall between two labels: on the vertical line x = k (vertical=True) or the horizontal
    line y = k, from t0 to t1 (cells along the line). `low` is the label on the low side (i < k or j < k)."""

    low: int
    high: int
    vertical: bool
    k: int
    t0: int
    t1: int

    @property
    def cells(self) -> int:
        return self.t1 - self.t0


def wall_runs(labels: np.ndarray) -> dict[tuple[int, int], list[WallRun]]:
    """Every straight run of wall between two different non-negative labels, keyed by the sorted label pair."""
    out: dict[tuple[int, int], list[WallRun]] = {}

    def collect(a: np.ndarray, b: np.ndarray, vertical: bool) -> None:
        diff = (a != b) & (a >= 0) & (b >= 0)
        if vertical:                                   # a = labels[:, :-1] (low x), b = labels[:, 1:]
            js, is_ = np.nonzero(diff)
            keys = sorted(zip(is_.tolist(), js.tolist()))          # by line k = i + 1, then along y
            seq = [(i + 1, j, int(a[j, i]), int(b[j, i])) for i, j in keys]
        else:                                          # a = labels[:-1, :] (low y), b = labels[1:, :]
            js, is_ = np.nonzero(diff)
            keys = sorted(zip(js.tolist(), is_.tolist()))
            seq = [(j + 1, i, int(a[j, i]), int(b[j, i])) for j, i in keys]
        run = None
        for k, t, lo, hi in seq:
            if run and run[0] == k and run[2] == t and run[3] == lo and run[4] == hi:
                run[2] = t + 1
                continue
            if run:
                _add(out, run, vertical)
            run = [k, t, t + 1, lo, hi]
        if run:
            _add(out, run, vertical)

    collect(labels[:, :-1], labels[:, 1:], True)
    collect(labels[:-1, :], labels[1:, :], False)
    return out


def _add(out, run, vertical: bool) -> None:
    k, t0, t1, lo, hi = run
    key = (min(lo, hi), max(lo, hi))
    out.setdefault(key, []).append(WallRun(lo, hi, vertical, k, t0, t1))


def contact_cells(labels: np.ndarray, a: int, codes: tuple[int, ...]) -> int:
    """Cell sides between label `a` and any of the codes (e.g. the outside), 4-neighbour."""
    m = labels == a
    o = np.isin(labels, codes)
    return int((m[:, 1:] & o[:, :-1]).sum() + (m[:, :-1] & o[:, 1:]).sum()
               + (m[1:, :] & o[:-1, :]).sum() + (m[:-1, :] & o[1:, :]).sum())


def longest_contact(labels: np.ndarray, a: int, codes: tuple[int, ...]) -> int:
    """Longest straight run (cells) of wall between label `a` and the codes."""
    m = labels == a
    o = np.isin(labels, codes)
    best = 0
    for side in (m[:, 1:] & o[:, :-1], m[:, :-1] & o[:, 1:]):          # vertical walls: runs along y per line
        best = max(best, _longest_true(side.T))
    for side in (m[1:, :] & o[:-1, :], m[:-1, :] & o[1:, :]):          # horizontal walls: runs along x per line
        best = max(best, _longest_true(side))
    return best


def _longest_true(rows: np.ndarray) -> int:
    """Longest run of True along the last axis of a 2-D array (vectorized)."""
    if rows.size == 0 or not rows.any():
        return 0
    padded = np.zeros((rows.shape[0], rows.shape[1] + 2), dtype=np.int8)
    padded[:, 1:-1] = rows
    d = np.diff(padded.ravel())
    starts, ends = np.nonzero(d == 1)[0], np.nonzero(d == -1)[0]
    return int((ends - starts).max())


def exterior_run(mask: np.ndarray, ext: tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]) -> int:
    """Longest straight run (cells) of exterior wall of a mask, given per-cell flags of an outside neighbour at
    -x, +x, -y, +y (arrays of the mask's shape)."""
    lo_x, hi_x, lo_y, hi_y = ext
    best = 0
    for side in (mask & lo_x, mask & hi_x):              # walls on vertical lines: runs along y
        best = max(best, _longest_true(side.T))
    for side in (mask & lo_y, mask & hi_y):              # walls on horizontal lines: runs along x
        best = max(best, _longest_true(side))
    return best


# ------------------------------------------------------------------ swings


def swing_cells(shape: tuple[int, int], run: WallRun, into_high: bool, hinge_t: float, leaf: float,
                toward_plus: bool) -> np.ndarray:
    """Cells whose centre lies in the quarter disc a leaf sweeps: hinge on the wall line at `hinge_t` (cells along
    the line), leaf length `leaf` (cells), opening toward the high side of the line (into_high) or the low side,
    the leaf lying along +t (toward_plus) or -t when closed."""
    ny, nx = shape
    out = np.zeros(shape, dtype=bool)
    r = leaf
    k = run.k
    if run.vertical:
        i_lo, i_hi = (k, int(np.ceil(k + r))) if into_high else (int(np.floor(k - r)), k)
        t_lo, t_hi = (int(np.floor(hinge_t)), int(np.ceil(hinge_t + r))) if toward_plus else \
            (int(np.floor(hinge_t - r)), int(np.ceil(hinge_t)))
        i_lo, i_hi, t_lo, t_hi = max(i_lo, 0), min(i_hi, nx), max(t_lo, 0), min(t_hi, ny)
        if i_hi <= i_lo or t_hi <= t_lo:
            return out
        ii, tt = np.meshgrid(np.arange(i_lo, i_hi) + 0.5, np.arange(t_lo, t_hi) + 0.5)
        inside = (ii - k) ** 2 + (tt - hinge_t) ** 2 <= r * r
        out[t_lo:t_hi, i_lo:i_hi] = inside
    else:
        j_lo, j_hi = (k, int(np.ceil(k + r))) if into_high else (int(np.floor(k - r)), k)
        t_lo, t_hi = (int(np.floor(hinge_t)), int(np.ceil(hinge_t + r))) if toward_plus else \
            (int(np.floor(hinge_t - r)), int(np.ceil(hinge_t)))
        j_lo, j_hi, t_lo, t_hi = max(j_lo, 0), min(j_hi, ny), max(t_lo, 0), min(t_hi, nx)
        if j_hi <= j_lo or t_hi <= t_lo:
            return out
        tt, jj = np.meshgrid(np.arange(t_lo, t_hi) + 0.5, np.arange(j_lo, j_hi) + 0.5)
        inside = (jj - k) ** 2 + (tt - hinge_t) ** 2 <= r * r
        out[j_lo:j_hi, t_lo:t_hi] = inside
    return out


def mask_polygon(mask: np.ndarray, grid):
    """Polygon of the cells of a mask on a grid with x0, y0, res (row runs merged)."""
    from shapely.geometry import box as _box
    from shapely.ops import unary_union

    boxes = []
    for j in np.nonzero(mask.any(1))[0]:
        row = np.concatenate(([0], mask[j].astype(np.int8), [0]))
        d = np.diff(row)
        for a, b in zip(np.nonzero(d == 1)[0], np.nonzero(d == -1)[0]):
            boxes.append(_box(grid.x0 + a * grid.res, grid.y0 + j * grid.res,
                              grid.x0 + b * grid.res, grid.y0 + (j + 1) * grid.res))
    return unary_union(boxes).simplify(0)


# ------------------------------------------------------------------ fit and exposure (step S2.2b)


def fits_in_mask(mask: np.ndarray, a: int, b: int) -> bool:
    """True when an a x b block of cells (either orientation) lies wholly inside the mask."""
    ny, nx = mask.shape
    if a <= 0 or b <= 0:
        return True
    integral = np.pad(mask.astype(np.int32).cumsum(0).cumsum(1), ((1, 0), (1, 0)))
    for kx, ky in ((a, b), (b, a)):
        if kx > nx or ky > ny:
            continue
        s = integral[ky:, kx:] - integral[:-ky, kx:] - integral[ky:, :-kx] + integral[:-ky, :-kx]
        if (s == kx * ky).any():
            return True
    return False


def exterior_cells(mask: np.ndarray, ext: tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]) -> int:
    """Cell edges of the mask on an outside neighbour (all four sides): its exposed wall in cells."""
    return int(sum((mask & e).sum() for e in ext))


def exposed_sides(mask: np.ndarray, ext: tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]) -> int:
    """How many of the four sides (-x, +x, -y, +y) of the mask touch the outside (2 or more: cross ventilation)."""
    return sum(1 for e in ext if (mask & e).any())


def shared_edge(a: np.ndarray, b: np.ndarray) -> tuple[int, bool]:
    """(cells of the longest common wall between masks a and b, True when that wall runs along y)."""
    along_y = int((a[:, 1:] & b[:, :-1]).sum() + (a[:, :-1] & b[:, 1:]).sum())     # neighbours across x
    along_x = int((a[1:, :] & b[:-1, :]).sum() + (a[:-1, :] & b[1:, :]).sum())     # neighbours across y
    return (along_y, True) if along_y >= along_x else (along_x, False)


__all__ = [
    "Guillotine",
    "Rect",
    "WallRun",
    "components",
    "contact_cells",
    "exposed_sides",
    "exterior_cells",
    "exterior_run",
    "fill_unassigned",
    "fits_in_mask",
    "largest_rect",
    "longest_contact",
    "mask_bounds",
    "mask_polygon",
    "realize",
    "rect_mask",
    "shared_edge",
    "swing_cells",
    "wall_runs",
]
