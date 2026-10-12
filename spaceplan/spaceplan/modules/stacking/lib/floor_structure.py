"""Structure, stair arrival and grouped bedroom doors of a spaced floor (step 6.7a S2.2f).

    ground floor   spans: every space under the upper floor at most joist_span_max_ft on its short side (the joists
                   bear on its walls; an open great-room boundary is a beam, so each zone spans on its own);
    upper floor    zones: the zone walls (S2 units) stand on the ground walls of the final ground layout (open
                   great-room boundaries removed): each interior run at least min_fraction supported, every beam at
                   most beam_span_max_ft (hard); partitions: share of the walls inside the zones on ground walls
                   (scored);
    any floor      doors of the bedrooms onto circulation: spread (largest distance between them) and route (largest
                   distance from the stair end), scored against the registry targets; halls (connected pieces of
                   circulation) and the stair end's short side for the indicators.

Values come from the design registry through SpaceRules.design; no numbers live here.
"""

from __future__ import annotations

from itertools import combinations
from typing import Any

import numpy as np
import shapely

from spaceplan.modules.stacking.lib.door_placement import FloorLayout, great_room_pair
from spaceplan.modules.stacking.lib.space_rules import SpaceRules
from spaceplan.modules.stacking.lib.unit_frame import OUT
from spaceplan.modules.stacking.lib_aux.space_grid import components
from spaceplan.modules.stacking.lib_aux.structure_grid import (
    bearing_spans,
    edge_walls,
    grid_offset,
    support_report,
    window,
)

UNIT_LABEL0 = 10_000


def enabled(rules: SpaceRules) -> bool:
    return bool(rules.design.get("structure.enabled"))


def ground_wall_labels(layout: FloorLayout, rules: SpaceRules) -> np.ndarray:
    """Labels of a ground layout with the open great-room boundaries removed (no wall there)."""
    lab = layout.labels.copy()
    n = len(layout.specs)
    for a in range(n):
        for b in range(a + 1, n):
            if great_room_pair(layout, rules, a, b):
                lab[lab == b] = a
    return lab


def floor_zone_labels(floor) -> np.ndarray:
    """Labels of the zone units of a SpaceFloor (fixed nodes kept, outside as OUT)."""
    lab = floor.base.copy()
    for k, u in enumerate(floor.units):
        lab[u.mask] = UNIT_LABEL0 + k
    return lab


def zone_labels(layout: FloorLayout) -> np.ndarray:
    """Labels of the zone units of a layout (fixed nodes kept; open air and outside as OUT)."""
    lab = floor_zone_labels(layout.floor)
    lab[layout.labels == OUT] = OUT
    return lab


def _stand(upper_labels: np.ndarray, upper_grid, ground: FloorLayout, rules: SpaceRules, min_fraction: float,
           beam_max: float):
    gg = ground.floor.grid
    di, dj = grid_offset(upper_grid.x0, upper_grid.y0, gg.x0, gg.y0, upper_grid.res)
    return support_report(upper_labels, OUT, ground_wall_labels(ground, rules), OUT, di, dj, upper_grid.res,
                          min_fraction, beam_max)


def _verdict(labels: np.ndarray, grid, zones, bad: list[str], rules: SpaceRules) -> tuple[dict, list[str]]:
    """The hard rule of the structural axes: 'bearing' (default) the joists span at most joist_span_max_ft between
    the outline and the interior walls that stand on the ground floor (those are the structural walls, sharing their
    axis with a ground wall); 'all_zone_walls' every zone wall must stand on the ground walls."""
    d = rules.design
    bearing = bearing_spans(labels, OUT, zones, grid.res, float(d["structure.joist_span_max_ft"]),
                            float(d["structure.support_min_fraction"]), float(d["structure.beam_span_max_ft"]))
    if d.get("structure.axes_rule") == "all_zone_walls":
        return bearing, bad
    return bearing, ([] if bearing["ok"] else ["structure:bearing"])


def upper_structure(upper: FloorLayout, ground: FloorLayout, rules: SpaceRules) -> tuple[dict[str, Any], list[str]]:
    """How the upper layout stands on the ground layout: zones (the structural axes, hard) and partitions (scored)."""
    d = rules.design
    mn, bm = float(d["structure.support_min_fraction"]), float(d["structure.beam_span_max_ft"])
    zones, bad = _stand(zone_labels(upper), upper.floor.grid, ground, rules, mn, bm)
    walls, _ = _stand(upper.labels, upper.floor.grid, ground, rules, mn, bm)
    # bearing lines: any wall of the floor (zone or room wall) that stands on the ground walls
    bearing, bad = _verdict(upper.labels, upper.floor.grid, walls, bad, rules)
    parts, _ = _stand(upper.labels, upper.floor.grid, ground, rules, 0.0, float("inf"))
    return {"zones": zones.to_dict(), "bearing": bearing, "partitions": parts.to_dict()}, bad


def ground_support(ground: FloorLayout, upper_floor, rules: SpaceRules) -> tuple[float, int]:
    """(share of the upper zone walls' interior runs on this ground layout's walls, violations) for scoring the
    ground floor before the upper one is laid out."""
    d = rules.design
    labels = floor_zone_labels(upper_floor)
    rep, bad = _stand(labels, upper_floor.grid, ground, rules,
                      float(d["structure.support_min_fraction"]), float(d["structure.beam_span_max_ft"]))
    _, bad = _verdict(labels, upper_floor.grid, rep, bad, rules)
    return rep.interior_fraction, len(bad)


