"""Circulation inside the rooms of a floor (step 6.7a S2.2j, client decisions 2026-10-13 23:21-23:30).

R3: in every room of circulation.in_room.types the path from its entry door to each inner door (walk-in, closet,
bath, terrace), circulation.in_room.path_width_ft wide, never crosses the bed: a bed with its clearances (the
room's clear furniture rectangle; the main bedroom's king bed) fits with its head on a wall, off every door swing and
doorway approach, and every doorway of the room is reached from the others around it. Hard when the registry says so.

R2 (measured here, scored in unit_layout and door_placement): the walk-in, closets and bath of a room stand beside
its entry door; `inner_door_gaps` gives the distance from the entry doorway to each inner doorway.

The bed comes from the registry without new numbers: its width is the furniture width less the side clearances and
its length the furniture depth less the foot clearance (space.<type>.bed_clearance_in)."""

from __future__ import annotations

from typing import Any

import numpy as np

from spaceplan.modules.stacking.lib.door_placement import EXTERIOR, OPENING, STAIR_LINK, FloorLayout
from spaceplan.modules.stacking.lib.space_rules import SpaceRules
from spaceplan.modules.stacking.lib_aux.room_paths import approach_cells, bed_fits
from spaceplan.modules.stacking.lib_aux.space_grid import swing_cells


def in_room_settings(rules: SpaceRules) -> dict[str, Any] | None:
    d = rules.design
    if not d.get("circulation.in_room.enabled"):
        return None
    return {"types": set(d.get("circulation.in_room.types") or ()),
            "path_ft": float(d.get("circulation.in_room.path_width_ft") or 3.0),
            "hard": rules.design_kinds.get("circulation.in_room.enabled") == "hard"}


def bed_cells(rules: SpaceRules, space_type: str, master: bool, res: float) -> tuple[int, int, int, int] | None:
    """(bed width, bed length, side clearance, foot clearance) in cells, from the furniture rectangle."""
    opts = rules.furniture_of(space_type, master)
    clear_in = rules.std(space_type, "bed_clearance_in")
    if not opts or clear_in is None:
        return None
    w, d = opts[0]
    c = float(clear_in) / 12.0
    bw, bl = w - 2.0 * c, d - c
    if bw <= 0 or bl <= 0:
        return None
    up = lambda ft: int(np.ceil(ft / res - 1e-9))             # noqa: E731
    return up(bw), up(bl), up(c), up(c)


def _room_doors(layout: FloorLayout, k: int) -> list:
    return [d for d in layout.doors if d.run is not None and d.kind not in (STAIR_LINK,) and k in (d.a, d.b)]


def _entry(layout: FloorLayout, k: int, doors: list):
    """The room's entry: a door onto circulation (else onto any space that does not hang from the room)."""
    specs = layout.specs
    sid = specs[k].space_id
    for d in doors:
        o = d.b if d.a == k else d.a
        if o != EXTERIOR and o >= 0 and specs[o].circulation:
            return d
    for d in doors:
        o = d.b if d.a == k else d.a
        if o != EXTERIOR and o >= 0 and specs[o].host != sid:
            return d
    return None


def _centre(d) -> tuple[float, float]:
    t = 0.5 * (d.t0 + d.t1)
    return (d.run.k, t) if d.run.vertical else (t, d.run.k)


def inner_door_gaps(layout: FloorLayout, k: int) -> list[float]:
    """Distance (ft, centre to centre) from the room's entry doorway to each of its other doorways (R2)."""
    doors = _room_doors(layout, k)
    e = _entry(layout, k, doors)
    if e is None:
        return []
    ex, ey = _centre(e)
    res = layout.floor.res
    return [round(float(np.hypot(*(np.subtract(_centre(d), (ex, ey))))) * res, 2) for d in doors if d is not e]


def check_room(layout: FloorLayout, rules: SpaceRules, k: int, st: dict[str, Any]) -> dict[str, Any] | None:
    """R3 for one room: the bed placement found, or why none; None when the room is not checked."""
    spec = layout.specs[k]
    if spec.fixed or spec.space_type not in st["types"]:
        return None
    res = layout.floor.res
    dims = bed_cells(rules, spec.space_type, spec.master, res)
    room_all = layout.labels == k
    if dims is None or not room_all.any():
        return None
    rows, cols = np.nonzero(room_all)
    j0, j1, i0, i1 = max(rows.min() - 1, 0), rows.max() + 2, max(cols.min() - 1, 0), cols.max() + 2
    room = room_all[j0:j1, i0:i1]
    depth = int(np.ceil(st["path_ft"] / res - 1e-9))
    swings = np.zeros_like(room)
    approaches = []
    doors = _room_doors(layout, k)
    for d in doors:
        run = d.run
        kk = run.k - (i0 if run.vertical else j0)
        off = j0 if run.vertical else i0
        a = approach_cells(room, run.vertical, kk, d.t0 - off, d.t1 - off, depth)
        if a.any():
            approaches.append(a)
        if d.hinge_t is not None and d.kind != OPENING and d.leaf_cells > 0:
            sw = swing_cells(layout.labels.shape, run, d.into_high, d.hinge_t, d.leaf_cells, d.toward_plus)
            swings |= sw[j0:j1, i0:i1] & room
    bw, bl, side, foot = dims
    place = bed_fits(room, swings, approaches, bw, bl, side, foot, 0.5 * st["path_ft"] / res)
    gaps = inner_door_gaps(layout, k)
    return {"space_id": spec.space_id, "space_type": spec.space_type, "master": spec.master,
            "doors": len(doors), "bed_fits": place is not None, "bed_head": place.head if place else None,
            "inner_door_gaps_ft": gaps}


def room_paths(layout: FloorLayout, rules: SpaceRules) -> tuple[list[dict[str, Any]], str | None]:
    """(report per checked room, first violation or None)."""
    st = in_room_settings(rules)
    if st is None:
        return [], None
    out, bad = [], None
    for k in range(len(layout.specs)):
        r = check_room(layout, rules, k, st)
        if r is None:
            continue
        out.append(r)
        if not r["bed_fits"] and st["hard"] and bad is None:
            bad = f"in_room:{r['space_type']}"
    return out, bad


__all__ = ["bed_cells", "check_room", "in_room_settings", "inner_door_gaps", "room_paths"]
