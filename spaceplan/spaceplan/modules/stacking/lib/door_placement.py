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
SLIDER, PATIO_SLIDER, EXTERIOR_DOOR = "closet_slider", "patio_slider", "exterior_door"   # stage S2.1b
EXTERIOR = -1                                    # the other side of an exterior door
OPEN_AIR_TYPES, OUT_LABEL = ("upper_roof", "terrace"), -1   # S2.2d (unit_layout.OPEN_AIR, unit_frame.OUT)
WALK_IN_TYPE, WALK_THROUGH_BATHS = "walk_in_closet", ("primary_bath",)   # S2.2c: the suite only


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
    patio_exit: dict | None = None
    open_air: list = field(default_factory=list)          # S2.2d: (spec, whole-floor mask) of roofs and terraces

    def node(self, space_id: str) -> int | None:
        return next((k for k, s in enumerate(self.specs) if s.space_id == space_id), None)

    def cells(self, k: int) -> int:
        return int((self.labels == k).sum())


# ------------------------------------------------------------------ composition


def compose(floor: SpaceFloor, options: tuple[UnitOption, ...]) -> FloorLayout:
    labels = floor.base.copy()
    specs = list(floor.fixed)
    open_air = []
    for o in options:
        u = floor.units[[x.index for x in floor.units].index(o.unit)]
        i0, i1, j0, j1 = u.box
        view = labels[j0:j1, i0:i1]
        for p in o.pieces:
            if p.spec.space_type in OPEN_AIR_TYPES:        # S2.2d: roof or terrace, outside the house
                view[p.mask] = OUT_LABEL
                whole = np.zeros(labels.shape, dtype=bool)
                whole[j0:j1, i0:i1] = p.mask
                open_air.append((p.spec, whole))
                continue
            view[p.mask] = len(specs)
            specs.append(p.spec)
    landing = _majority(labels, floor.landing)
    if floor.level == 0:
        root = next((k for k, s in enumerate(specs) if s.space_type == "entry_vestibule"), None)
    else:
        root = next((k for k, s in enumerate(specs) if s.space_type == STAIR_TYPE), None)
    return FloorLayout(floor, options, specs, labels, root, landing, open_air=open_air)


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
    if room.between:                                                # K10: a shared bath opens onto the hall only
        return 1 if other.circulation else None
    if (room.host and room.space_type in WALK_THROUGH_BATHS and rules.policy("walk_through_closet")
            and other.space_type == WALK_IN_TYPE and other.host == room.host):
        return 0                                                   # S2.2c: the suite's bath through its walk-in
    if room.host and room.host == other.space_id:
        if room.space_type in WALK_THROUGH_BATHS and rules.policy("walk_through_closet"):
            return 1                                               # straight from the bedroom only without walk-in
        return 0                                                   # closet, pantry, en-suite space onto its host
    if room.host and _private(rules, room) and room.space_type not in rules.s21["doors"]["sliding_space_types"]:
        return None                                                # K10: an en-suite space opens onto its room only
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


