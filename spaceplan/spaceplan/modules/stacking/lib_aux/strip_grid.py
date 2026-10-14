"""Thin strips of a labelled grid (step 6.7a S2.2j). Domain-free: integer labels, cell counts and masks.

A strip of a region is the part no w x w square inside the region covers (the region less its morphological
opening by a w x w square)."""

from __future__ import annotations

import numpy as np
from scipy.ndimage import binary_opening, label


def strip_cells(mask: np.ndarray, w: int) -> np.ndarray:
    """Cells of `mask` that no w x w square inside the mask covers."""
    if w <= 1 or not mask.any():
        return np.zeros_like(mask)
    core = binary_opening(np.pad(mask, w), structure=np.ones((w, w), dtype=bool))[w:-w, w:-w]
    return mask & ~core


def strip_parts(mask: np.ndarray, w: int, min_cells: int = 1) -> list[np.ndarray]:
    """The connected strips of a mask (4-connected), each at least `min_cells` cells."""
    lab, n = label(strip_cells(mask, w))
    return [lab == i for i in range(1, n + 1) if int((lab == i).sum()) >= min_cells]


def neighbours(labels: np.ndarray, part: np.ndarray) -> dict[int, int]:
    """Label -> cells of contact (4-neighbours) around `part`, its own labels and negatives excluded."""
    out: dict[int, int] = {}
    own = set(np.unique(labels[part]).tolist())
    for sl_a, sl_b in (((slice(None), slice(1, None)), (slice(None), slice(None, -1))),
                       ((slice(None), slice(None, -1)), (slice(None), slice(1, None))),
                       ((slice(1, None), slice(None)), (slice(None, -1), slice(None))),
                       ((slice(None, -1), slice(None)), (slice(1, None), slice(None)))):
        hit = part[sl_a]
        vals = labels[sl_b][hit]
        for v in vals.tolist():
            if v >= 0 and v not in own:
                out[v] = out.get(v, 0) + 1
    return out


def relabel(labels: np.ndarray, keep: list[int]) -> tuple[np.ndarray, dict[int, int]]:
    """Labels with only `keep` (in that order, renumbered 0..n-1); other non-negative labels must not remain."""
    mapping = {old: new for new, old in enumerate(keep)}
    out = labels.copy()
    for old, new in mapping.items():
        out[labels == old] = new
    return out, mapping


__all__ = ["neighbours", "relabel", "strip_cells", "strip_parts"]
