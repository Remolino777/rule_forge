"""Paths and a bed inside one room on a cell grid (step 6.7a S2.2j). Domain-free: boolean masks of the room, of the
door swings and of the door approaches, sizes in cells; the rules (bed, clearances, path width) come from the caller.

A bed placement is the bed rectangle with its clearance rectangle around it (sides and foot), the head on a wall.
A placement keeps the room passable when the bed stays off every swing and approach and every approach is reached
from every other one through the free cells by a path at least `path` cells wide (the free cells eroded by half the
path width, with distance_transform_edt, stay one connected piece that meets each approach)."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view
from scipy.ndimage import distance_transform_edt, label

HEADS = ("low_x", "high_x", "low_y", "high_y")


@dataclass(frozen=True)
class BedPlace:
    head: str                     # wall the headboard stands on
    bed: tuple[int, int, int, int]       # (i0, i1, j0, j1) in mask coordinates
    clear: tuple[int, int, int, int]     # the bed with its clearances


def _windows(mask: np.ndarray, h: int, w: int) -> np.ndarray:
    """(rows, cols) of the top-left corners where an h x w window is all True."""
    if h <= 0 or w <= 0 or mask.shape[0] < h or mask.shape[1] < w:
        return np.zeros((0, 2), dtype=int)
    win = sliding_window_view(mask, (h, w)).all(axis=(2, 3))
    return np.argwhere(win)


def bed_places(room: np.ndarray, bed_w: int, bed_l: int, side: int, foot: int) -> list[BedPlace]:
    """Every placement of a bed (bed_w across, bed_l from head to foot) whose clearance rectangle (side cells on
    both sides, foot cells at the foot) lies in the room, with the head against a wall (the cells beyond the head
    are outside the room)."""
    ny, nx = room.shape
    out: list[BedPlace] = []
    for head in HEADS:
        across_x = head in ("low_y", "high_y")          # head on a horizontal wall: the bed runs along y
        cw, ch = (bed_w + 2 * side, bed_l + foot) if across_x else (bed_l + foot, bed_w + 2 * side)
        for j, i in _windows(room, ch, cw):
            if head == "low_y":
                bed = (i + side, i + side + bed_w, j, j + bed_l)
                wall = room[j - 1, i + side:i + side + bed_w] if j > 0 else np.zeros(0, dtype=bool)
            elif head == "high_y":
                bed = (i + side, i + side + bed_w, j + ch - bed_l, j + ch)
                wall = room[j + ch, i + side:i + side + bed_w] if j + ch < ny else np.zeros(0, dtype=bool)
            elif head == "low_x":
                bed = (i, i + bed_l, j + side, j + side + bed_w)
                wall = room[j + side:j + side + bed_w, i - 1] if i > 0 else np.zeros(0, dtype=bool)
            else:
                bed = (i + cw - bed_l, i + cw, j + side, j + side + bed_w)
                wall = room[j + side:j + side + bed_w, i + cw] if i + cw < nx else np.zeros(0, dtype=bool)
            if wall.any():
                continue                                 # the head would stand in the room, not on a wall
            out.append(BedPlace(head, bed, (i, i + cw, j, j + ch)))
    return out


def _rect(shape: tuple[int, int], r: tuple[int, int, int, int]) -> np.ndarray:
    m = np.zeros(shape, dtype=bool)
    i0, i1, j0, j1 = r
    m[j0:j1, i0:i1] = True
    return m


def passable(room: np.ndarray, blocked: np.ndarray, approaches: list[np.ndarray], half_path: float) -> bool:
    """Every approach is reached from the others through room cells off `blocked`, along a path at least
    2 x half_path cells wide."""
    if len(approaches) < 2:
        return True
    free = room & ~blocked
    if not free.any():
        return False
    dist = distance_transform_edt(np.pad(free, 1))[1:-1, 1:-1]
    core = free & (dist >= half_path - 1e-9)
    lab, n = label(core)
    if n == 0:
        return False
    common = None
    for a in approaches:
        hit = set(np.unique(lab[a & core]).tolist()) - {0}
        common = hit if common is None else common & hit
        if not common:
            return False
    return True


def bed_fits(room: np.ndarray, swings: np.ndarray, approaches: list[np.ndarray], bed_w: int, bed_l: int,
             side: int, foot: int, half_path: float) -> BedPlace | None:
    """The first bed placement that stays off the swings and the approaches and keeps every approach reached from
    the others around the bed; None when no placement does."""
    keep_off = swings.copy()
    for a in approaches:
        keep_off |= a
    for p in bed_places(room, bed_w, bed_l, side, foot):
        bed = _rect(room.shape, p.bed)
        if (bed & keep_off).any():
            continue
        if passable(room, bed, approaches, half_path):
            return p
    return None


def approach_cells(room: np.ndarray, vertical: bool, k: int, t0: float, t1: float, depth: int) -> np.ndarray:
    """Room cells in front of a doorway on wall line k (cells t0..t1 along it), `depth` cells deep, on the room's
    side of the line."""
    ny, nx = room.shape
    m = np.zeros_like(room)
    a, b = max(int(np.floor(t0 + 1e-9)), 0), int(np.ceil(t1 - 1e-9))
    if vertical:
        m[a:min(b, ny), max(k - depth, 0):min(k + depth, nx)] = True
    else:
        m[max(k - depth, 0):min(k + depth, ny), a:min(b, nx)] = True
    return m & room


__all__ = ["BedPlace", "HEADS", "approach_cells", "bed_fits", "bed_places", "passable"]
