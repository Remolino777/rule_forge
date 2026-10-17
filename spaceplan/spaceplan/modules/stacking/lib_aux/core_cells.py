"""Cell helpers of the stair core (step V6.8 k1b): which labels a mask lies on, which labels touch it, and the
bounding cells of a block. Pure numpy on label grids (rows = y, cols = x); no design values."""

from __future__ import annotations

import numpy as np


def labels_on(labels: np.ndarray, mask: np.ndarray) -> set[int]:
    """Non-negative labels under the cells of `mask`."""
    if mask is None or not mask.any():
        return set()
    vals = labels[mask]
    return {int(v) for v in np.unique(vals) if v >= 0}


def ring(mask: np.ndarray) -> np.ndarray:
    """Cells 4-adjacent to `mask` and not in it."""
    out = np.zeros_like(mask, dtype=bool)
    out[1:, :] |= mask[:-1, :]
    out[:-1, :] |= mask[1:, :]
    out[:, 1:] |= mask[:, :-1]
    out[:, :-1] |= mask[:, 1:]
    return out & ~mask


def labels_touching(labels: np.ndarray, mask: np.ndarray) -> set[int]:
    """Non-negative labels of the cells 4-adjacent to `mask` (outside it)."""
    if mask is None or not mask.any():
        return set()
    return labels_on(labels, ring(mask))


def rect_mask(shape: tuple[int, int], rect: tuple[int, int, int, int]) -> np.ndarray:
    """Mask of a grid rectangle (i0, i1, j0, j1): columns i0..i1, rows j0..j1."""
    i0, i1, j0, j1 = rect
    m = np.zeros(shape, dtype=bool)
    m[j0:j1, i0:i1] = True
    return m


def rects_touching(shape: tuple[int, int], rects, mask: np.ndarray) -> int:
    """How many rectangles hold or border the cells of `mask` (a zone unit the stair touches)."""
    if mask is None or not mask.any():
        return 0
    near = mask | ring(mask)
    return sum(1 for r in rects if (rect_mask(shape, r) & near).any())


def block_bounds(*masks) -> tuple[int, int, int, int] | None:
    """Bounding cells (i0, i1, j0, j1) of the union of the masks (None when all are empty)."""
    ms = [m for m in masks if m is not None and m.any()]
    if not ms:
        return None
    u = np.logical_or.reduce(ms)
    rows, cols = np.nonzero(u)
    return int(cols.min()), int(cols.max()) + 1, int(rows.min()), int(rows.max()) + 1


__all__ = ["block_bounds", "labels_on", "labels_touching", "rect_mask", "rects_touching", "ring"]