def below_walls(upper_floor, ground: FloorLayout, rules: SpaceRules) -> tuple[np.ndarray, np.ndarray]:
    """(V, H) ground walls seen from the upper floor's grid (open great-room boundaries removed)."""
    gg, gu = ground.floor.grid, upper_floor.grid
    di, dj = grid_offset(gu.x0, gu.y0, gg.x0, gg.y0, gu.res)
    v, h = edge_walls(ground_wall_labels(ground, rules), OUT)
    ny, nx = gu.labels.shape
    return window(v, (ny, nx + 1), di, dj), window(h, (ny + 1, nx), di, dj)


def span_violation(ground: FloorLayout, under_upper: np.ndarray | None, rules: SpaceRules) -> str | None:
    """A ground space under the upper floor wider than the joist span on its short side."""
    if under_upper is None:
        return None
    limit = float(rules.design["structure.joist_span_max_ft"])
    res = ground.floor.res
    for k, s in enumerate(ground.specs):
        if s.space_type == "stair":
            continue
        m = ground.labels == k
        if not (m & under_upper).any():
            continue
        rows, cols = np.nonzero(m)
        short = min(rows.max() - rows.min() + 1, cols.max() - cols.min() + 1) * res
        if short > limit + 1e-9:
            return f"structure:span:{s.space_type}"
    return None


def under_mask(grid, polygon) -> np.ndarray:
    """Cells of a grid whose centre lies in `polygon` (the upper floor seen from the ground floor)."""
    xs = grid.x0 + (np.arange(grid.nx) + 0.5) * grid.res
    ys = grid.y0 + (np.arange(grid.ny) + 0.5) * grid.res
    gx, gy = np.meshgrid(xs, ys)
    return shapely.contains_xy(polygon, gx, gy)


def landing_centre(layout: FloorLayout) -> tuple[float, float] | None:
    """(x, y) in cells of the stair end zone on this floor."""
    m = layout.floor.landing
    if m is None or not m.any():
        return None
    rows, cols = np.nonzero(m)
    return float(cols.mean() + 0.5), float(rows.mean() + 0.5)


def _door_point(d) -> tuple[float, float] | None:
    if d.run is None:
        return None
    t = 0.5 * (d.t0 + d.t1)
    return (float(d.run.k), t) if d.run.vertical else (t, float(d.run.k))


def bedroom_doors(layout: FloorLayout, rules: SpaceRules) -> list[tuple[float, float]]:
    """Centres (cells) of the doors of sleeping rooms onto circulation."""
    out = []
    for d in layout.doors:
        p = _door_point(d)
        if p is None or d.a < 0 or d.b < 0:
            continue
        a, b = layout.specs[d.a], layout.specs[d.b]
        if (a.space_type in rules.sleeping_types and b.circulation) or \
                (b.space_type in rules.sleeping_types and a.circulation):
            out.append(p)
    return out


def grouping(layout: FloorLayout, rules: SpaceRules) -> tuple[float, dict[str, Any]]:
    """Score (0..1) of the bedroom doors' spread and route from the stair end, and the metrics (ft)."""
    d = rules.design
    res = layout.floor.res
    pts = bedroom_doors(layout, rules)
    centre = landing_centre(layout)
    spread = max((np.hypot(p[0] - q[0], p[1] - q[1]) for p, q in combinations(pts, 2)), default=0.0) * res
    route = max((np.hypot(p[0] - centre[0], p[1] - centre[1]) for p in pts), default=0.0) * res \
        if centre is not None else 0.0
    target, rmax = float(d.get("door.grouping.spread_target_ft") or 0.0), float(d.get("circulation.arrival.route_max_ft")
                                                                              or 0.0)

    def fall(v: float, lim: float) -> float:
        return 1.0 if lim <= 0 or v <= lim else max(0.0, 1.0 - (v - lim) / lim)

    score = 0.5 * fall(spread, target) + 0.5 * fall(route, rmax) if pts else 1.0
    return score, {"bedroom_doors": len(pts), "spread_ft": round(float(spread), 2), "route_ft": round(float(route), 2)}


def arrival_metrics(layout: FloorLayout) -> dict[str, Any]:
    """Pieces of circulation on the floor and the short side of the space that receives the stair."""
    lab = layout.labels
    circ = np.zeros(lab.shape, dtype=bool)
    for k, s in enumerate(layout.specs):
        if s.circulation and s.space_type != "stair":
            circ |= lab == k
    halls = len(components(circ)) if circ.any() else 0
    short = None
    if layout.landing_node is not None:
        rows, cols = np.nonzero(lab == layout.landing_node)
        if len(rows):
            short = round(float(min(rows.max() - rows.min() + 1, cols.max() - cols.min() + 1) * layout.floor.res), 2)
    return {"halls": halls, "arrival_short_side_ft": short}


__all__ = [
    "UNIT_LABEL0",
    "arrival_metrics",
    "bedroom_doors",
    "below_walls",
    "enabled",
    "floor_zone_labels",
    "ground_support",
    "ground_wall_labels",
    "grouping",
    "landing_centre",
    "span_violation",
    "under_mask",
    "upper_structure",
    "zone_labels",
]