def great_room_pair(layout: FloorLayout, rules: SpaceRules, a: int, b: int) -> bool:
    """Both nodes are zones of the great room of an open-plan floor (S2.2c): their boundary is open."""
    if not getattr(layout.floor, "open_plan", False) or a < 0 or b < 0:
        return False
    zones = set(rules.design.get("space.great_room.zones") or ())
    sa, sb = layout.specs[a], layout.specs[b]
    return sa.space_type in zones and sb.space_type in zones and not sa.fixed and not sb.fixed


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
        whole = great_room_pair(self.layout, self.rules, a, b)      # S2.2c: no wall inside the great room
        for run in self.runs_between(a, b):
            if whole:
                return Door(a, b, kind, run, run.t0, run.t1, clear_ft=run.cells * self.res)
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
                if not self._supported(run, into_high, toward_plus, served, leaf):
                    continue                          # the open leaf would stand in the air
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

    def _supported(self, run: WallRun, into_high: bool, toward_plus: bool, served: int, leaf: float) -> bool:
        """The open leaf rests on a wall: the hinge end of the run is a corner of the served space whose wall runs
        on, perpendicular to the door wall, at least as deep as the leaf."""
        labels = self.layout.labels
        ny, nx = labels.shape
        n = int(np.ceil(leaf - 1e-9))
        k = run.k
        if run.vertical:
            cols = range(k, k + n) if into_high else range(k - n, k)
            beside, inside = (run.t0 - 1, run.t0) if toward_plus else (run.t1, run.t1 - 1)
            if not (0 <= beside < ny) or min(cols) < 0 or max(cols) >= nx:
                return False
            a = labels[beside, list(cols)]
            b = labels[inside, list(cols)]
        else:
            rows = range(k, k + n) if into_high else range(k - n, k)
            beside, inside = (run.t0 - 1, run.t0) if toward_plus else (run.t1, run.t1 - 1)
            if not (0 <= beside < nx) or min(rows) < 0 or max(rows) >= ny:
                return False
            a = labels[list(rows), beside]
            b = labels[list(rows), inside]
        return bool((a != served).all() and (b == served).all())

    def slider(self, room: int, other: int, min_width_ft: float, kind: str = SLIDER) -> Door | None:
        """A sliding door (no swing) centred on the longest shared run."""
        need = min_width_ft / self.res
        for run in self.runs_between(room, other):
            if run.cells + 1e-9 < need:
                continue
            width = max(need, min(run.cells - 2 * self.corner, 2 * need))
            mid = 0.5 * (run.t0 + run.t1)
            return Door(room, other, kind, run, mid - width / 2, mid + width / 2, clear_ft=width * self.res)
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
    for (lo, hi), _ in sorted(placer.runs.items()):            # S2.2c: the great room has no inner walls
        if lo >= 0 and hi >= 0 and hi not in adj[lo] and great_room_pair(layout, rules, lo, hi):
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
    pending = sorted(rooms, key=lambda k: (specs[k].host is not None,              # walk-ins before their baths
                                           specs[k].space_type in WALK_THROUGH_BATHS, specs[k].space_id))
    accessible = f.accessible
    out_swing = set(rules.s21["doors"]["out_swing_space_types"])
    sliding = set(rules.s21["doors"]["sliding_space_types"])
    slider_min = float(rules.s21["doors"]["types"]["closet_slider"]["min_width_in"]) / 12.0
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
                elif room.space_type in sliding:
                    d = placer.slider(k, j, slider_min)                      # closets: sliding door, no swing
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
    # K10: a shared bath sits between its two bedrooms (a wall with each)
    need = float(rules.s21["program"]["shared_contact_ft"]) / placer.res
    for k, s in enumerate(specs):
        for b in s.between:
            j = layout.node(b)
            if j is not None and placer.longest(k, j) / placer.res + 1e-9 < need:
                layout.violations.append("k10:shared_bath_not_between")
                break
    if f.level == 0 and not layout.violations:
        layout.patio_exit = place_patio_exit(layout, placer, rules)
        if layout.patio_exit is None:
            layout.violations.append("exit:patio")
    if f.level > 0 and not layout.violations and layout.open_air:
        place_terrace_doors(layout, placer, rules)                 # S2.2d: room -> terrace slider
    return layout


# ------------------------------------------------------------------ the secondary door (patio)


def exterior_runs(labels: np.ndarray, k: int, side: str) -> list[WallRun]:
    """Straight runs of exterior wall of node k on one facade side (low_x, high_x, low_y, high_y)."""
    m = labels == k
    out = labels == EXTERIOR
    ny, nx = labels.shape
    runs: list[WallRun] = []
    if side in ("low_x", "high_x"):
        hit = np.zeros_like(m)
        if side == "low_x":
            hit[:, 1:] = m[:, 1:] & out[:, :-1]
        else:
            hit[:, :-1] = m[:, :-1] & out[:, 1:]
        for i in range(nx):
            col = hit[:, i]
            if not col.any():
                continue
            line = i if side == "low_x" else i + 1
            for t0, t1 in _true_runs(col):
                runs.append(WallRun(EXTERIOR if side == "low_x" else k, k if side == "low_x" else EXTERIOR,
                                    True, line, t0, t1))
    else:
        hit = np.zeros_like(m)
        if side == "low_y":
            hit[1:, :] = m[1:, :] & out[:-1, :]
        else:
            hit[:-1, :] = m[:-1, :] & out[1:, :]
        for j in range(ny):
            row = hit[j, :]
            if not row.any():
                continue
            line = j if side == "low_y" else j + 1
            for t0, t1 in _true_runs(row):
                runs.append(WallRun(EXTERIOR if side == "low_y" else k, k if side == "low_y" else EXTERIOR,
                                    False, line, t0, t1))
    return sorted(runs, key=lambda r: -r.cells)


