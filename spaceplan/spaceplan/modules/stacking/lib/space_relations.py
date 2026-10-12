"""Relation matrix of stage S2.1 (step 6.7a): the S2 matrix (base D/I/N with K05 on top) evaluated on the door graph.

Nodes are the spaces of a floor (halls, closets and the fixed vestibules included); edges are doors and openings.
This closes what S2 left `deferred_to_S2.1`:
  D  met when both roles share a space, a door joins them, or both open onto the same circulation space; two
     passable rooms also meet D when they share a wall (the semantics of the base matrix);
  I  met when they are at most two doors apart;
  N  (no direct door, e.g. the half bath and the living room, K04 / K05) met when no door joins them;
  N with a stair end (K05: no bedroom, private bath or laundry at the landing) met when the role's space holds no
     landing cell and none of its doors opens onto the landing.
Pairs whose roles sit on different floors are measured through the stair (vertical_pairs of the zone matrix, with the
space-level depth limits of the catalog).
"""

from __future__ import annotations

from typing import Any

import numpy as np

from spaceplan.modules.stacking.lib.door_placement import STAIR_LINK, FloorLayout
from spaceplan.modules.stacking.lib.unit_frame import UNDER_STAIR
from spaceplan.modules.stacking.lib.zone_relations import (
    ABSENT,
    DEFERRED,
    ENTRY,
    FAILED,
    MET,
    PATIO,
    STAIR_BOTTOM,
    STAIR_TOP,
    FloorGraph,
    ZoneMatrix,
    ZonePair,
)

WALK_THROUGH = "walk_in_closet"                  # a dressing room on the way from the suite to its bath


def door_touches(layout: FloorLayout, node: int, mask: np.ndarray) -> bool:
    """Does a door of `node` open onto a cell of `mask` (the cells on the other side of its leaf span)?"""
    for d in layout.doors:
        if d.run is None or node not in (d.a, d.b):
            continue
        run = d.run
        lo, hi = int(np.floor(d.t0)), int(np.ceil(d.t1))
        other_high = (run.low == node)
        if run.vertical:
            i = run.k if other_high else run.k - 1
            cells = mask[max(lo, 0):hi, i]
        else:
            j = run.k if other_high else run.k - 1
            cells = mask[j, max(lo, 0):hi]
        if cells.any():
            return True
    return False


def space_graph(layout: FloorLayout, matrix: ZoneMatrix, patio_nodes: set[int]) -> FloorGraph:
    specs = layout.specs
    anchors = {ENTRY: {k for k, s in enumerate(specs) if ENTRY in s.roles},
               PATIO: set(patio_nodes),
               STAIR_BOTTOM if layout.floor.level == 0 else STAIR_TOP: (
                   {layout.landing_node} if layout.landing_node is not None else set()),
               UNDER_STAIR: {k for k, s in enumerate(specs) if UNDER_STAIR in s.roles}}
    located: dict[str, frozenset] = {}
    for role, types in matrix.roles.items():
        if any(t.startswith("@") for t in types):
            nodes = set().union(*(anchors.get(t, set()) for t in types))
        else:
            nodes = {k for k, s in enumerate(specs) if s.space_type in types}
        if nodes:
            located[role] = frozenset(nodes)
    adj = {k: frozenset(v) for k, v in layout.adj.items()}
    circ = frozenset(k for k, s in enumerate(specs) if s.circulation)
    return FloorGraph(adj, circ, located)


def _touch(layout: FloorLayout, a: int, b: int) -> bool:
    lab = layout.labels
    ma, mb = lab == a, lab == b
    return bool((ma[:, 1:] & mb[:, :-1]).any() or (ma[:, :-1] & mb[:, 1:]).any()
                or (ma[1:, :] & mb[:-1, :]).any() or (ma[:-1, :] & mb[1:, :]).any())


def pair_on_space_floor(layout: FloorLayout, g: FloorGraph, p: ZonePair) -> str:
    xa, xb = g.located.get(p.a), g.located.get(p.b)
    if not xa or not xb:
        return ABSENT
    specs = layout.specs
    if p.type == "D":
        for x in xa:
            for y in xb:
                if x == y or y in g.adj.get(x, ()):
                    return MET
                if any(c in g.circulation and y in g.adj.get(c, ()) for c in g.adj.get(x, ())):
                    return MET
                if any(specs[c].space_type == WALK_THROUGH and y in g.adj.get(c, ()) for c in g.adj.get(x, ())):
                    return MET                                  # S2.2c: suite -> walk-in -> bath (client K11)
                if specs[x].passable and specs[y].passable and _touch(layout, x, y):
                    return MET
        return FAILED
    if p.type == "I":
        d = g.dist(xa, xb)
        return MET if d is not None and d <= 2 else FAILED
    if p.stair_pair:
        landing = layout.floor.landing
        stair_roles = {r for r, t in g_roles(layout).items() if t & {STAIR_TOP, STAIR_BOTTOM}}
        other = xb if p.a in stair_roles else xa
        for x in other:
            if (layout.labels[landing] == x).any() or door_touches(layout, x, landing):
                return FAILED
        return MET
    for x in xa:
        for y in xb:
            if x != y and y in g.adj.get(x, ()) and not _stair_link(layout, x, y):
                return FAILED
    return MET


def g_roles(layout: FloorLayout) -> dict[str, frozenset]:
    return layout.matrix_roles


def _stair_link(layout: FloorLayout, x: int, y: int) -> bool:
    return any(d.kind == STAIR_LINK and {d.a, d.b} == {x, y} for d in layout.doors)


def evaluate_space_floor(matrix: ZoneMatrix, layout: FloorLayout, g: FloorGraph) -> dict[str, Any]:
    layout.matrix_roles = matrix.roles
    results = {p.pair_id: pair_on_space_floor(layout, g, p) for p in matrix.pairs}
    hard_failed = [p.pair_id for p in matrix.pairs if p.kind == "hard" and results[p.pair_id] == FAILED]
    for gid, pids, k in matrix.groups:
        known = [pid for pid in pids if results.get(pid) in (MET, FAILED)]
        if known and sum(results[pid] == MET for pid in known) < min(k, len(known)):
            hard_failed.append(f"group:{gid}")
    group_pairs = {pid for _, pids, _ in matrix.groups for pid in pids}
    soft = [p for p in matrix.pairs if p.kind == "soft" and p.type in ("D", "I") and results[p.pair_id] in (MET, FAILED)
            and p.pair_id not in group_pairs]
    total = sum(p.weight for p in soft)
    score = sum(p.weight for p in soft if results[p.pair_id] == MET) / total if total else 1.0
    return {"results": results, "hard_failed": hard_failed, "score": score,
            "deferred": sorted(pid for pid, r in results.items() if r == DEFERRED)}


__all__ = ["door_touches", "evaluate_space_floor", "pair_on_space_floor", "space_graph"]
