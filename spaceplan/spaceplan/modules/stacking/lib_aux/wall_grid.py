"""Walls of a rectangle on a cell grid (V6.8 k4). Domain-free: boolean masks, integer label grids and
(i0, i1, j0, j1) rectangles (x columns i0:i1, y rows j0:j1).

  * SIDES: the four sides of a rectangle (-x, +x, -y, +y);
  * side_length: cells along a side;
  * side_strip: the strip of a given depth inside a rectangle along one side (the whole side);
  * beyond: the cells just outside a side (the other face of that wall), clipped to the grid, and how many fall off;
  * strip_side: the side of a rectangle that a full-width strip of it lies on (None when the part is no such strip);
  * rest_rect: the rectangle left when a side strip is cut off."""

from __future__ import annotations

import numpy as np

Rect = tuple[int, int, int, int]
X_LOW, X_HIGH, Y_LOW, Y_HIGH = "x_low", "x_high", "y_low", "y_high"
SIDES = (X_LOW, X_HIGH, Y_LOW, Y_HIGH)


def side_length(r: Rect, side: str) -> int:
    """Cells along a side: a side on an x line runs along y."""
    return (r[3] - r[2]) if side in (X_LOW, X_HIGH) else (r[1] - r[0])


def side_depth(r: Rect, side: str) -> int:
    """Cells across the rectangle, perpendicular to a side."""
    return (r[1] - r[0]) if side in (X_LOW, X_HIGH) else (r[3] - r[2])


def side_strip(r: Rect, side: str, depth: int) -> Rect:
    """The strip `depth` cells deep inside `r` along the whole of `side`."""
    i0, i1, j0, j1 = r
    if side == X_LOW:
        return i0, min(i0 + depth, i1), j0, j1
    if side == X_HIGH:
        return max(i1 - depth, i0), i1, j0, j1
    if side == Y_LOW:
        return i0, i1, j0, min(j0 + depth, j1)
    return i0, i1, max(j1 - depth, j0), j1


def rest_rect(r: Rect, side: str, depth: int) -> Rect:
    """The rectangle of `r` left when the strip along `side` is cut off."""
    i0, i1, j0, j1 = r
    if side == X_LOW:
        return i0 + depth, i1, j0, j1
    if side == X_HIGH:
        return i0, i1 - depth, j0, j1
    if side == Y_LOW:
        return i0, i1, j0 + depth, j1
    return i0, i1, j0, j1 - depth


def beyond(labels: np.ndarray, r: Rect, side: str) -> tuple[np.ndarray, int]:
    """(labels of the cells just outside `side` that lie on the grid, how many of them fall off the grid)."""
    i0, i1, j0, j1 = r
    ny, nx = labels.shape
    if side == X_LOW:
        return (labels[j0:j1, i0 - 1] if i0 > 0 else labels[j0:j0, 0]), (0 if i0 > 0 else j1 - j0)
    if side == X_HIGH:
        return (labels[j0:j1, i1] if i1 < nx else labels[j0:j0, 0]), (0 if i1 < nx else j1 - j0)
    if side == Y_LOW:
        return (labels[j0 - 1, i0:i1] if j0 > 0 else labels[0, i0:i0]), (0 if j0 > 0 else i1 - i0)
    return (labels[j1, i0:i1] if j1 < ny else labels[0, i0:i0]), (0 if j1 < ny else i1 - i0)


def strip_side(union: Rect, part: Rect) -> str | None:
    """The side of `union` that `part` covers whole as a strip (its full length, from that side inward); None when
    the part is no such strip."""
    i0, i1, j0, j1 = union
    p0, p1, q0, q1 = part
    if (q0, q1) == (j0, j1) and p0 == i0 and p1 < i1:
        return X_LOW
    if (q0, q1) == (j0, j1) and p1 == i1 and p0 > i0:
        return X_HIGH
    if (p0, p1) == (i0, i1) and q0 == j0 and q1 < j1:
        return Y_LOW
    if (p0, p1) == (i0, i1) and q1 == j1 and q0 > j0:
        return Y_HIGH
    return None


__all__ = ["SIDES", "X_HIGH", "X_LOW", "Y_HIGH", "Y_LOW", "beyond", "rest_rect", "side_depth", "side_length",
           "side_strip", "strip_side"]
