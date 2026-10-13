"""Positions on a structural frame (step 6.7a S2.2g, part E): where the free axes stand and where the zone walls of
both floors go, once the topologies of a (ground, upper) pair are chosen.

    axis shift   a free axis (not on the stair core or the garage) moves within its window; both floors are realized
                 again on each position (same topologies) and the position with the least cost is kept:
                 cost = area deviation of every unit from its program area (sq ft) + surplus_weight x open sq ft
    alignment    the zone walls across the bands (column cuts) of both floors move within the snap reach so upper
                 walls stand on ground walls: a small MILP (lib_aux/milp_tools, HiGHS) with the cut positions
                 (integer cells), one binary per close (upper, ground) wall pair, the unit areas linearized on the
                 free-cell profile at each cut, the least widths, the compact node, the landing kept in its unit and
                 the area band of S2.2g as constraints; objective = area deviation (sq ft) - align_bonus_sqft per
                 aligned wall + a small cost per cell moved
    exact check  each result is checked again by its floor search (prefix sums, every S2 rule); a floor whose result
                 fails keeps its realization

No numbers live here: the settings come from the design registry (positions_settings).
"""

from __future__ import annotations

from dataclasses import replace
from math import ceil
from typing import Any

import numpy as np

from spaceplan.modules.stacking.lib.core_zoning import Realization
from spaceplan.modules.stacking.lib.structural_frame import FREE, Axis, Frame
from spaceplan.modules.stacking.lib_aux.milp_tools import Model
from spaceplan.modules.stacking.lib_aux.structure_grid import grid_offset

MOVE_COST = 1e-3          # tie-break per cell moved (keeps the MILP from moving walls for nothing)


def positions_settings(values: dict[str, Any], s2: dict[str, Any]) -> dict[str, Any] | None:
    """Settings of the position optimization (None when off)."""
    if not values.get("structure.frame.optimize", False):
        return None
    res = float(s2["grid_ft"])
    return {"window_cells": max(0, round(float(values["structure.frame.axis_window_ft"]) / res)),
            "reach_cells": max(0, round(float(values["structure.snap_max_ft"]) / res)),
            "surplus_weight": float(values["structure.frame.surplus_weight"]),
            "align_bonus_sqft": float(values["structure.frame.align_bonus_sqft"])}


# ------------------------------------------------------------------ cost


def pair_cost(rzs: list[Realization], surplus_weight: float) -> float:
    """Area deviation (sq ft) of the units from their program area + surplus_weight x open sq ft."""
    total = 0.0
    for rz in rzs:
        s = rz.search
        ca = s.f.grid.cell_area
        for k, c in enumerate(rz.counts):
            if k not in rz.exempt:
                total += abs(c - s.opt[k]) * ca
        total += surplus_weight * sum(s.f.grid.count(r) for r, _ in rz.open_air) * ca
    return total


# ------------------------------------------------------------------ axis shift


def _shift_topology(topology, old: tuple[int, ...], new: tuple[int, ...]):
    if len(topology) != 4:                                 # an S2 topology on the frame: no frame line to move
        return topology
    axis, bands, cuts, split = topology
    move = dict(zip(old, new, strict=True))
    return axis, bands, tuple(move.get(c, c) for c in cuts), split


def _shift_guide(fg, d: int, axis_cells: set[int]):
    lines = tuple(c + d if c in axis_cells else c for c in fg.lines)
    spine = tuple(c + d if c in axis_cells else c for c in fg.spine) if fg.spine else None
    return lines, replace(fg, lines=tuple(sorted(lines)), spine=spine)


def _axis_cells(frame: Frame, search) -> set[int]:
    g = search.f.grid
    origin = g.x0 if frame.axis == "x" else g.y0
    out = {round((a.pos - origin) / g.res) for a in frame.axes}
    if search.fg.spine:                                   # the hall's second line is a hall width from the first
        out |= set(search.fg.spine)
    return out


