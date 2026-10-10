"""Relation matrix of stage S2 (step 6.7a): the base D/I/N matrix of the zoning catalog with the client extension
K05 merged on top, evaluated at the level of zones on each floor and between floors through the stair.

Precedence (client decision 2026-10-10, D4): a K05 pair replaces the base pair of the same roles and the replaced
pair is reported (overridden_by K05). Roles starting with "@" are anchors: @entry (the entry zone), @patio (zones on
the garden facade), @stair_bottom and @stair_top (the zones that receive the stair ends).

Zone-level semantics (doors are placed in stage S2.1):
  D  met when both roles share a zone, their zones are linked by a door, or both zones open onto the same
     circulation zone;
  I  met when the zones are at most two links apart;
  N  hard pairs with a stair end are violated when both roles share a zone other than circulation (the stair would
     land in that room); sharing a circulation zone (a laundry closet off the hall) is deferred to the door level;
     other N pairs (no direct door, e.g. the vestibulated half bath) are deferred to the door level.
A pair whose roles never share a floor is measured through the stair: links from the role to the bottom zone, one
for the stair, links from the top zone to the other role; met when the depth is within the catalog's limit.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Any

from spaceplan.modules.zoning.lib.relation_matrix import load_matrix

ENTRY, PATIO, STAIR_TOP, STAIR_BOTTOM = "@entry", "@patio", "@stair_top", "@stair_bottom"
MET, FAILED, DEFERRED, ABSENT = "met", "failed", "deferred", "absent"


@dataclass(frozen=True)
class ZonePair:
    a: str
    b: str
    type: str
    kind: str
    weight: float
    source: str                       # "base" or the client rule id
    overrides: str | None = None      # base pair id replaced by this one
    stair_pair: bool = False          # one role is a stair end
    anchored: bool = False            # one role is an anchor (@...)

    @property
    def pair_id(self) -> str:
        return f"{self.type}:{self.a}-{self.b}"


@dataclass(frozen=True)
class ZoneMatrix:
    roles: dict[str, frozenset[str]]
    pairs: tuple[ZonePair, ...]
    groups: tuple[tuple[str, tuple[str, ...], int], ...]
    overrides: tuple[dict[str, Any], ...]


def build_matrix(catalog, client_relations: dict[str, Any], default_weights: dict[str, float]) -> ZoneMatrix:
    """Base house matrix + K05 (client) with K05 taking precedence."""
    base = load_matrix(catalog, "house")
    roles = dict(base.roles)
    for role, members in client_relations["roles"].items():
        roles[role] = frozenset(members)
    stair = {r for r, t in roles.items() if t & {STAIR_TOP, STAIR_BOTTOM}}
    anchor = {r for r, t in roles.items() if any(x.startswith("@") for x in t)}

    def flags(a: str, b: str) -> dict[str, bool]:
        return {"stair_pair": bool({a, b} & stair), "anchored": bool({a, b} & anchor)}

    pairs: dict[frozenset, ZonePair] = {
        frozenset((p.a, p.b)): ZonePair(p.a, p.b, p.type, p.kind, p.weight, "base", **flags(p.a, p.b))
        for p in base.pairs}
    overrides = []
    rule_id = client_relations["rule_id"]
    for r in client_relations["relations"]:
        a, b = r["a"], r["b"]
        key = frozenset((a, b))
        old = pairs.get(key)
        new = ZonePair(a, b, r["type"], r["kind"], float(r.get("weight", default_weights[r["type"]])), rule_id,
                       old.pair_id if old else None, **flags(a, b))
        if old is not None:
            overrides.append({"pair": old.pair_id, "kind": old.kind, "overridden_by": rule_id,
                              "now": new.pair_id, "now_kind": new.kind, "note": r.get("note")})
        pairs[key] = new
    groups = tuple((g.group_id, g.pair_ids, g.k) for g in base.groups)
    return ZoneMatrix(roles, tuple(pairs.values()), groups, tuple(overrides))


# ------------------------------------------------------------------ zone graph of one floor


@dataclass(frozen=True)
class FloorGraph:
    """Zones of a realized floor (nodes 0..n-1, plus @entry / @patio pseudo-nodes on the ground floor)."""

    adj: dict[Any, frozenset]
    circulation: frozenset            # nodes that are circulation zones
    located: dict[str, frozenset]     # role -> nodes holding it on this floor

    def dist(self, sources, targets) -> int | None:
        targets = set(targets)
        seen = {s: 0 for s in sources}
        queue = deque(sources)
        while queue:
            x = queue.popleft()
            if x in targets:
                return seen[x]
            for y in self.adj.get(x, ()):
                if y not in seen:
                    seen[y] = seen[x] + 1
                    queue.append(y)
        return None


def role_nodes(matrix: ZoneMatrix, unit_types: list[frozenset[str]], anchors: dict[str, set]) -> dict[str, frozenset]:
    out = {}
    for role, types in matrix.roles.items():
        if any(t.startswith("@") for t in types):
            nodes = set().union(*(anchors.get(t, set()) for t in types))
        else:
            nodes = {k for k, ut in enumerate(unit_types) if ut & types}
        if nodes:
            out[role] = frozenset(nodes)
    return out


def floor_graph(matrix: ZoneMatrix, unit_types: list[frozenset[str]], links: set[tuple[int, int]],
                circulation: set[int], anchors: dict[str, set], pseudo_links: dict[str, set[int]]) -> FloorGraph:
    """Graph of door links; pseudo-nodes (@entry, @patio) linked to the zones they open to."""
    adj: dict[Any, set] = {k: set() for k in range(len(unit_types))}
    for a, b in links:
        adj[a].add(b)
        adj[b].add(a)
    for node, zs in pseudo_links.items():
        adj.setdefault(node, set())
        for z in zs:
            adj[node].add(z)
            adj[z].add(node)
    located = role_nodes(matrix, unit_types, anchors)
    return FloorGraph({k: frozenset(v) for k, v in adj.items()}, frozenset(circulation), located)


def _direct(g: FloorGraph, xa, xb) -> bool:
    for x in xa:
        for y in xb:
            if x == y or y in g.adj.get(x, ()):
                return True
            if any(c in g.circulation and y in g.adj.get(c, ()) for c in g.adj.get(x, ())):
                return True
    return False


def pair_on_floor(g: FloorGraph, p: ZonePair) -> str:
    xa, xb = g.located.get(p.a), g.located.get(p.b)
    if not xa or not xb:
        return ABSENT
    if p.type == "D":
        return MET if _direct(g, xa, xb) else FAILED
    if p.type == "I":
        d = g.dist(xa, xb)
        return MET if d is not None and d <= 2 else FAILED
    if p.stair_pair:
        shared = xa & xb
        if shared - g.circulation:
            return FAILED                     # the stair end lands in that room's zone
        return DEFERRED if shared else MET    # a hall holding a closet: kept off the landing at the door level
    return DEFERRED


def evaluate_floor(matrix: ZoneMatrix, g: FloorGraph) -> dict[str, Any]:
    """Pairs whose roles both sit on this floor: hard failures, soft score, deferred pairs."""
    results = {p.pair_id: pair_on_floor(g, p) for p in matrix.pairs}
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


def vertical_pairs(matrix: ZoneMatrix, ground: FloorGraph, upper: FloorGraph, bottom: int, top: int,
                   depth_ok: dict[str, int]) -> dict[str, Any]:
    """Pairs whose roles never share a floor, measured through the stair."""
    out, total, met = [], 0.0, 0.0
    for p in matrix.pairs:
        if p.type not in ("D", "I") or p.anchored:
            continue
        g_a, g_b, u_a, u_b = (ground.located.get(p.a), ground.located.get(p.b), upper.located.get(p.a),
                              upper.located.get(p.b))
        if (g_a and g_b) or (u_a and u_b):
            continue                              # measured on the floor they share
        if g_a and u_b:
            low, high = ground.dist(g_a, {bottom}), upper.dist({top}, u_b)
        elif u_a and g_b:
            low, high = ground.dist(g_b, {bottom}), upper.dist({top}, u_a)
        else:
            continue
        depth = None if low is None or high is None else low + 1 + high
        ok = depth is not None and depth <= depth_ok[p.type]
        total += p.weight
        met += p.weight if ok else 0.0
        out.append({"pair": p.pair_id, "kind": p.kind, "depth": depth, "met": ok})
    return {"pairs": out, "score": met / total if total else 1.0}


__all__ = ["ABSENT", "DEFERRED", "ENTRY", "FAILED", "MET", "PATIO", "STAIR_BOTTOM", "STAIR_TOP", "FloorGraph",
           "ZoneMatrix", "ZonePair", "build_matrix", "evaluate_floor", "floor_graph", "pair_on_floor", "role_nodes",
           "vertical_pairs"]
