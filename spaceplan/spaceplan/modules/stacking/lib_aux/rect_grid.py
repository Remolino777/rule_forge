"""Rectangles of a cell mask (V6.8 k3). Domain-free: boolean masks and (i0, i1, j0, j1) rectangles.

  * is_rect: a mask that is exactly one full rectangle;
  * candidate_rects: the rectangles a region could keep (its largest, and the largest on each side of every line
    where its outline steps), largest first;
  * corner_lines: the x and y lines inside a box where a region's outline steps (the lines of its inner corners);
  * rect_pieces: the part of a region outside a rectangle cut into rectangles (connected parts, greedy);
  * split_lines / merge_snap: those lines as guillotine snap lines."""

from __future__ import annotations

import numpy as np
from scipy.ndimage import label

from spaceplan.modules.stacking.lib_aux.hall_geometry import rectangles
from spaceplan.modules.stacking.lib_aux.space_grid import largest_rect, mask_bounds

Rect = tuple[int, int, int, int]


def is_rect(mask: np.ndarray) -> bool:
    """True when the True cells of `mask` form one full rectangle (an empty mask is no rectangle)."""
    b = mask_bounds(mask)
    return b is not None and int(mask.sum()) == (b[1] - b[0]) * (b[3] - b[2])


def rect_mask(shape: tuple[int, int], r: Rect) -> np.ndarray:
    m = np.zeros(shape, dtype=bool)
    m[r[2]:r[3], r[0]:r[1]] = True
    return m


def corner_lines(mask: np.ndarray, box: Rect | None = None) -> tuple[tuple[int, ...], tuple[int, ...]]:
    """(x lines, y lines), absolute indices strictly inside the box, where the region's outline steps: a column
    (row) whose cells differ from the previous column's (row's)."""
    b = box if box is not None else mask_bounds(mask)
    if b is None:
        return (), ()
    i0, i1, j0, j1 = b
    sub = mask[j0:j1, i0:i1]
    xs = tuple(i0 + k for k in range(1, sub.shape[1]) if (sub[:, k] != sub[:, k - 1]).any())
    ys = tuple(j0 + k for k in range(1, sub.shape[0]) if (sub[k, :] != sub[k - 1, :]).any())
    return xs, ys


def split_lines(mask: np.ndarray, box: Rect, reach: int):
    """(x lines, y lines, reach) of the inner corners of a region that is no rectangle, as cut lines a guillotine
    snaps to; None for a rectangle, no reach or no corner."""
    if reach <= 0 or is_rect(mask):
        return None
    xs, ys = corner_lines(mask, box)
    if not xs and not ys:
        return None
    return xs, ys, reach


def merge_snap(a, b):
    """Two snap tuples (x lines, y lines, reach) as one: both sets of lines, the larger reach."""
    if a is None:
        return b
    if b is None:
        return a
    return tuple(sorted(set(a[0]) | set(b[0]))), tuple(sorted(set(a[1]) | set(b[1]))), max(a[2], b[2])


def candidate_rects(mask: np.ndarray, limit: int = 8) -> list[Rect]:
    """Rectangles the region could keep, largest first and without repeats: its largest rectangle and, for every
    line where its outline steps, the largest rectangle on each side of the line."""
    out: dict[Rect, int] = {}
    n, r = largest_rect(mask)
    if r is not None:
        out[r] = n
    xs, ys = corner_lines(mask)
    for lines, vertical in ((xs, True), (ys, False)):
        for c in lines:
            for side in (0, 1):
                part = mask.copy()
                if vertical:
                    if side == 0:
                        part[:, c:] = False
                    else:
                        part[:, :c] = False
                elif side == 0:
                    part[c:, :] = False
                else:
                    part[:c, :] = False
                n, r = largest_rect(part)
                if r is not None and r not in out:
                    out[r] = n
    return [r for r, _ in sorted(out.items(), key=lambda kv: (-kv[1], kv[0]))][:limit]


def rect_pieces(mask: np.ndarray, keep: Rect) -> list[np.ndarray]:
    """The part of `mask` outside the rectangle `keep`, as rectangles: each connected part cut greedily (largest
    rectangle of what is left first)."""
    rest = mask & ~rect_mask(mask.shape, keep)
    lab, n = label(rest)
    out = []
    for k in range(1, n + 1):
        comp = lab == k
        for r in rectangles(comp):
            out.append(rect_mask(mask.shape, r) & comp)
    return out


__all__ = ["candidate_rects", "corner_lines", "is_rect", "merge_snap", "rect_mask", "rect_pieces", "split_lines"]
