"""Doors of one floor (step 6.7a S2.1): which walls get a door or an opening, where, how wide and how they swing.

A floor layout is one option per zone unit plus the fixed nodes (main-door vestibule, stair, half bath under the
stair and its vestibule, garage). On its node-label grid:

  1. passable spaces (circulation, living, dining, kitchen, family room, mudroom, the vestibules) are joined by
     cased openings along the cheapest tree from the root (the main-door vestibule downstairs, the stair upstairs;
     crossing a room costs more than crossing circulation), plus an opening for every D pair of passable rooms that
     share a wall long enough;
  2. every other space gets one door (client decision E3): onto circulation when its door rules allow it, else onto
     its host (closet, en-suite bath) or a passable room; private rooms only onto circulation or en suite; the half
     bath only onto a foyer, hall or vestibule (K04); the garage onto circulation, service or kitchen and never a
     sleeping room (O02, self-closing door);
  3. a door sits near a corner of the shared wall (corner return + leaf + frame); its leaf swings into the space it
     serves (closets: into the host; garage: into the dwelling) and the swept quarter disc must stay inside that
     space, off the stair and its landing (S08 / R311.7.6) and off every other swing.
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass, field

import numpy as np

from spaceplan.modules.stacking.lib.space_rules import SpaceRules
from spaceplan.modules.stacking.lib.unit_frame import (
    STAIR_TYPE,
    VESTIBULE_TYPE,
    SpaceFloor,
    SpaceSpec,
    d_pair,
)
from spaceplan.modules.stacking.lib.unit_layout import UnitOption
from spaceplan.modules.stacking.lib.zone_relations import ENTRY, ZoneMatrix
from spaceplan.modules.stacking.lib_aux.space_grid import WallRun, swing_cells, wall_runs

OPENING, DOOR, CLOSET_DOOR, FIXED_DOOR, GARAGE_DOOR, STAIR_LINK = (
    "opening", "door", "closet_door", "fixed", "garage_door", "stair")


@dataclass
class Door:
    a: int                       # served node (the leaf swings into it) or the first node of an opening
    b: int
    kind: str
    run: WallRun | None
    t0: float                    # cells along the wall line
    t1: float
    hinge_t: float | None = None
    toward_plus: bool | None = None
    into_high: bool | None = None
    leaf_cells: float = 0.0
    clear_ft: float = 0.0


@dataclass
class FloorLayout:
    """A composed floor: nodes, labels, doors and the checks' outcome."""

    floor: SpaceFloor
    options: tuple[UnitOption, ...]
    specs: list[SpaceSpec]
    labels: np.ndarray
    root: int | None
    landing_node: int | None
    doors: list[Door] = field(default_factory=list)
    adj: dict[int, set] = field(default_factory=dict)
    violations: list[str] = field(default_factory=list)
    swept: np.ndarray | None = None
    matrix_roles: dict = field(default_factory=dict)

    def node(self, space_id: str) -> int | None:
        return next((k for k, s in enumerate(self.specs) if s.space_id == space_id), None)

    def cells(self, k: int) -> int:
        return int((self.labels == k).sum())


# ------------------------------------------------------------------ composition


def compose(floor: SpaceFloor, options: tuple[UnitOption, ...]) -> FloorLayout:
    labels = floor.base.copy()
    specs = list(floor.fixed)
    for o in options:
        u = floor.units[[x.index for x in floor.units].index(o.unit)]
        i0, i1, j0, j1 = u.box
        view = labels[j0:j1, i0:i1]
        for p in o.pieces:
            view[p.mask] = len(specs)
            specs.append(p.spec)
    landing = _majority(labels, floor.landing)
    if floor.level == 0:
        root = next((k for k, s in enumerate(specs) if s.space_type == "entry_vestibule"), None)
    else:
        root = next((k for k, s in enumerate(specs) if s.space_type == STAIR_TYPE), None)
    return FloorLayout(floor, options, specs, labels, root, landing)