def shift_axes(g_rz: Realization, u_rz: Realization, st: dict[str, Any]) -> tuple[Realization, Realization, float]:
    """The pair on the best position of the frame's free axes within their window (same topologies); the shift in
    feet (0: kept)."""
    frame = u_rz.sframe
    if frame is None or not frame.axes or frame.axes[0].tag != FREE or not st["window_cells"]:
        return g_rz, u_rz, 0.0
    us, gs = u_rz.search, g_rz.search
    res = us.f.grid.res
    lo = max(-st["window_cells"], round((frame.axes[0].window[0] - frame.axes[0].pos) / res))
    hi = min(st["window_cells"], round((frame.axes[0].window[1] - frame.axes[0].pos) / res))
    best = (pair_cost([g_rz, u_rz], st["surplus_weight"]), 0, g_rz, u_rz)
    u_cells, g_cells = _axis_cells(frame, us), _axis_cells(frame, gs)
    for d in range(lo, hi + 1):
        if d == 0:
            continue
        u_old = us.fg.lines
        u_new, u_fg = _shift_guide(us.fg, d, u_cells)
        g_old = gs.fg.lines
        g_new, g_fg = _shift_guide(gs.fg, d, g_cells)
        moved = replace(frame, axes=tuple(Axis(a.pos + d * res, a.tag, a.window) for a in frame.axes))
        u_s, g_s = us.shifted(replace(u_fg, ref=moved)), gs.shifted(replace(g_fg, ref=moved))
        u2 = u_s.evaluate(_shift_topology(u_rz.topology, u_old, u_new))
        g2 = g_s.evaluate(_shift_topology(g_rz.topology, g_old, g_new))
        if u2.violation or g2.violation:
            continue
        for rz, s in ((u2, u_s), (g2, g_s)):
            rz.frame, rz.sframe, rz.search = s.f, moved, s
        cost = pair_cost([g2, u2], st["surplus_weight"])
        if cost < best[0] - 1e-9:
            best = (cost, d, g2, u2)
    return best[2], best[3], best[1] * res


# ------------------------------------------------------------------ wall alignment


def _columns(rz: Realization) -> list[dict[str, Any]]:
    """Per band: its row range (lo, hi) across the bands, the ordered units and their column edges."""
    axis, bands = rz.topology[0], rz.topology[1]
    out = []
    for band in bands:
        rects = [rz.rects[u] for u in band]
        if axis == "y":                                     # bands are row ranges, columns along x
            lo, hi = rects[0][2], rects[0][3]
            edges = [rects[0][0]] + [r[1] for r in rects]
        else:
            lo, hi = rects[0][0], rects[0][1]
            edges = [rects[0][2]] + [r[3] for r in rects]
        out.append({"band": band, "lo": lo, "hi": hi, "edges": edges})
    return out


def _profile_at(search, axis: str, lo: int, hi: int, c: int) -> float:
    """Free cells of one line of columns at index c (mean of the lines on both sides of the cut)."""
    prof = search.f.grid.profile("x" if axis == "y" else "y", lo, hi)
    vals = [prof[k] for k in (c - 1, c) if 0 <= k < len(prof)]
    return float(np.mean(vals)) if vals else 0.0


def _rects(rz: Realization, cols: list[dict[str, Any]], pos: dict[tuple[int, int], int]) -> tuple:
    axis = rz.topology[0]
    rects = list(rz.rects)
    for b, col in enumerate(cols):
        edges = [pos.get((b, k), e) for k, e in enumerate(col["edges"])]
        for k, u in enumerate(col["band"]):
            a, z = edges[k], edges[k + 1]
            rects[u] = (a, z, col["lo"], col["hi"]) if axis == "y" else (col["lo"], col["hi"], a, z)
    return tuple(rects)


def _landing_span(search, axis: str, lo: int, hi: int) -> tuple[int, int] | None:
    rows, cols = search.f.landing
    if not len(rows):
        return None
    across, along = (rows, cols) if axis == "y" else (cols, rows)
    inside = (across >= lo) & (across < hi)
    if not inside.any():
        return None
    return int(along[inside].min()), int(along[inside].max()) + 1


