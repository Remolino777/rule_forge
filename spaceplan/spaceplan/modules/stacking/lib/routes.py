"""Routes of the ground floor from the main door (stage S1.2, client steps 3 and 7).

Walking distance on the zoning grid (4-neighbour steps times the cell size) from the vestibule behind the main door
to the centre of the zone holding each target role (living, dining, kitchen: the reachable cell closest to the
zone's centroid; the nearest edge would reward any zone that merely touches the vestibule) and to the stair start. Only the
zones the catalog lists as passable are crossed (circulation, social, kitchen, service: never bedrooms or the
garage), plus the vestibule and the stair's arrival zone. A target that cannot be reached is reported as None.

Two floors (client decision 2026-10-10): a target that is not on the ground floor (living upstairs on a hillside,
for instance) is walked as door -> stair start, the stair's horizontal length (treads and landings, no effort
factor) and stair arrival -> the target's centre on the upper floor.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from spaceplan.modules.stacking.lib.floor_frame import FIXED_ENTRY, FloorFrame
from spaceplan.modules.stacking.lib_aux.zone_grid import bfs_steps, cells_of

IN_PER_FT = 12.0                                  # unit conversion, not a normative value

STAIR = "stair"


def _centre_cell(mask: np.ndarray, dist: np.ndarray) -> np.ndarray:
    """The reachable cell of a zone closest to the zone's centroid (a one-cell mask)."""
    rows, cols = np.nonzero(mask & (dist >= 0))
    if not len(rows):
        return mask
    cr, cc = np.nonzero(mask)
    r0, c0 = cr.mean(), cc.mean()
    k = int(np.argmin((rows - r0) ** 2 + (cols - c0) ** 2))
    out = np.zeros_like(mask)
    out[rows[k], cols[k]] = True
    return out


def route_lengths(frame: FloorFrame, rects, roles: dict[str, frozenset[str]], cfg: dict[str, Any],
                  source_geom=None, from_landing: bool = False) -> dict[str, Any]:
    """Walking distance to each target on one floor: from the vestibule (ground), or from the stair arrival
    (`from_landing`, upper floor; the stair itself is then not a target). `absent` lists the targets whose role is
    not on this floor."""
    g = frame.grid
    units = frame.units
    passable = np.zeros_like(g.free)
    unit_masks = []
    for u, (i0, i1, j0, j1) in zip(units, rects):
        m = np.zeros_like(g.free)
        m[j0:j1, i0:i1] = g.free[j0:j1, i0:i1]
        unit_masks.append(m)
        if u.zone in cfg["passable_zones"]:
            passable |= m
    landing = np.zeros_like(g.free)
    rows, cols = frame.landing
    landing[rows, cols] = True
    passable |= landing
    if from_landing:
        sources = landing.copy()
    elif FIXED_ENTRY in g.label_ids:
        sources = g.mask_of(FIXED_ENTRY)
    else:
        sources = np.zeros_like(g.free)
        r, c = cells_of(g, source_geom)
        sources[r, c] = True
    if not sources.any():
        return {"total_ft": None, "by_target": {}, "absent": [], "note": "no vestibule"}
    dist = bfs_steps(passable | sources, sources)
    out: dict[str, float | None] = {}
    absent: list[str] = []
    for target in cfg["route_targets"]:
        if target == STAIR and from_landing:
            continue
        if target == STAIR:
            mask = landing
        else:
            types = roles.get(target, frozenset())
            mask = np.zeros_like(g.free)
            for u, m in zip(units, unit_masks):
                if u.space_types & types:
                    mask |= m
        if not mask.any():
            absent.append(target)                     # role absent from this floor
            continue
        if target != STAIR:
            mask = _centre_cell(mask, dist)           # walk into the room: to its centre, not to its edge
        reach = dist[mask & (dist >= 0)]
        out[target] = round(float(reach.min()) * g.res, 2) if reach.size else None
    known = [v for v in out.values() if v is not None]
    return {"total_ft": round(sum(known), 2) if len(known) == len(out) else None, "by_target": out,
            "absent": absent}


def stair_walk_ft(stair: dict[str, Any], flights: int) -> float:
    """Horizontal walking length of a stair: its treads and its landings (flights - 1), no effort factor."""
    return stair["treads"] * stair["tread_in"] / IN_PER_FT + max(0, flights - 1) * stair["landing_ft"]


def two_floor_routes(ground: dict[str, Any], upper: dict[str, Any] | None, walk_ft: float) -> dict[str, Any]:
    """The ground routes completed with the targets that are only upstairs: door -> stair start + stair + arrival
    -> target. A target on neither floor stays out; one that cannot be reached makes the total None."""
    moved = [t for t in ground.get("absent", []) if upper and t in upper["by_target"]]
    if not moved:
        return ground
    by = dict(ground["by_target"])
    to_stair = by.get(STAIR)
    for t in moved:
        up = upper["by_target"][t]
        by[t] = None if to_stair is None or up is None else round(to_stair + walk_ft + up, 2)
    known = [v for v in by.values() if v is not None]
    return {"total_ft": round(sum(known), 2) if len(known) == len(by) else None, "by_target": by,
            "absent": [t for t in ground["absent"] if t not in moved],
            "upper": {"targets": moved, "stair_walk_ft": round(walk_ft, 2),
                      "from_arrival_ft": {t: upper["by_target"][t] for t in moved}}}


__all__ = ["route_lengths", "stair_walk_ft", "two_floor_routes"]