def _majority(labels: np.ndarray, mask: np.ndarray) -> int | None:
    vals = labels[mask]
    vals = vals[vals >= 0]
    if not len(vals):
        return None
    counts = np.bincount(vals)
    return int(counts.argmax())


# ------------------------------------------------------------------ door rules


def _private(rules: SpaceRules, s: SpaceSpec) -> bool:
    return bool(s.roles & rules.private_roles) or (s.zone == "private" and not s.passable)


def door_choices(rules: SpaceRules, matrix: ZoneMatrix, room: SpaceSpec, other: SpaceSpec) -> int | None:
    """Preference rank of a door from a non-passable space `room` onto `other` (lower is better), None when the
    rules forbid it."""
    if other.space_type == STAIR_TYPE:
        return None
    if room.host and room.host == other.space_id:
        return 0                                                   # closet, pantry, en-suite space onto its host
    if room.space_type in rules.half_bath_types:
        return 1 if other.space_type in rules.half_bath_door_to else None
    if room.zone == "garage" or room.space_type.startswith("garage"):
        if other.space_type in rules.garage_forbidden or other.zone not in rules.garage_opens_to:
            return None
        return 1 if other.circulation else 2
    if other.zone == "garage" or other.space_type.startswith("garage"):
        return None                                                # the garage door is placed from the garage side
    if _private(rules, room):
        if other.zone in rules.private_opens_to or other.circulation:
            return 1
        es = rules.s21["doors"]["en_suite"]
        if (not other.passable and room.roles & set(es["from_roles"]) and other.roles & set(es["to_roles"])
                and d_pair(matrix, room, other)):
            return 0 if room.space_type not in es["prefer_circulation"] else 2   # en suite (a shared bath: hall first)
        return None
    if other.circulation:
        return 1
    if other.passable:
        return 2
    if d_pair(matrix, room, other) or (other.host and other.host == room.space_id):
        return 3
    return None


# ------------------------------------------------------------------ geometry of one door


