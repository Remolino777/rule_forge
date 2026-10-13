"""Geometry of a hall on a label grid (step 6.7a S2.2h): rectangles of a mask, positions along a rectangle, the labels
beside it and the cells of a wall run. Domain-free: cells and integer labels; rectangles are (i0, i1, j0, j1)."""

from __future__ import annotations

import numpy as np

Rect = tuple[int, int, int, int]


def rectangles(mask: np.ndarray) -> list[Rect]:
    """The mask cut into rectangles, largest first (greedy: the largest rectangle of what is left, again)."""
    left = mask.copy()
    out: list[Rect] = []
    while left.any():
        r = _largest(left)
        if r is None:
            break
        i0, i1, j0, j1 = r
        left[j0:j1, i0:i1] = False
        out.append(r)
    return out


def _largest(mask: np.ndarray) -> Rect | None:
    """Largest all-true rectangle of a mask (histogram method)."""
    ny, nx = mask.shape
    heights = np.zeros(nx, dtype=int)
    best, best_area = None, 0
    for j in range(ny):
        heights = np.where(mask[j], heights + 1, 0)
        stack: list[int] = []
        for i in range(nx + 1):
            h = heights[i] if i < nx else 0
            while stack and heights[stack[-1]] >= h:
                top = stack.pop()
                left = stack[-1] + 1 if stack else 0
                area = int(heights[top]) * (i - left)
                if area > best_area:
                    best_area = area
                    best = (left, i, j + 1 - int(heights[top]), j + 1)
            if i < nx:
                stack.append(i)
    return best


def along(r: Rect) -> str:
    """'x' when the rectangle is at least as wide as it is deep (its long axis)."""
    return "x" if (r[1] - r[0]) >= (r[3] - r[2]) else "y"


def span(r: Rect, axis: str) -> tuple[int, int]:
    return (r[0], r[1]) if axis == "x" else (r[2], r[3])


def sub(r: Rect, axis: str, a: int, b: int) -> Rect:
    """The part of r between positions a and b along `axis`."""
    return (a, b, r[2], r[3]) if axis == "x" else (r[0], r[1], a, b)


def cells(shape: tuple[int, int], r: Rect) -> np.ndarray:
    m = np.zeros(shape, dtype=bool)
    i0, i1, j0, j1 = r
    m[j0:j1, i0:i1] = True
    return m


def positions_hit(r: Rect, axis: str, hit: np.ndarray) -> np.ndarray:
    """Positions along the rectangle's axis where `hit` has a cell inside the rectangle."""
    i0, i1, j0, j1 = r
    block = hit[j0:j1, i0:i1]
    return np.nonzero(block.any(axis=0) if axis == "x" else block.any(axis=1))[0] + (i0 if axis == "x" else j0)


def sides(labels: np.ndarray, r: Rect, axis: str) -> tuple[np.ndarray, np.ndarray]:
    """Labels just outside the two long sides of r, one per position along the axis (a value of `labels` dtype; the
    grid edge reads as the minimum integer)."""
    i0, i1, j0, j1 = r
    ny, nx = labels.shape
    edge = np.iinfo(labels.dtype).min
    if axis == "x":
        lo = labels[j0 - 1, i0:i1] if j0 > 0 else np.full(i1 - i0, edge, labels.dtype)
        hi = labels[j1, i0:i1] if j1 < ny else np.full(i1 - i0, edge, labels.dtype)
    else:
        lo = labels[j0:j1, i0 - 1] if i0 > 0 else np.full(j1 - j0, edge, labels.dtype)
        hi = labels[j0:j1, i1] if i1 < nx else np.full(j1 - j0, edge, labels.dtype)
    return lo, hi


def ring(labels: np.ndarray, r: Rect) -> np.ndarray:
    """Labels of the cells around the rectangle (4-neighbours), without the corners."""
    i0, i1, j0, j1 = r
    ny, nx = labels.shape
    parts = []
    if j0 > 0:
        parts.append(labels[j0 - 1, i0:i1])
    if j1 < ny:
        parts.append(labels[j1, i0:i1])
    if i0 > 0:
        parts.append(labels[j0:j1, i0 - 1])
    if i1 < nx:
        parts.append(labels[j0:j1, i1])
    return np.concatenate(parts) if parts else np.zeros(0, dtype=labels.dtype)


def run_cells(shape: tuple[int, int], vertical: bool, k: int, t0: float, t1: float, high: bool) -> np.ndarray:
    """Cells beside a stretch t0..t1 of wall line k, on its high side (column k / row k) or low side (k - 1)."""
    m = np.zeros(shape, dtype=bool)
    ny, nx = shape
    a, b = max(int(np.floor(t0)), 0), int(np.ceil(t1))
    line = k if high else k - 1
    if vertical and 0 <= line < nx:
        m[a:min(b, ny), line] = True
    elif not vertical and 0 <= line < ny:
        m[line, a:min(b, nx)] = True
    return m


__all__ = ["Rect", "along", "cells", "positions_hit", "rectangles", "ring", "run_cells", "sides", "span", "sub"]
