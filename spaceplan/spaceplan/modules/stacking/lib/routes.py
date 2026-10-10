"""Routes of the ground floor from the main door (stage S1.2, client steps 3 and 7).

Walking distance on the zoning grid (4-neighbour steps times the cell size) from the vestibule behind the main door
to the nearest cell of the zone holding each target role (living, dining, kitchen) and to the stair start. Only the
zones the catalog lists as passable are crossed (circulation, social, kitchen, service: never bedrooms or the
garage), plus the vestibule and the stair's arrival zone. A target that cannot be reached is reported as None.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from spaceplan.modules.stacking.lib.floor_frame import FIXED_ENTRY, FloorFrame
from spaceplan.modules.stacking.lib_aux.zone_grid import bfs_steps, cells_of

STAIR = "stair"


def route_lengths(frame: FloorFrame, rects, roles: dict[str, frozenset[str]], cfg: dict[str, Any],
                  source_geom=None) -> dict[str, Any]:
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
    if FIXED_ENTRY in g.label_ids:
        sources = g.mask_of(FIXED_ENTRY)
    else:
        sources = np.zeros_like(g.free)
        r, c = cells_of(g, source_geom)
        sources[r, c] = True
    if not sources.any():
        return {"total_ft": None, "by_target": {}, "note": "no vestibule"}
    dist = bfs_steps(passable | sources, sources)
    out: dict[str, float | None] = {}
    for target in cfg["route_targets"]:
        if target == STAIR:
            mask = landing
        else:
            types = roles.get(target, frozenset())
            mask = np.zeros_like(g.free)
            for u, m in zip(units, unit_masks):
                if u.space_types & types:
                    mask |= m
        if not mask.any():
            continue                                  # role absent from this floor
        reach = dist[mask & (dist >= 0)]
        out[target] = round(float(reach.min()) * g.res, 2) if reach.size else None
    known = [v for v in out.values() if v is not None]
    return {"total_ft": round(sum(known), 2) if len(known) == len(out) else None, "by_target": out}


__all__ = ["route_lengths"]