class DoorPlacer:
    def __init__(self, layout: FloorLayout, rules: SpaceRules):
        self.layout, self.rules = layout, rules
        self.res = layout.floor.res
        self.runs = wall_runs(layout.labels)
        f = layout.floor
        self.forbidden = np.zeros(layout.labels.shape, dtype=bool)
        if "stair" in rules.swing_forbidden:
            self.forbidden |= f.stair
        if "landing" in rules.swing_forbidden:
            self.forbidden |= f.landing
        layout.swept = np.zeros(layout.labels.shape, dtype=bool)
        d = rules.door_ft
        self.corner = d["corner_return"] / self.res
        self.frame = d["frame"] / self.res

    def runs_between(self, a: int, b: int) -> list[WallRun]:
        return sorted(self.runs.get((min(a, b), max(a, b)), []), key=lambda r: (-r.cells, r.k, r.t0))

    def longest(self, a: int, b: int) -> float:
        rs = self.runs_between(a, b)
        return rs[0].cells * self.res if rs else 0.0

    def opening(self, a: int, b: int, kind: str = OPENING) -> Door | None:
        """A cased opening (no leaf) as wide as the catalog allows, centred on the longest shared run."""
        need = self.rules.door_ft["interior"] / self.res
        for run in self.runs_between(a, b):
            if run.cells + 1e-9 < need:
                continue
            returns = min(2 * self.corner, run.cells - need)          # kept when the wall allows them
            width = min(self.rules.door_ft["opening"] / self.res, run.cells - returns)
            mid = 0.5 * (run.t0 + run.t1)
            return Door(a, b, kind, run, mid - width / 2, mid + width / 2, clear_ft=width * self.res)
        return None

    def door(self, served: int, other: int, kind: str, accessible: bool, check_swing: bool = True) -> Door | None:
        """A hinged door between `served` (the leaf swings into it) and `other`."""
        leaf = self.rules.leaf_ft("closet" if kind == CLOSET_DOOR else "room", accessible) / self.res
        clear = self.rules.clear_ft("closet" if kind == CLOSET_DOOR else "room", accessible)
        need = leaf + self.frame                       # the corner return is kept when the wall allows it
        labels = self.layout.labels
        fallback = None
        for run in self.runs_between(served, other):
            if run.cells + 1e-9 < need and check_swing:
                continue
            corner = min(self.corner, max(0.0, run.cells - need))
            if not check_swing:                           # a door S1 already sized (half bath under the stair)
                mid = 0.5 * (run.t0 + run.t1)
                half = min(leaf, run.cells) / 2
                return Door(served, other, kind, run, mid - half, mid + half, None, None, run.high == served, leaf, clear)
            into_high = run.high == served
            for toward_plus in (True, False):
                hinge = run.t0 + corner + self.frame / 2 if toward_plus else run.t1 - corner - self.frame / 2
                t0, t1 = (hinge, hinge + leaf) if toward_plus else (hinge - leaf, hinge)
                if not check_swing:
                    return Door(served, other, kind, run, t0, t1, hinge, toward_plus, into_high, leaf, clear)
                sw = swing_cells(labels.shape, run, into_high, hinge, leaf, toward_plus)
                if not sw.any():
                    continue
                if (labels[sw] != served).any() or (sw & self.forbidden).any() or (sw & self.layout.swept).any():
                    continue
                door = Door(served, other, kind, run, t0, t1, hinge, toward_plus, into_high, leaf, clear)
                if self._on_landing(door):            # keep the landing free when another position exists
                    fallback = fallback or (door, sw)
                    continue
                self.layout.swept |= sw
                return door
        if fallback is not None:
            self.layout.swept |= fallback[1]
            return fallback[0]
        return None

    def _on_landing(self, d: Door) -> bool:
        landing = self.layout.floor.landing
        run = d.run
        lo, hi = int(np.floor(d.t0)), int(np.ceil(d.t1))
        if run.vertical:
            cells = landing[max(lo, 0):hi, max(run.k - 1, 0):run.k + 1]
        else:
            cells = landing[max(run.k - 1, 0):run.k + 1, max(lo, 0):hi]
        return bool(cells.any())


# ------------------------------------------------------------------ the floor