def _true_runs(v: np.ndarray) -> list[tuple[int, int]]:
    padded = np.concatenate(([0], v.astype(np.int8), [0]))
    d = np.diff(padded)
    return list(zip(np.nonzero(d == 1)[0].tolist(), np.nonzero(d == -1)[0].tolist()))


def _segment_local(floor: SpaceFloor, run: WallRun, t0: float, t1: float):
    from shapely.geometry import LineString

    g = floor.grid
    if run.vertical:
        x = g.x0 + run.k * g.res
        return LineString([(x, g.y0 + t0 * g.res), (x, g.y0 + t1 * g.res)])
    y = g.y0 + run.k * g.res
    return LineString([(g.x0 + t0 * g.res, y), (g.x0 + t1 * g.res, y)])


def _landing_local(floor: SpaceFloor, run: WallRun, t0: float, t1: float, depth_ft: float):
    """Rectangle outside the door, depth_ft deep (R311.3), as wide as the door."""
    from shapely.geometry import box

    g = floor.grid
    a, b = g.x0 + t0 * g.res, g.x0 + t1 * g.res
    if run.vertical:
        a, b = g.y0 + t0 * g.res, g.y0 + t1 * g.res
        x = g.x0 + run.k * g.res
        return box(x - depth_ft, a, x, b) if run.low == EXTERIOR else box(x, a, x + depth_ft, b)
    y = g.y0 + run.k * g.res
    return box(a, y - depth_ft, b, y) if run.low == EXTERIOR else box(a, y, b, y + depth_ft)


def place_terrace_doors(layout: FloorLayout, placer: DoorPlacer, rules: SpaceRules) -> int:
    """S2.2d: a glass slider from each room to the terrace it serves (centred on their common wall); returns how
    many were placed. A terrace without a long enough wall stays a plain roof edge (no door)."""
    placed = 0
    types = rules.s21["doors"]["types"]["patio_slider"]
    for spec, mask in layout.open_air:
        if spec.space_type != "terrace" or not spec.host:
            continue
        k = layout.node(spec.host)
        if k is None:
            continue
        lab = np.where(layout.labels == EXTERIOR, -9, layout.labels)
        lab[mask] = EXTERIOR                      # only the terrace counts as outside here
        best = None
        for side in ("low_x", "high_x", "low_y", "high_y"):
            for run in exterior_runs(lab, k, side):
                if best is None or run.cells > best.cells:
                    best = run
        if best is None:
            continue
        w = float(types["width_in"]) / 12.0 / placer.res
        room = best.cells - 2 * placer.corner
        if room + 1e-9 < w:
            continue
        mid = 0.5 * (best.t0 + best.t1)
        layout.doors.append(Door(k, EXTERIOR, PATIO_SLIDER, best, mid - w / 2, mid + w / 2, clear_ft=w * placer.res))
        placed += 1
    return placed


