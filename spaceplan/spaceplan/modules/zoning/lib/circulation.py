"""Door graph, reachability and D/I evaluation for a space-level layout.

Doors are placed on shared walls of at least the door contact length:
  passable <-> any            open connection or door
  terminal <-> terminal       only when the matrix has a D pair between their types (en-suite)
  zone pairs with forbidden openings (brief), garage only to its linked zones or circulation
Every space must be reachable from the entry through passable spaces only (a bedroom is never a corridor).
Paths through passable rooms consume a strip of the circulation width from those rooms.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from spaceplan.modules.zoning.lib.relation_matrix import ENTRY, PATIO, RelationMatrix

Rect = tuple[float, float, float, float]
TOL = 1e-6


@dataclass(frozen=True)
class Node:
    node_id: str
    space_type: str
    zone: str
    cell: str
    rect: Rect | None
    passable: bool
    circulation: bool          # foyer or carved hall
    min_side: float
    min_area: float
    roles: frozenset[str]
    wet: bool = False


def shared_edge(a: Rect, b: Rect) -> tuple[float, tuple[tuple[float, float], tuple[float, float]] | None]:
    """Length and segment of the common wall of two axis-aligned rectangles."""
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    for xa, xb in ((ax1, bx0), (bx1, ax0)):
        if abs(xa - xb) < TOL:
            lo, hi = max(ay0, by0), min(ay1, by1)
            if hi - lo > TOL:
                return hi - lo, ((xa, lo), (xa, hi))
    for ya, yb in ((ay1, by0), (by1, ay0)):
        if abs(ya - yb) < TOL:
            lo, hi = max(ax0, bx0), min(ax1, bx1)
            if hi - lo > TOL:
                return hi - lo, ((lo, ya), (hi, ya))
    return 0.0, None


@dataclass
class DoorGraph:
    nodes: dict[str, Node]
    adj: dict[str, set[str]] = field(default_factory=dict)
    doors: list[dict] = field(default_factory=list)
    ensuite: set[tuple[str, str]] = field(default_factory=set)  # directed: (room, its en-suite)

    def add(self, a: str, b: str, kind: str, segment) -> None:
        self.adj.setdefault(a, set()).add(b)
        self.adj.setdefault(b, set()).add(a)
        self.doors.append({"a": a, "b": b, "kind": kind, "segment": segment})

    def linked(self, a: str, b: str) -> bool:
        return b in self.adj.get(a, set())


@dataclass(frozen=True)
class DoorRules:
    door_contact: float
    matrix: RelationMatrix
    no_door_zones: frozenset[frozenset[str]]
    garage_zones: frozenset[str]
    entry_zone: str
    entry_interval: tuple[float, float] | None
    entry_min_overlap: float
    footprint: Rect
    patio_facades: tuple[str, ...]
    private_roles: frozenset[str] = frozenset()


def door_allowed(rules: DoorRules, a: Node, b: Node) -> bool:
    if frozenset((a.zone, b.zone)) in rules.no_door_zones and a.zone != b.zone:
        return False
    for g, o in ((a, b), (b, a)):
        if g.zone == "garage":
            return o.circulation or o.zone in rules.garage_zones
    if not a.passable and not b.passable:
        return rules.matrix.d_between_types(a.space_type, b.space_type)
    for t, o in ((a, b), (b, a)):
        if not t.passable and t.roles & rules.private_roles and not o.circulation:
            return False  # bedrooms and private baths open onto a foyer or hall, never onto living rooms
    return True


def build_graph(nodes: dict[str, Node], rules: DoorRules) -> DoorGraph:
    g = DoorGraph(nodes)
    ids = sorted(n for n in nodes if nodes[n].rect is not None)
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            length, seg = shared_edge(nodes[a].rect, nodes[b].rect)
            if length >= rules.door_contact - TOL and door_allowed(rules, nodes[a], nodes[b]):
                both_open = nodes[a].passable and nodes[b].passable
                both_terminal = not nodes[a].passable and not nodes[b].passable
                g.add(a, b, "open" if both_open else ("ensuite" if both_terminal else "door"), seg)
                for x, y in ((a, b), (b, a)):
                    if both_terminal and rules.matrix.d_directed(nodes[x].space_type, nodes[y].space_type):
                        g.ensuite.add((x, y))
    fx0, fy0, fx1, fy1 = rules.footprint
    if rules.entry_interval:
        lo, hi = rules.entry_interval
        candidates = [n for n in ids if abs(nodes[n].rect[1] - fy0) < TOL
                      and min(nodes[n].rect[2], hi) - max(nodes[n].rect[0], lo) >= rules.entry_min_overlap - TOL]
        preferred = [n for n in candidates if nodes[n].zone == rules.entry_zone] or candidates
        for n in preferred[:1]:
            x0, _, x1, _ = nodes[n].rect
            g.add(ENTRY, n, "entry", ((max(x0, lo), fy0), (min(x1, hi), fy0)))
    if rules.patio_facades:
        for n in ids:
            node = nodes[n]
            if node.zone == "garage" or (node.wet and "laundry" not in node.roles):
                continue
            x0, y0, x1, y1 = node.rect
            if "rear" in rules.patio_facades and abs(y1 - fy1) < TOL and x1 - x0 >= rules.door_contact - TOL:
                g.add(n, PATIO, "patio", ((x0, fy1), (x1, fy1)))
    return g


def reachability(g: DoorGraph) -> tuple[dict[str, int], dict[str, str]]:
    """Breadth-first depth from the entry.

    Paths cross passable spaces only. A terminal room reached that way may open one more en-suite room
    (terminal-to-terminal doors exist only for D pairs, e.g. suite -> its bath or walk-in closet).
    """
    depth, parent = {ENTRY: 0}, {}
    queue = deque([ENTRY])
    while queue:
        cur = queue.popleft()
        if cur == PATIO:
            continue
        cur_terminal = cur != ENTRY and not g.nodes[cur].passable
        if cur_terminal and parent.get(cur) in g.nodes and not g.nodes[parent[cur]].passable:
            continue  # already an en-suite hop
        for nxt in sorted(g.adj.get(cur, ())):
            if nxt in depth:
                continue
            if cur_terminal and (cur, nxt) not in g.ensuite:
                continue
            depth[nxt] = depth[cur] + 1
            parent[nxt] = cur
            queue.append(nxt)
    return depth, parent


def _d(g: DoorGraph, a: str, b: str) -> bool:
    """Direct link; for pairs involving a terminal room (or the entry) also through a shared foyer or hall.

    Two open rooms (living, dining, kitchen) must touch: joining them through a corridor is not immediate.
    """
    if a == b or g.linked(a, b):
        return True
    both_open = all(x in g.nodes and g.nodes[x].passable and not g.nodes[x].circulation for x in (a, b))
    if both_open:
        return False
    return any(g.nodes[c].circulation and g.linked(b, c) for c in g.adj.get(a, ()) if c in g.nodes)


def _i(g: DoorGraph, a: str, b: str) -> bool:
    if a == b or g.linked(a, b):
        return False
    return any(g.linked(m, b) for m in g.adj.get(a, ()) if m in g.nodes and g.nodes[m].passable)


def evaluate_matrix(matrix: RelationMatrix, g: DoorGraph) -> list[dict]:
    members: dict[str, list[str]] = {}
    for nid, node in g.nodes.items():
        for role in node.roles:
            members.setdefault(role, []).append(nid)
    members["access"] = [ENTRY] if ENTRY in g.adj else []
    members["patio"] = [PATIO] if PATIO in g.adj else []
    out = []
    for p in matrix.pairs:
        A, B = sorted(set(members.get(p.a, []))), sorted(set(members.get(p.b, [])))
        test = _d if p.type == "D" else _i
        if not A or not B:
            out.append({"pair": p.pair_id, "type": p.type, "kind": p.kind, "weight": p.weight,
                        "applicable": False, "satisfied": True, "detail": "role absent"})
            continue
        if p.a == p.b:
            checks = [(x, y) for i, x in enumerate(A) for y in A[i + 1:]]
            if not checks:
                out.append({"pair": p.pair_id, "type": p.type, "kind": p.kind, "weight": p.weight,
                            "applicable": False, "satisfied": True, "detail": "single space"})
                continue
            failed = [f"{x}/{y}" for x, y in checks if not test(g, x, y)]
        else:
            failed = [x for x in A if not any(test(g, x, y) for y in B if not (p.type == "I" and x == y))]
        out.append({"pair": p.pair_id, "type": p.type, "kind": p.kind, "weight": p.weight, "applicable": True,
                    "satisfied": not failed, "detail": ("fails for " + ", ".join(failed)) if failed else None})
    by_id = {r["pair"]: r for r in out}
    for grp in matrix.groups:
        members = [by_id[pid] for pid in grp.pair_ids if pid in by_id and by_id[pid]["applicable"]]
        met = sum(m["satisfied"] for m in members)
        out.append({"pair": f"group:{grp.group_id}", "type": "D", "kind": "hard", "weight": 0.0,
                    "applicable": bool(members), "satisfied": (not members) or met >= grp.k,
                    "detail": f"{met} of {len(members)} (needs {grp.k})"})
    return out


def _door_mid(g: DoorGraph, a: str, b: str):
    for d in g.doors:
        if {d["a"], d["b"]} == {a, b} and d["segment"]:
            (x0, y0), (x1, y1) = d["segment"]
            return ((x0 + x1) / 2.0, (y0 + y1) / 2.0)
    return None


def through_strips(g: DoorGraph, parent: dict[str, str], width: float) -> dict[str, float]:
    """Area each passable room gives up to the paths that cross it.

    For a crossed room the strip runs (as an L) from the door it is entered by to the farthest door it
    leads out of; its area is that Manhattan length times the circulation width.
    """
    children: dict[str, list[str]] = {}
    for child, par in parent.items():
        children.setdefault(par, []).append(child)
    strips = {}
    for nid, kids in children.items():
        node = g.nodes.get(nid)
        if node is None or node.circulation or not node.passable or nid not in parent:
            continue
        entry = _door_mid(g, parent[nid], nid)
        exits = [m for m in (_door_mid(g, nid, k) for k in kids) if m is not None]
        if entry is None or not exits:
            continue
        length = max(abs(entry[0] - e[0]) + abs(entry[1] - e[1]) for e in exits)
        strips[nid] = width * max(length, width)
    return strips