def place_doors(layout: FloorLayout, rules: SpaceRules, matrix: ZoneMatrix) -> FloorLayout:
    specs, f = layout.specs, layout.floor
    placer = DoorPlacer(layout, rules)
    adj: dict[int, set] = {k: set() for k in range(len(specs))}
    layout.adj = adj
    if layout.root is None:
        layout.violations.append("root:missing")
        return layout
    if layout.landing_node is None:
        layout.violations.append("landing:missing")
        return layout

    def link(d: Door) -> None:
        layout.doors.append(d)
        adj[d.a].add(d.b)
        adj[d.b].add(d.a)

    stair = next((k for k, s in enumerate(specs) if s.space_type == STAIR_TYPE), None)
    landing = layout.landing_node
    if stair is not None and landing != stair:
        link(Door(landing, stair, STAIR_LINK, None, 0.0, 0.0))

    # 1. passable tree from the root (cheapest crossing; circulation before rooms)
    costs = rules.s21["doors"]["tree_costs"]
    passable = {k for k, s in enumerate(specs) if s.passable and s.space_type != STAIR_TYPE}
    reached = {layout.root} | ({landing} if stair is not None else set())
    if stair is not None:
        reached.add(stair)
    start = [layout.root] if layout.root != stair else [landing]
    dist = {k: 0.0 for k in start}
    heap = [(0.0, k) for k in start]
    parent: dict[int, Door] = {}
    done = set()
    while heap:
        d0, x = heapq.heappop(heap)
        if x in done:
            continue
        done.add(x)
        if x in parent:
            link(parent[x])
        reached.add(x)
        for lo, hi in placer.runs:
            if x not in (lo, hi):
                continue
            y = hi if lo == x else lo
            if y not in passable or y in done:
                continue
            cost = d0 + float(costs["circulation"] if specs[y].circulation else costs["room"])
            if cost >= dist.get(y, float("inf")) - 1e-12:
                continue
            door = placer.opening(x, y)
            if door is None:
                continue
            dist[y] = cost
            parent[y] = door
            heapq.heappush(heap, (cost, y))
    for k in sorted(passable - done):
        layout.violations.append(f"reach:{specs[k].space_type}")
    # openings for D pairs of passable spaces that touch (living-dining, dining-kitchen), and for a D pair with the
    # entry: the room opens onto the circulation space the entry vestibule opens onto (access-living)
    for (lo, hi), _ in sorted(placer.runs.items()):
        if lo in passable and hi in passable and hi not in adj[lo] and not specs[lo].circulation \
                and not specs[hi].circulation and d_pair(matrix, specs[lo], specs[hi]):
            d = placer.opening(lo, hi)
            if d is not None:
                link(d)
    entry = [k for k, s in enumerate(specs) if ENTRY in s.roles]
    for e in entry:
        hubs = [c for c in adj[e] if specs[c].circulation]
        for k, s in enumerate(specs):
            if k not in passable or s.circulation or not d_pair(matrix, specs[e], s):
                continue
            if any(k in adj[c] for c in hubs) or k in adj[e]:
                continue
            for c in hubs:
                if (min(c, k), max(c, k)) in placer.runs:
                    d = placer.opening(c, k)
                    if d is not None:
                        link(d)
                        break

    # 2. one door per other space, iterated until no space can be reached any more
    rooms = [k for k in range(len(specs)) if k not in passable and k != stair and k not in reached]
    pending = sorted(rooms, key=lambda k: (specs[k].host is not None, specs[k].space_id))
    accessible = f.accessible
    out_swing = set(rules.s21["doors"]["out_swing_space_types"])
    fixed_pairs = {(k, j) for k, s in enumerate(specs) for j, t in enumerate(specs)
                   if s.fixed and t.fixed and s.space_type in rules.half_bath_types and t.space_type == VESTIBULE_TYPE}
    progress = True
    no_fit: dict[int, str] = {}
    while pending and progress:
        progress = False
        for k in list(pending):
            room = specs[k]
            cands = []
            for lo, hi in placer.runs:
                if k not in (lo, hi):
                    continue
                j = hi if lo == k else lo
                if j not in reached:
                    continue
                rank = door_choices(rules, matrix, room, specs[j])
                if rank is not None:
                    cands.append((rank, -placer.longest(k, j), j))
            if not cands:
                continue
            for _, _, j in sorted(cands):
                if (k, j) in fixed_pairs:
                    d = placer.door(k, j, FIXED_DOOR, accessible, check_swing=False)
                elif room.zone == "garage" or room.space_type.startswith("garage"):
                    d = placer.door(j, k, GARAGE_DOOR, accessible)            # swings into the dwelling
                elif room.space_type in out_swing:
                    d = placer.door(j, k, CLOSET_DOOR, accessible)            # storage space: leaf swings out
                else:
                    d = placer.door(k, j, DOOR, accessible)
                if d is not None:
                    link(d)
                    reached.add(k)
                    pending.remove(k)
                    progress = True
                    break
            else:
                no_fit[k] = specs[k].space_type
    for k in pending:
        layout.violations.append(f"door:{no_fit[k]}" if k in no_fit else f"reach:{specs[k].space_type}")
    return layout


__all__ = [
    "CLOSET_DOOR",
    "DOOR",
    "FIXED_DOOR",
    "GARAGE_DOOR",
    "OPENING",
    "STAIR_LINK",
    "Door",
    "DoorPlacer",
    "FloorLayout",
    "compose",
    "door_choices",
    "place_doors",
]