def align_walls(g_rz: Realization, u_rz: Realization, st: dict[str, Any],
                time_limit: float = 1.0) -> tuple[Realization, Realization, int]:
    """The pair with its zone walls moved to stand upper on ground (MILP); the walls aligned (0: unchanged)."""
    us, gs = u_rz.search, g_rz.search
    axis = u_rz.topology[0]
    if axis != g_rz.topology[0] or not st["reach_cells"]:
        return g_rz, u_rz, 0
    reach, res = st["reach_cells"], us.f.grid.res
    di, dj = grid_offset(us.f.grid.x0, us.f.grid.y0, gs.f.grid.x0, gs.f.grid.y0, res)
    d_across, d_along = (dj, di) if axis == "y" else (di, dj)    # upper index + d = ground index
    m = Model()
    floors = []
    for rz, s, shift_across, shift_along in ((g_rz, gs, 0, 0), (u_rz, us, d_across, d_along)):
        cols = _columns(rz)
        var: dict[tuple[int, int], int] = {}
        node = s._node()
        tol = s.r.area_tolerance
        ca = s.f.grid.cell_area
        for b, col in enumerate(cols):
            edges = col["edges"]
            for k in range(1, len(edges) - 1):              # interior walls of the band
                e = edges[k]
                var[(b, k)] = m.var(e - reach, e + reach, 0.0, True)
                dev = m.var(0.0, np.inf, MOVE_COST)          # cells moved
                m.row({var[(b, k)]: 1.0, dev: -1.0}, hi=e)
                m.row({var[(b, k)]: -1.0, dev: -1.0}, hi=-e)

            def x(k, b=b, edges=edges, var=var):                      # (coef, const) of edge k
                return ({var[(b, k)]: 1.0}, 0.0) if (b, k) in var else ({}, float(edges[k]))

            span = _landing_span(s, axis, col["lo"], col["hi"])
            for k, u in enumerate(col["band"]):
                (cl, kl), (cr, kr) = x(k), x(k + 1)
                width = {**cr, **{v: -c for v, c in cl.items()}}
                if width:                                    # the least width, as the S2 check reads it
                    m.row(width, lo=ceil((s.units[u].min_width_ft - s.tol) / res - 1e-9) - (kr - kl))
                    if node and u in s.circ and (col["hi"] - col["lo"]) > node:
                        m.row(width, hi=node - (kr - kl))
                if span is not None and rz.landing_unit == u and edges[k] <= span[0] and edges[k + 1] >= span[1]:
                    if cl:
                        m.row(cl, hi=span[0])
                    if cr:
                        m.row(cr, lo=span[1])
                # area of the unit, linearized on the profile at both edges
                pl = _profile_at(s, axis, col["lo"], col["hi"], edges[k])
                pr = _profile_at(s, axis, col["lo"], col["hi"], edges[k + 1])
                coef = {}
                for v, c in cr.items():
                    coef[v] = coef.get(v, 0.0) + pr * c
                for v, c in cl.items():
                    coef[v] = coef.get(v, 0.0) - pl * c
                const = rz.counts[u] - pr * edges[k + 1] * (1 if cr else 0) + pl * edges[k] * (1 if cl else 0)
                if not coef:
                    continue
                if u not in rz.exempt:
                    lo_a = s.opt[u] * (1.0 - tol)
                    hi_a = max(s.opt[u], s.f.targets[u]) * (1.0 + tol)
                    m.row(coef, lo=lo_a - const, hi=hi_a - const)
                    m.abs_dev(coef, const - s.opt[u], ca)
        floors.append((rz, s, cols, var, shift_across, shift_along))
    # alignment pairs: an upper wall and a ground wall in overlapping bands, within twice the reach
    (_, _, gcols, gvar, _, _), (_, _, ucols, uvar, sa, sl) = floors
    zs = []
    for (ub, uk), uv in uvar.items():
        ucol = ucols[ub]
        u_lo, u_hi = ucol["lo"] + sa, ucol["hi"] + sa
        ue = ucol["edges"][uk] + sl
        for (gb, gk), gv in gvar.items():
            gcol = gcols[gb]
            if min(u_hi, gcol["hi"]) <= max(u_lo, gcol["lo"]):
                continue
            if abs(gcol["edges"][gk] - ue) > 2 * reach:
                continue
            z = m.binary(-st["align_bonus_sqft"])
            big = 4 * reach + 1
            m.row({uv: 1.0, gv: -1.0, z: big}, hi=big - sl)      # (u + sl) - g <= big (1 - z)
            m.row({uv: -1.0, gv: 1.0, z: big}, hi=big + sl)      # g - (u + sl) <= big (1 - z)
            zs.append((z, (ub, uk), (gb, gk)))
    if not zs:
        return g_rz, u_rz, 0
    for key in {k for _, k, _ in zs}:                       # each wall in one pair at most
        m.row({z: 1.0 for z, k, _ in zs if k == key}, hi=1.0)
    for key in {k for _, _, k in zs}:
        m.row({z: 1.0 for z, _, k in zs if k == key}, hi=1.0)
    sol = m.solve(time_limit)
    if sol is None:
        return g_rz, u_rz, 0
    out = []
    for rz, s, cols, var, _, _ in floors:
        pos = {key: round(sol[v]) for key, v in var.items()}
        rects = _rects(rz, cols, pos)
        if rects == rz.rects:
            out.append(rz)
            continue
        new = s.recheck(rz, rects)
        out.append(rz if new.violation else new)
    g2, u2 = out
    if g2 is g_rz and u2 is u_rz:
        return g_rz, u_rz, 0
    return g2, u2, _count_aligned(g2, u2, sa, sl)


