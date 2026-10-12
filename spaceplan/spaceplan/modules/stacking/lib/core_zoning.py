"""Zoning of one floor around the stair core (step 6.7a S2): a lightweight enumerator of band/column topologies.

A topology cuts the floor into one or two bands along an axis (y: access side / far side; x: along the front) and each
band into a row of columns, one zone unit per column. The cuts are placed where each band and column holds its target
free area (grid prefix sums), so the fixed objects (garage, stair, half bath) and polygonal outlines are absorbed by
the columns they fall in. Each realization is checked in this order, stopping at the first violation:

  width     every unit at least its zone's least width;
  area      realized area within the catalog tolerance of the target;
  landing   the arrival zone of the stair falls (mostly) in one unit;
  doors     zone-level door rules (private zones open only onto circulation), every unit reachable from the entry
            (ground) or from the arrival (upper); the garage opens to an allowed zone;
  entry     the entry zone of the house profile on the front facade (ground);
  K04       the vestibule of the half bath under the stair opens onto circulation (ground, half-bath variant);
  K01       the stair arrives into the receiving space of the catalog's arrival order (upper);
  anchors   hard anchors of the house zoning profile (living toward the street, with its fallback);
  matrix    hard pairs and groups of the relation matrix (K05 over the base) with both roles on this floor.

Valid realizations are scored (relations, shape, anchors, stair access); the receiving unit of the bottom end is
recorded so the A/B/C start options (K02) can be read from the same search.

Structure (step S2.2f, when a StructureGuide is given): every cut moves to the nearest line of the guide's walls
within the snap reach (upper floor: the ground floor's zone walls; ground floor: the upper floor's outline over the
ground interior); on the upper floor the realization must stand on the ground floor (structure: each interior zone
wall at least min_fraction on ground walls of its line, every beam at most beam_max_ft) and the circulation zone is
at most node_cells on its short side (compact arrival: what it gives up goes to the other zones of its band).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from itertools import combinations, permutations
from typing import Any

import numpy as np

from spaceplan.modules.stacking.lib.floor_frame import (
    CIRCULATION,
    FIXED_ENTRY,
    FIXED_GARAGE,
    FIXED_STAIR,
    FIXED_VESTIBULE,
    GROUND,
    HALF_BATH_USE,
    FloorFrame,
    arrival_of,
)
from spaceplan.modules.stacking.lib.zone_relations import (
    ENTRY,
    PATIO,
    STAIR_BOTTOM,
    STAIR_TOP,
    FloorGraph,
    ZoneMatrix,
    evaluate_floor,
    floor_graph,
)
from spaceplan.modules.stacking.lib_aux.structure_grid import snap_line, support_report
from spaceplan.modules.stacking.lib_aux.zone_grid import (
    FREE,
    OUTSIDE,
    Rect,
    bounding_cells,
    cells_in,
    cut_index,
    label_contact,
    label_contact_mask,
    shared_contact,
)

PRIVATE = "private"
VIOLATION_ORDER = ("width", "area", "arrival", "structure", "landing", "doors", "entry", "K04", "K01", "hall", "anchors",
                   "matrix")
UNIT_LABEL0 = 100                       # labels of the zone units painted on a grid (structure checks)


@dataclass(frozen=True)
class FloorRules:
    """Catalog and rule values one floor search needs (no numbers live in this module)."""

    door_contact_ft: float
    area_tolerance: float
    receiving_min_share: float
    private_opens_to: frozenset[str]
    garage_opens_to: frozenset[str]
    entry_zone: str
    entry_min_overlap_ft: float
    anchors: tuple[dict[str, Any], ...]
    facade_sides: dict[str, tuple[str, ...]]
    max_aspect: float
    weights: dict[str, float]
    axes: tuple[str, ...]
    max_bands: int
    max_topologies: int
    arrival: str | None = None               # upper floor: K01 most preferred receiving kind
    arrival_order: tuple[str, ...] = ()      # upper floor: allowed receiving kinds by preference (K01)
    stair_hall: dict[str, Any] | None = None  # both floors: stair bordered by circulation, not inside a room


@dataclass(frozen=True)
class StructureGuide:
    """Walls the cuts of one floor snap to (V / H arrays in this floor's grid) and, on the upper floor, the ground
    floor it must stand on (labels painted with the ground zones, in the ground grid, and the offset)."""

    v: Any
    h: Any
    snap_cells: int
    min_density: float
    ground_labels: Any = None
    di: int = 0
    dj: int = 0
    min_fraction: float = 0.0
    beam_max_ft: float = 0.0
    node_cells: int = 0                  # upper floor: largest short side of the circulation zone (0: no limit)
    hard: bool = False                   # structure violations reject the realization (else only scored)


def zone_labels(grid, rects) -> Any:
    """The grid's labels with each zone's free cells painted UNIT_LABEL0 + k."""
    lab = grid.labels.copy()
    for k, (i0, i1, j0, j1) in enumerate(rects):
        sub = lab[j0:j1, i0:i1]
        sub[sub == FREE] = UNIT_LABEL0 + k
    return lab


@dataclass
class Realization:
    topology: tuple[str, tuple[tuple[int, ...], ...]]
    rects: tuple[Rect, ...]
    counts: tuple[int, ...]
    landing_unit: int | None = None
    landing_share: float = 0.0
    entry_unit: int | None = None
    entry_fallback: bool = False
    links: frozenset = frozenset()
    graph: FloorGraph | None = None
    relations: dict[str, Any] = field(default_factory=dict)
    parts: dict[str, float] = field(default_factory=dict)
    score: float = 0.0
    violation: str | None = None
    frame: Any = None                        # the floor frame (unit set) this realization belongs to
    structure: dict[str, Any] | None = None  # S2.2f: how the upper floor stands on the ground floor
    targets: tuple[float, ...] | None = None  # S2.2f: targets after the compact-arrival cap (None: the frame's)


class FloorSearch:
    """Every topology of one floor frame, realized and checked; valid ones scored."""

    def __init__(self, frame: FloorFrame, rules: FloorRules, matrix: ZoneMatrix, pin: int | None = None,
                 guide: StructureGuide | None = None):
        """`pin`: unit whose column (and band) is stretched to cover the stair's arrival zone on this floor;
        `guide`: structure of step S2.2f (None: no snapping, no check)."""
        self.f, self.r, self.m = frame, rules, matrix
        self.guide = guide
        self._capped: list = []
        self.pin = pin
        rows, cols = frame.landing
        self.span = ((int(cols.min()), int(cols.max()) + 1, int(rows.min()), int(rows.max()) + 1)
                     if len(rows) and not frame.landing_in_entry else None)
        if self.span is None:
            self.pin = None
        g = frame.grid
        self.bbox = bounding_cells(g)
        self.outside = g.labels == OUTSIDE
        self.garage = g.mask_of(FIXED_GARAGE) if FIXED_GARAGE in g.label_ids else None
        self.vestibule = g.mask_of(FIXED_VESTIBULE) if FIXED_VESTIBULE in g.label_ids else None
        self.stair = g.mask_of(FIXED_STAIR) if FIXED_STAIR in g.label_ids else None
        self.entry = g.mask_of(FIXED_ENTRY) if FIXED_ENTRY in g.label_ids else None
        self._cum: dict[tuple[str, int, int], np.ndarray] = {}
        self.units = frame.units
        self.types = [u.space_types for u in self.units]
        self.circ = {k for k, u in enumerate(self.units) if u.zone == CIRCULATION}
        self.tol = g.res
        self.tried = 0
        self.truncated = False
        self.first_violations: Counter = Counter()

    # ---------------------------------------------------------------- topologies and realization

    def topologies(self):
        n = len(self.units)
        count = 0
        for axis in self.r.axes:
            orders = [(perm,) for perm in permutations(range(n))]
            if self.r.max_bands == 2 and n >= 2:
                for k in range(1, n):
                    for low in combinations(range(n), k):
                        high = tuple(i for i in range(n) if i not in low)
                        orders += [(p0, p1) for p0 in permutations(low) for p1 in permutations(high)]
            for bands in orders:
                if count >= self.r.max_topologies:
                    self.truncated = True
                    return
                count += 1
                yield axis, bands

    def _cum_profile(self, axis: str, lo: int, hi: int) -> np.ndarray:
        key = (axis, lo, hi)
        if key not in self._cum:
            self._cum[key] = np.cumsum(self.f.grid.profile(axis, lo, hi))
        return self._cum[key]

    def _count(self, cum: np.ndarray, a: int, b: int) -> int:
        return int(cum[b - 1] - (cum[a - 1] if a > 0 else 0)) if b > a else 0

    def _cuts(self, cum: np.ndarray, lo: int, hi: int, targets: list[float]) -> list[int] | None:
        """Positions lo = x0 < x1 < ... < xm = hi giving each column its target (the last takes the rest)."""
        xs, start = [lo], lo
        for t in targets[:-1]:
            k = cut_index(cum, start, int(round(t)))
            if k >= hi:
                return None
            xs.append(k)
            start = k
        xs.append(hi)
        return xs

    def _share(self, cum, lo: int, hi: int, targets: list[float]) -> list[int] | None:
        """Cuts of lo..hi among `targets` scaled to the free cells it holds."""
        room, want = self._count(cum, lo, hi), sum(targets) or 1.0
        return self._cuts(cum, lo, hi, [x * room / want for x in targets])

    def _cut_back(self, cum: np.ndarray, end: int, target: float) -> int:
        """Start s < end such that the cells from s to end are nearest `target`."""
        top = cum[end - 1]
        k = int(np.searchsorted(cum, top - target, side="left"))
        best = min((x for x in (k, k + 1) if 0 <= x < end),
                   key=lambda x: abs(top - (cum[x - 1] if x > 0 else 0) - target), default=0)
        return best

    def _pinned_cuts(self, cum, lo, hi, targets, p: int, span: tuple[int, int]) -> list[int] | None:
        """Cuts whose column p covers `span`; the columns before and after share what is left by their targets.

        Several positions of column p are tried (from the area cuts, ending or starting at the span, centred on it,
        the span alone) and the one with the least largest relative area deviation is kept."""
        m = len(targets)
        ideal = self._cuts(cum, lo, hi, targets)
        tp = targets[p]
        mid = (span[0] + span[1]) // 2
        width = None
        if ideal is not None:
            width = ideal[p + 1] - ideal[p]
        starts = {span[0], self._cut_back(cum, span[1], tp)}
        if ideal is not None:
            starts.add(min(ideal[p], span[0]))
        if width:
            starts.add(mid - width // 2)
        candidates = set()
        for s0 in starts:
            s_ = lo if p == 0 else max(lo + 1, min(s0, span[0]))
            e_ = hi if p == m - 1 else max(span[1], cut_index(cum, s_, int(round(tp))))
            candidates.add((s_, min(e_, hi if p == m - 1 else hi - 1)))
        candidates.add((lo if p == 0 else span[0], hi if p == m - 1 else span[1]))
        best, best_dev = None, None
        for s_, e_ in sorted(candidates):
            if not lo <= s_ < e_ <= hi or (p > 0 and s_ <= lo) or (p < m - 1 and e_ >= hi):
                continue
            if s_ > span[0] or e_ < span[1]:
                continue
            before = self._share(cum, lo, s_, targets[:p]) if p > 0 else [lo]
            after = self._share(cum, e_, hi, targets[p + 1:]) if p < m - 1 else [hi]
            if before is None or after is None:
                continue
            xs = before[:-1] + [s_, e_] + after[1:]
            if not all(x < y for x, y in zip(xs, xs[1:])):
                continue
            dev = max(abs(self._count(cum, x, y) - t) / t for x, y, t in zip(xs, xs[1:], targets) if t > 0)
            if best_dev is None or dev < best_dev - 1e-12:
                best, best_dev = xs, dev
        return best

    def _node(self) -> int:
        """Largest short side (cells) of the upper circulation zone: the registry limit, never less than the stair
        arrival zone needs (S2.2f)."""
        g = self.guide
        if g is None or not g.node_cells or self.f.level == GROUND:
            return 0
        if self.span is None:
            return g.node_cells
        i0, i1, j0, j1 = self.span
        return max(g.node_cells, min(i1 - i0, j1 - j0))

    def _snap(self, xs: list[int], vertical: bool, lo: int, hi: int) -> list[int]:
        """Interior cuts moved to the guide's nearest wall lines (S2.2f), order kept."""
        g = self.guide
        if g is None or g.snap_cells <= 0 or len(xs) < 3:
            return xs
        walls = g.v if vertical else g.h
        out = list(xs)
        for k in range(1, len(out) - 1):
            out[k] = snap_line(walls, vertical, out[k], lo, hi, g.snap_cells, g.min_density, out[k - 1], out[k + 1])
        return out

    def _columns(self, band, cum, c_lo, c_hi, targets, pin, c_span):
        return (self._pinned_cuts(cum, c_lo, c_hi, targets, band.index(pin), c_span) if pin in band
                else self._cuts(cum, c_lo, c_hi, targets))

    def realize(self, topology) -> tuple[Rect, ...] | None:
        axis, bands = topology
        i0, i1, j0, j1 = self.bbox
        t = self.f.targets
        self._capped = []
        node = self._node()
        circ = next(iter(sorted(self.circ)), None) if node else None
        # band axis: y -> bands are row ranges, columns run along x; x -> bands are column ranges, columns along y
        b_lo, b_hi, c_lo, c_hi = (j0, j1, i0, i1) if axis == "y" else (i0, i1, j0, j1)
        band_profile, col_profile = ("y", "x") if axis == "y" else ("x", "y")
        pin, span = self.pin, self.span
        if span is None:
            pin = None
            span = (0, 0, 0, 0)
        b_span, c_span = ((span[2], span[3]), (span[0], span[1])) if axis == "y" else \
            ((span[0], span[1]), (span[2], span[3]))
        if len(bands) == 1:
            ranges = [(b_lo, b_hi)]
        else:
            cum = self._cum_profile(band_profile, c_lo, c_hi)
            cut = cut_index(cum, b_lo, sum(t[u] for u in bands[0]))
            if circ is not None and c_hi - c_lo > node:     # S2.2f: a band holding only the circulation zone
                if bands[0] == (circ,) and cut - b_lo > node:
                    cut = b_lo + node
                    self._capped.append((bands[1], circ))
                elif bands[1] == (circ,) and b_hi - cut > node:
                    cut = b_hi - node
                    self._capped.append((bands[0], circ))
            cut = self._snap([b_lo, cut, b_hi], axis == "x", c_lo, c_hi)[1]
            if pin is not None:
                cut = max(cut, b_span[1]) if pin in bands[0] else min(cut, b_span[0]) if pin in bands[1] else cut
            if not b_lo < cut < b_hi:
                return None
            ranges = [(b_lo, cut), (cut, b_hi)]
        rects: list[Rect | None] = [None] * len(self.units)
        for band, (lo, hi) in zip(bands, ranges):
            cum = self._cum_profile(col_profile, lo, hi)
            targets = [float(t[u]) for u in band]
            xs = self._columns(band, cum, c_lo, c_hi, targets, pin, c_span)
            if circ in band and len(band) > 1 and hi - lo > node and xs is not None:
                k = band.index(circ)                         # S2.2f: compact arrival node
                width = xs[k + 1] - xs[k]
                if width > node:
                    cap = targets[k] * node / width
                    rest = sum(x for q, x in enumerate(targets) if q != k) or 1.0
                    grow = (sum(targets) - cap) / rest
                    targets = [cap if q == k else x * grow for q, x in enumerate(targets)]
                    xs = self._columns(band, cum, c_lo, c_hi, targets, pin, c_span)
                    self._capped.append((tuple(u for u in band if u != circ), circ))
            if xs is None:
                return None
            xs = self._snap(xs, axis == "y", lo, hi)
            for u, a, b in zip(band, xs, xs[1:]):
                rects[u] = (a, b, lo, hi) if axis == "y" else (lo, hi, a, b)
        return tuple(rects)

    # ---------------------------------------------------------------- checks

    def _facade(self, rect: Rect, role: str) -> float:
        return label_contact(self.f.grid, rect, self.outside, self.r.facade_sides[role])

    def _door_ok(self, a: int, b: int) -> bool:
        za, zb = self.units[a].zone, self.units[b].zone
        if za == PRIVATE and zb == PRIVATE:
            return False                     # rooms of the private zone meet through circulation
        for x, y in ((za, zb), (zb, za)):
            if x == PRIVATE and y not in self.r.private_opens_to:
                return False
        return True

    def evaluate(self, topology) -> Realization:
        g, units, t = self.f.grid, self.units, self.f.targets
        rects = self.realize(topology)
        if rects is None:
            return Realization(topology, (), (), violation="width:cut")
        counts = tuple(g.count(r) for r in rects)
        rz = Realization(topology, rects, counts)
        res = g.res
        for k, (u, r) in enumerate(zip(units, rects)):
            w, h = (r[1] - r[0]) * res, (r[3] - r[2]) * res
            if min(w, h) < u.min_width_ft - self.tol:
                rz.violation = f"width:{u.unit_id}"
                return rz
        exempt, scale = set(), {}
        for others, c in self._capped:                    # S2.2f: the capped arrival zone and who took its area
            exempt.add(c)
            tt, tc = sum(t[q] for q in others), sum(counts[q] for q in others)
            for q in others:
                scale[q] = tc / tt if tt else 1.0
        for k, u in enumerate(units):
            tk = t[k] * scale.get(k, 1.0)
            if k not in exempt and tk and abs(counts[k] - tk) > self.r.area_tolerance * tk:
                rz.violation = f"area:{u.unit_id}"
                return rz
        node = self._node()
        if node:                                            # S2.2f: compact arrival node (after pins and snaps)
            for k in self.circ:
                i0_, i1_, j0_, j1_ = rects[k]
                if min(i1_ - i0_, j1_ - j0_) > node:
                    rz.violation = f"arrival:node:{units[k].unit_id}"
                    return rz
        if self._capped:
            rz.targets = tuple(float(counts[k]) if k in exempt else t[k] * scale.get(k, 1.0) for k in range(len(t)))
        if self.guide is not None and self.guide.ground_labels is not None:
            rep, bad = support_report(zone_labels(g, rects), OUTSIDE, self.guide.ground_labels, OUTSIDE,
                                      self.guide.di, self.guide.dj, res, self.guide.min_fraction,
                                      self.guide.beam_max_ft)
            rz.structure = rep.to_dict()
            if bad and self.guide.hard:
                rz.violation = bad[0]
                return rz
        # landing of the stair on this floor
        landing = self.f.landing
        total = len(landing[0])
        if self.f.landing_in_entry:
            pass                                  # the start is in the vestibule: received by the entry zone below
        elif total:
            inside = [cells_in(landing, r) for r in rects]
            best = int(np.argmax(inside))
            rz.landing_unit, rz.landing_share = best, inside[best] / total
            if rz.landing_share < self.r.receiving_min_share:
                rz.violation = "landing:split"
                return rz
        else:
            rz.violation = "landing:outside"
            return rz
        # door links and reachability
        links = set()
        for a in range(len(units)):
            for b in range(a + 1, len(units)):
                if shared_contact(g, rects[a], rects[b]) >= self.r.door_contact_ft - self.tol and self._door_ok(a, b):
                    links.add((a, b))
        rz.links = frozenset(links)
        if self.f.level == GROUND:
            entry = self._entry(rects)
            if entry is None:
                rz.violation = "entry:front"
                return rz
            rz.entry_unit, rz.entry_fallback = entry
            start = rz.entry_unit
            if self.f.landing_in_entry:
                rz.landing_unit, rz.landing_share = rz.entry_unit, 1.0
        else:
            start = rz.landing_unit
        reached = self._reach(start, links)
        missing = [units[k].unit_id for k in range(len(units)) if k not in reached]
        if missing:
            rz.violation = f"doors:unreachable:{missing[0]}"
            return rz
        if self.f.level == GROUND and self.garage is not None and self.garage.any():
            if not any(units[k].zone in self.r.garage_opens_to
                       and label_contact(g, rects[k], self.garage) >= self.r.door_contact_ft - self.tol
                       for k in range(len(units))):
                rz.violation = "doors:garage"
                return rz
        if self.f.level == GROUND and self.f.variant == HALF_BATH_USE and self.vestibule is not None:
            if not any(label_contact(g, rects[k], self.vestibule) >= self.r.door_contact_ft - self.tol
                       for k in self.circ):
                rz.violation = "K04:vestibule"
                return rz
        if self.f.level != GROUND and not self._arrival_ok(rz.landing_unit):
            rz.violation = f"K01:{self.r.arrival}"
            return rz
        hall = self._stair_hall(rects)
        if hall:
            rz.violation = hall
            return rz
        anchor_score, anchor_fail = self._anchors(rects)
        if anchor_fail:
            rz.violation = f"anchors:{anchor_fail}"
            return rz
        rz.graph = self._graph(rz, rects)
        rz.relations = evaluate_floor(self.m, rz.graph)
        if rz.relations["hard_failed"]:
            rz.violation = f"matrix:{rz.relations['hard_failed'][0]}"
            return rz
        rz.parts = {"relations": rz.relations["score"], "shape": self._shape(rects, counts),
                    "stair_access": self._stair_access(rz)}
        if rz.structure is not None:
            rz.parts["structure"] = rz.structure["interior_fraction"]
        if self.f.level == GROUND:
            rz.parts["anchors"] = anchor_score
        elif self._order():
            rz.parts["arrival"] = self._arrival_score(rz.landing_unit)
        w = self.r.weights
        rz.score = sum(w[k] * v for k, v in rz.parts.items()) / (sum(w[k] for k in rz.parts) or 1.0)
        return rz

    def _entry(self, rects) -> tuple[int, bool] | None:
        need = self.r.entry_min_overlap_ft - self.tol
        if self.entry is not None and self.entry.any():
            # stage S1.2: the main door and its vestibule are fixed; the entry zone is the one opening onto it
            touching = [k for k, u in enumerate(self.units) if u.zone != PRIVATE
                        and label_contact(self.f.grid, rects[k], self.entry) >= self.r.door_contact_ft - self.tol]
            main = [k for k in touching if self.units[k].zone == self.r.entry_zone]
            if main:
                return main[0], False
            return (touching[0], True) if touching else None
        main = [k for k, u in enumerate(self.units) if u.zone == self.r.entry_zone
                and self._facade(rects[k], "main_street") >= need]
        if main:
            return main[0], False
        living = set().union(*(set(a["space_types"]) for a in self.r.anchors if a.get("facade_role") == "main_street"))
        fallback = [k for k, u in enumerate(self.units) if u.hosts(living)
                    and self._facade(rects[k], "main_street") >= need]
        return (fallback[0], True) if fallback else None

    @staticmethod
    def _reach(start: int, links) -> set[int]:
        adj: dict[int, set[int]] = {}
        for a, b in links:
            adj.setdefault(a, set()).add(b)
            adj.setdefault(b, set()).add(a)
        seen, stack = {start}, [start]
        while stack:
            x = stack.pop()
            for y in adj.get(x, ()):
                if y not in seen:
                    seen.add(y)
                    stack.append(y)
        return seen

    def _order(self) -> tuple[str, ...]:
        return self.r.arrival_order or ((self.r.arrival,) if self.r.arrival else ())

    def _arrival_ok(self, unit: int | None) -> bool:
        return unit is not None and arrival_of(self.units[unit], list(self._order())) is not None

    def _arrival_score(self, unit: int) -> float:
        """K01 as a preference: 1 for the most preferred receiving kind, less down the order."""
        order = list(self._order())
        kind = arrival_of(self.units[unit], order)
        return (len(order) - order.index(kind)) / len(order) if kind in order else 0.0

    def _stair_hall(self, rects) -> str | None:
        """The stair borders the circulation (or the entry vestibule) along at least a stair width, and the living
        or kitchen zones along no more than the catalog share of its edge: never in the middle of a room."""
        cfg = self.r.stair_hall
        if not cfg or self.stair is None or not self.stair.any():
            return None
        g = self.f.grid
        contact = [label_contact(g, r, self.stair) for r in rects]
        total = sum(contact) + (label_contact_mask(g, self.entry, self.stair) if self.entry is not None else 0.0)
        circ = sum(c for c, u in zip(contact, self.units) if u.zone == CIRCULATION)
        circ += label_contact_mask(g, self.entry, self.stair) if self.entry is not None else 0.0
        open_ = sum(c for c, u in zip(contact, self.units) if u.zone in cfg["open_zones"])
        if circ < cfg["min_circulation_contact_ft"] - self.tol:
            return "hall:no_circulation"
        if total and open_ / total > cfg["max_open_zone_share"] + 1e-9:
            return "hall:inside_room"
        private_max = cfg.get("max_private_unit_share")
        if total and private_max is not None and any(
                c / total > private_max + 1e-9 for c, u in zip(contact, self.units) if u.zone == PRIVATE):
            return "hall:inside_private"
        return None

    def _anchors(self, rects) -> tuple[float, str | None]:
        if self.f.level != GROUND or not self.r.anchors:
            return 1.0, None
        total = got = 0.0
        for a in self.r.anchors:
            holders = [k for k, u in enumerate(self.units) if u.hosts(a["space_types"])]
            if not holders:
                continue
            best = max(self._facade(rects[k], a["facade_role"]) for k in holders)
            value = 1.0 if best >= a["min_contact_ft"] - self.tol else 0.0
            if not value and a.get("fallback_role") in self.r.facade_sides:
                fb = max(self._facade(rects[k], a["fallback_role"]) for k in holders)
                if fb >= self.r.door_contact_ft - self.tol:
                    value = 1.0 - float(a.get("fallback_penalty", 0.0))
            if not value and a["kind"] == "hard":
                return 0.0, a["anchor_id"]
            total += a["weight"]
            got += a["weight"] * value
        return (got / total if total else 1.0), None

    def _graph(self, rz: Realization, rects) -> FloorGraph:
        anchors: dict[str, set] = {}
        pseudo: dict[str, set[int]] = {}
        if self.f.level == GROUND:
            anchors[ENTRY] = {ENTRY}
            pseudo[ENTRY] = {rz.entry_unit}
            patio = {k for k, u in enumerate(self.units) if u.zone not in (PRIVATE,)
                     and self._facade(rects[k], "garden") >= self.r.door_contact_ft - self.tol}
            if patio:
                anchors[PATIO] = {PATIO}
                pseudo[PATIO] = patio
            anchors[STAIR_BOTTOM] = {rz.landing_unit}
        else:
            anchors[STAIR_TOP] = {rz.landing_unit}
        return floor_graph(self.m, self.types, set(rz.links), self.circ, anchors, pseudo)

    def _shape(self, rects, counts) -> float:
        g = self.f.grid
        total = sum(counts) or 1
        value = 0.0
        for r, c in zip(rects, counts):
            w, h = r[1] - r[0], r[3] - r[2]
            fill = g.inside_count(r) / (w * h)
            aspect = max(w, h) / max(min(w, h), 1)
            value += c / total * (0.5 * fill + 0.5 * min(1.0, self.r.max_aspect / aspect))
        return value

    def _stair_privacy(self, rects) -> float:
        """Share of the stair's wall that does not border a private zone (a flight running through a bedroom zone
        is a poor stair hall even when both ends land right)."""
        if self.stair is None or not self.stair.any():
            return 1.0
        g = self.f.grid
        contact = [label_contact(g, r, self.stair) for r in rects]
        total = sum(contact)
        private = sum(c for c, u in zip(contact, self.units) if u.zone == PRIVATE)
        return 1.0 - private / total if total else 1.0

    def _stair_access(self, rz: Realization) -> float:
        """Depth from the entry to the start (ground) or from the arrival to the private zones (upper), times the
        share of the stair's wall that does not border a private zone."""
        g = rz.graph
        privacy = self._stair_privacy(rz.rects)
        if self.f.level == GROUND:
            d = g.dist({rz.entry_unit}, {rz.landing_unit})
            return privacy / (1.0 + d) if d is not None else 0.0
        private = [k for k, u in enumerate(self.units) if u.zone == PRIVATE]
        if not private:
            return privacy
        d = max(g.dist({rz.landing_unit}, {k}) or 0 for k in private)
        return privacy / (1.0 + max(0, d - 1))

    # ---------------------------------------------------------------- search

    def run(self) -> list[Realization]:
        valid = []
        for topology in self.topologies():
            self.tried += 1
            rz = self.evaluate(topology)
            if rz.violation is None:
                rz.frame = self.f
                valid.append(rz)
            else:
                self.first_violations[rz.violation.split(":")[0]] += 1
        valid.sort(key=lambda x: (-x.score, x.topology))
        return valid

    def summary(self, valid: list[Realization]) -> dict[str, Any]:
        return {"units": len(self.units), "topologies_tried": self.tried, "valid": len(valid),
                "truncated": self.truncated,
                "first_violations": {k: self.first_violations[k] for k in VIOLATION_ORDER if self.first_violations[k]}
                | {k: v for k, v in sorted(self.first_violations.items()) if k not in VIOLATION_ORDER}}


__all__ = ["PRIVATE", "UNIT_LABEL0", "VIOLATION_ORDER", "FloorRules", "FloorSearch", "Realization", "StructureGuide",
           "zone_labels"]
