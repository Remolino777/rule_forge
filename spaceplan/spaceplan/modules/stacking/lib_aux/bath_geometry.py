"""Bands of fixtures in a rectangular room on a cell grid (step 6.7a S2.2j). Domain-free: a mask, depths in cells.

The long axis of the room's bounding box runs from one short end to the other; a band is the room's cells within a
depth of an end (or between two depths), across the whole short side."""

from __future__ import annotations

import numpy as np

from spaceplan.modules.stacking.lib_aux.space_grid import mask_bounds


def long_axis(mask: np.ndarray) -> str | None:
    """'x' when the bounding box is at least as wide as it is deep, 'y' otherwise; None for an empty mask."""
    b = mask_bounds(mask)
    if b is None:
        return None
    return "x" if (b[1] - b[0]) >= (b[3] - b[2]) else "y"


def band(mask: np.ndarray, end: str, d0: int, d1: int) -> np.ndarray:
    """The mask's cells from depth d0 to d1 (cells) measured from one short end ('low' or 'high') of its long axis."""
    b = mask_bounds(mask)
    out = np.zeros_like(mask)
    if b is None or d1 <= d0:
        return out
    i0, i1, j0, j1 = b
    if long_axis(mask) == "x":
        a, z = (i0 + d0, i0 + d1) if end == "low" else (i1 - d1, i1 - d0)
        out[:, max(a, i0):min(z, i1)] = True
    else:
        a, z = (j0 + d0, j0 + d1) if end == "low" else (j1 - d1, j1 - d0)
        out[max(a, j0):min(z, j1), :] = True
    return out & mask


def touches(a: np.ndarray, b: np.ndarray) -> bool:
    """Do two masks share an edge (4-neighbours)?"""
    return bool((a[:, 1:] & b[:, :-1]).any() or (a[:, :-1] & b[:, 1:]).any()
                or (a[1:, :] & b[:-1, :]).any() or (a[:-1, :] & b[1:, :]).any())


def length(mask: np.ndarray) -> int:
    """Cells along the long axis of the mask's bounding box."""
    b = mask_bounds(mask)
    if b is None:
        return 0
    return max(b[1] - b[0], b[3] - b[2])


__all__ = ["band", "length", "long_axis", "touches"]