def _count_aligned(g_rz: Realization, u_rz: Realization, sa: int, sl: int) -> int:
    """Upper zone walls standing on a ground zone wall (same line, overlapping bands)."""
    n = 0
    for ucol in _columns(u_rz):
        for ue in ucol["edges"][1:-1]:
            for gcol in _columns(g_rz):
                if min(ucol["hi"] + sa, gcol["hi"]) > max(ucol["lo"] + sa, gcol["lo"]) and ue + sl in gcol["edges"][1:-1]:
                    n += 1
                    break
    return n


def optimize_pair(g_rz: Realization, u_rz: Realization, st: dict[str, Any] | None) -> tuple[Realization, Realization,
                                                                                               dict[str, Any]]:
    """Axis shift, then wall alignment; the report of what moved."""
    if st is None or g_rz.search is None or u_rz.search is None:
        return g_rz, u_rz, {}
    before = pair_cost([g_rz, u_rz], st["surplus_weight"])
    g1, u1, shift = shift_axes(g_rz, u_rz, st)
    res = u_rz.search.f.grid.res
    di, dj = grid_offset(u1.search.f.grid.x0, u1.search.f.grid.y0, g1.search.f.grid.x0, g1.search.f.grid.y0, res)
    sa, sl = (dj, di) if u1.topology[0] == "y" else (di, dj)
    aligned0 = _count_aligned(g1, u1, sa, sl)
    g2, u2, aligned = align_walls(g1, u1, st)
    if g2 is g1 and u2 is u1:
        aligned = aligned0
    return g2, u2, {"axis_shift_ft": round(shift, 3), "cost_before_sqft": round(before, 1),
                    "cost_after_sqft": round(pair_cost([g2, u2], st["surplus_weight"]), 1),
                    "walls_aligned_before": aligned0, "walls_aligned": aligned,
                    "upper_walls": sum(len(c["edges"]) - 2 for c in _columns(u2))}


__all__ = ["align_walls", "optimize_pair", "pair_cost", "positions_settings", "shift_axes"]