def place_patio_exit(layout: FloorLayout, placer: DoorPlacer, rules: SpaceRules) -> dict | None:
    """The secondary door of the ground floor (client decision 2026-10-11): from the dining room before the kitchen
    before the laundry or mudroom, on the rear facade first or a side facade; a glass slider from the social rooms
    and the kitchen, a side-hinged door from the service rooms; a landing (R311.3) outside, inside the lot and off
    the lot lines closer than S13 allows; nearest the rear deck of the site plan when there is one."""
    ex = rules.s21["exits"]["patio"]
    types = rules.s21["doors"]["types"]
    f = layout.floor
    ext = f.exterior or {}
    lot, deck = ext.get("lot"), ext.get("deck")
    s13 = float(ext.get("no_openings_below_ft", 0.0))
    landing_ft = float(ext.get("landing_ft", 3.0))
    by_type: dict[str, list[int]] = {}
    for k, s in enumerate(layout.specs):
        by_type.setdefault(s.space_type, []).append(k)
    for st in ex["order"]:
        for k in by_type.get(st, []):
            slider = st in ex["slider_from"]
            if slider:
                big = st in types["patio_slider"]["large_from"]
                widths = ([types["patio_slider"]["width_large_in"]] if big else []) + [types["patio_slider"]["width_in"]]
            else:
                widths = [types["service_exterior"]["leaf_in"]]
            for side in ex["facades"]:
                for run in exterior_runs(layout.labels, k, side):
                    for w_in in widths:
                        w = w_in / 12.0 / placer.res
                        if run.cells + 1e-9 < w + 2 * placer.corner:
                            continue
                        spots = [0.5 * (run.t0 + run.t1) - w / 2]
                        if not slider:                    # a hinged leaf sits at a corner (it rests on a wall)
                            spots = [run.t0 + placer.corner, run.t1 - placer.corner - w]
                        elif deck is not None:              # slide toward the rear deck of the site plan
                            seg = _segment_local(f, run, run.t0, run.t1)
                            c = seg.interpolate(seg.project(deck.centroid))
                            t = ((c.y - f.grid.y0) if run.vertical else (c.x - f.grid.x0)) / placer.res
                            spots.insert(0, min(max(t - w / 2, run.t0 + placer.corner), run.t1 - placer.corner - w))
                        for t0 in spots:
                            t1 = t0 + w
                            landing = _landing_local(f, run, t0, t1, landing_ft)
                            if lot is not None and not lot.buffer(1e-6).covers(landing):
                                continue
                            seg = _segment_local(f, run, t0, t1)
                            if lot is not None and side != "high_y" and seg.distance(lot.exterior) < s13 - 1e-9:
                                continue                  # S13: no opening this close to a lot line
                            into_high = run.high == k
                            if slider:
                                door = Door(k, EXTERIOR, PATIO_SLIDER, run, t0, t1, clear_ft=w * placer.res)
                            else:
                                toward = abs(t0 - (run.t0 + placer.corner)) < 1e-9
                                hinge = t0 + placer.frame / 2 if toward else t1 - placer.frame / 2
                                if not placer._supported(run, into_high, toward, k, w):
                                    continue
                                sw = swing_cells(layout.labels.shape, run, into_high, hinge, w, toward)
                                if (layout.labels[sw] != k).any() or (sw & placer.layout.swept).any():
                                    continue
                                placer.layout.swept |= sw
                                door = Door(k, EXTERIOR, EXTERIOR_DOOR, run, t0, t1, hinge, toward, into_high, w,
                                            w * placer.res - float(rules.door_ft["leaf_over_clear"]))
                            layout.doors.append(door)
                            glass = (w * placer.res * float(types["patio_slider"]["height_in"]) / 12.0
                                     * float(types["patio_slider"]["glass_fraction"])) if slider else 0.0
                            return {"space": layout.specs[k].space_id, "space_type": st, "facade": side,
                                    "kind": door.kind, "width_in": round(w_in, 1), "glass_sqft": round(glass, 1),
                                    "landing": landing, "on_deck": bool(deck is not None
                                                                         and landing.intersects(deck)),
                                    "door": door}
    return None


__all__ = [
    "CLOSET_DOOR",
    "DOOR",
    "EXTERIOR",
    "EXTERIOR_DOOR",
    "FIXED_DOOR",
    "GARAGE_DOOR",
    "OPENING",
    "PATIO_SLIDER",
    "SLIDER",
    "STAIR_LINK",
    "Door",
    "DoorPlacer",
    "FloorLayout",
    "compose",
    "door_choices",
    "great_room_pair",
    "place_doors",
    "place_terrace_doors",
]
