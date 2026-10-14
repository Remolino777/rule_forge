"""The upper hall trimmed to what it serves (step 6.7a S2.2h, client 2026-10-12 21:42-22:03).

On a composed upper floor with its doors:

    served      the stair landing, and the hall in front of every door or opening onto it (door_margin_ft beyond each
                jamb); each rectangle of the hall keeps the stretch between its first and its last served position
                (and where it meets the other rectangles of the hall); the vestibule before the first bedroom door
                comes from the door placement (circulation.upper_hall.vestibule_min_ft)
    linen       the largest remainder starts with a linen closet as wide as the hall (wall to wall) and
                space.closets.linen_depth_ft deep, opening onto the hall it closes
    remainder   each piece left, by what it touches:
                  two bedrooms  cut across where one room's side ends and the other's begins (balanced): a closet of
                                each room (space.closets.reach_in_depth_ft deep against the far wall, the rest of the
                                width joins the room), a walk-in from walk_in_from_ft wide
                  one bedroom   on a facade: roof (tail_one_room); inside: its closet, or it joins the room
                  no bedroom    on a facade: roof (tail_no_room); inside: it joins the neighbour space
                pieces smaller than a closet and shorter than two cells stay hall

The trimmed floor is a new FloorLayout without doors: the caller places the doors again and runs every check; when
a check fails the floor keeps its hall. Values come from the design registry (SpaceRules.design).
"""

from __future__ import annotations

from typing import Any

import numpy as np

from spaceplan.modules.stacking.lib.door_placement import FloorLayout
from spaceplan.modules.stacking.lib.space_rules import SpaceRules
from spaceplan.modules.stacking.lib.unit_frame import OUT, SpaceSpec
from spaceplan.modules.stacking.lib.unit_layout import BATH_TYPES, ROOF_TYPE, WALK_IN, _closet_spec
from spaceplan.modules.stacking.lib_aux.hall_geometry import (
    along,
    cells,
    positions_hit,
    rectangles,
    ring,
    run_cells,
    sides,
    span,
    sub,
)

HALL_TYPE = "hall"
ROOF, CLOSET, NEIGHBOUR = "roof", "closet", "neighbour"


def trim_settings(rules: SpaceRules) -> dict[str, Any] | None:
    """Settings of the trim from the design registry (None when it is off)."""
    d = rules.design
    if not d.get("circulation.upper_hall.trim"):
        return None
    return {"margin_ft": float(d.get("circulation.upper_hall.door_margin_ft") or 0.0),
            "linen": bool(d.get("circulation.upper_hall.linen")),
            "linen_ft": float(d.get("space.closets.linen_depth_ft") or 2.0),
            "closet_ft": float(d.get("space.closets.reach_in_depth_ft") or 2.0),
            "walk_in_ft": float(d.get("circulation.upper_hall.walk_in_from_ft") or 5.0),
            "one_room": str(d.get("circulation.upper_hall.tail_one_room") or ROOF),
            "no_room": str(d.get("circulation.upper_hall.tail_no_room") or ROOF),
            "roof_min_sqft": float(d.get("structure.roofs.min_piece_sqft") or 0.0)}


# ------------------------------------------------------------------ served hall and remainders


def hall_nodes(layout: FloorLayout) -> list[int]:
    return [k for k, s in enumerate(layout.specs) if s.space_type == HALL_TYPE and not s.fixed]


def remainders(layout: FloorLayout, margin_ft: float) -> list[tuple[tuple[int, int, int, int], str, str]]:
    """Pieces of the hall beyond what it serves: (rectangle, hall axis, side facing the served hall 'lo' / 'hi')."""
    halls = hall_nodes(layout)
    if not halls:
        return []
    lab, f = layout.labels, layout.floor
    hall = np.isin(lab, halls)
    seeds = hall & f.landing if f.landing is not None else np.zeros_like(hall)
    m = margin_ft / f.res
    for d in layout.doors:
        if d.run is None or not (d.a in halls or d.b in halls):
            continue
        for high in (True, False):
            seeds |= run_cells(lab.shape, d.run.vertical, d.run.k, d.t0 - m, d.t1 + m, high) & hall
    out = []
    rects = rectangles(hall)
    for r in rects:
        inr = cells(lab.shape, r)
        other = hall & ~inr
        touch = np.zeros_like(hall)                       # cells of r meeting the rest of the hall
        touch[:, 1:] |= other[:, :-1]
        touch[:, :-1] |= other[:, 1:]
        touch[1:, :] |= other[:-1, :]
        touch[:-1, :] |= other[1:, :]
        ax = along(r)
        pos = positions_hit(r, ax, (seeds | touch) & inr)
        if not len(pos):
            continue                                       # a piece of hall with nothing on it: left as is
        lo, hi = span(r, ax)
        a, b = int(pos.min()), int(pos.max()) + 1
        if a > lo:
            out.append((sub(r, ax, lo, a), ax, "hi"))
        if b < hi:
            out.append((sub(r, ax, b, hi), ax, "lo"))
    return out


def door_gaps(layout: FloorLayout, rules: SpaceRules) -> list[float]:
    """Distance (ft) from the stair landing to each bedroom door onto circulation (the vestibule, indicator)."""
    f = layout.floor
    if f.landing is None or not f.landing.any():
        return []
    rows, cols = np.nonzero(f.landing)
    px, py = cols + 0.5, rows + 0.5
    out = []
    for d in layout.doors:
        if d.run is None or d.a < 0 or d.b < 0:
            continue
        a, b = layout.specs[d.a], layout.specs[d.b]
        if not ((a.space_type in rules.sleeping_types and b.circulation)
                or (b.space_type in rules.sleeping_types and a.circulation)):
            continue
        along_, across = (py, px) if d.run.vertical else (px, py)
        da = np.maximum(0.0, np.maximum(d.t0 - along_, along_ - d.t1))
        gap = max(0.0, float(np.min(np.hypot(da, np.abs(across - d.run.k)))) - 0.5)
        out.append(round(gap * f.res, 2))
    return out


def dead_end_sqft(layout: FloorLayout, margin_ft: float) -> float:
    """Hall area beyond what it serves (indicator)."""
    ca = layout.floor.res ** 2
    return sum((r[1] - r[0]) * (r[3] - r[2]) for r, _, _ in remainders(layout, margin_ft)) * ca


# ------------------------------------------------------------------ the trim


class _Trim:
    def __init__(self, layout: FloorLayout, rules: SpaceRules, st: dict[str, Any]):
        self.layout, self.rules, self.st = layout, rules, st
        self.res = layout.floor.res
        self.ca = self.res * self.res
        self.labels = layout.labels.copy()
        self.specs = list(layout.specs)
        self.open_air = list(layout.open_air)
        self.report: dict[str, Any] = {"linen_sqft": 0.0, "closets": [], "roof_sqft": 0.0, "joined_sqft": 0.0,
                                       "kept_sqft": 0.0}
        self.count = 0

    def _cells(self, ft: float) -> int:
        return max(1, round(ft / self.res))

    def _add(self, spec: SpaceSpec, mask: np.ndarray) -> None:
        self.labels[mask] = len(self.specs)
        self.specs.append(spec)

    def _host_hall(self, mask: np.ndarray) -> SpaceSpec:
        vals = self.layout.labels[mask]
        vals = vals[vals >= 0]
        return self.specs[int(np.bincount(vals).argmax())]

    def linen(self, r, ax: str, inner: str):
        """The linen closet at the served end of a remainder; the rest of the remainder (None: nothing left)."""
        d = self._cells(self.st["linen_ft"])
        lo, hi = span(r, ax)
        if hi - lo < d:
            return r
        strip = sub(r, ax, hi - d, hi) if inner == "hi" else sub(r, ax, lo, lo + d)
        rest = sub(r, ax, lo, hi - d) if inner == "hi" else sub(r, ax, lo + d, hi)
        mask = cells(self.labels.shape, strip)
        area = int(mask.sum()) * self.ca
        if area < self.rules.closet_min_sqft - 1e-9:
            return r
        hall = self._host_hall(mask)
        self._add(_closet_spec(self.rules, hall, 0, area, "linen"), mask)
        self.report["linen_sqft"] += area
        return rest if span(rest, ax)[1] > span(rest, ax)[0] else None

    def _closet_for(self, r, ax: str, room: int) -> None:
        """A closet of `room` in r (against the wall away from it), a walk-in when r is wide, or r joins the room."""
        lab = self.labels
        a, b = sides(lab, r, ax)
        near_lo = int((a == room).sum()) >= int((b == room).sum())
        i0, i1, j0, j1 = r
        width = (j1 - j0) if ax == "x" else (i1 - i0)
        host = self.specs[room]
        mask = cells(lab.shape, r)
        area = int(mask.sum()) * self.ca
        if width * self.res + 1e-9 >= self.st["walk_in_ft"]:
            self.count += 1
            spec = SpaceSpec(f"{host.space_id}_walk_in{self.count}", WALK_IN, host.zone, host.unit_id, area,
                             self.rules.closet_min_sqft, self.rules.closet_min_side_ft, False, False, False,
                             frozenset(), host.space_id, False, True)
            self._add(spec, mask)
            self.report["closets"].append({"host": host.space_id, "kind": WALK_IN, "sqft": round(area, 1)})
            return
        d = self._cells(self.st["closet_ft"])
        if width - d >= 1:                                   # the closet against the far wall, the rest to the room
            if ax == "x":
                closet = (i0, i1, j1 - d, j1) if near_lo else (i0, i1, j0, j0 + d)
                joined = (i0, i1, j0, j1 - d) if near_lo else (i0, i1, j0 + d, j1)
            else:
                closet = (i1 - d, i1, j0, j1) if near_lo else (i0, i0 + d, j0, j1)
                joined = (i0, i1 - d, j0, j1) if near_lo else (i0 + d, i1, j0, j1)
        else:
            closet, joined = r, None
        cm = cells(lab.shape, closet)
        c_area = int(cm.sum()) * self.ca
        if c_area < self.rules.closet_min_sqft - 1e-9:
            lab[mask] = room
            self.report["joined_sqft"] += area
            return
        self.count += 1
        self._add(_closet_spec(self.rules, host, self.count, c_area, "closet"), cm)
        self.report["closets"].append({"host": host.space_id, "kind": "closet", "sqft": round(c_area, 1)})
        if joined is not None:
            jm = cells(lab.shape, joined)
            lab[jm] = room
            self.report["joined_sqft"] += int(jm.sum()) * self.ca

    def _roof(self, r) -> None:
        mask = cells(self.labels.shape, r)
        area = int(mask.sum()) * self.ca
        hall = self._host_hall(mask)
        self.count += 1
        spec = SpaceSpec(f"{hall.space_id}_roof{self.count}", ROOF_TYPE, hall.zone, hall.unit_id, area, 0.0, 0.0,
                         False, False, False, frozenset(), None, False, True)
        self.labels[mask] = OUT
        self.open_air.append((spec, mask))
        self.report["roof_sqft"] += area

    def piece(self, r, ax: str) -> None:
        lab, specs = self.labels, self.specs
        mask = cells(lab.shape, r)
        area = int(mask.sum()) * self.ca
        lo, hi = span(r, ax)
        if area < self.rules.closet_min_sqft - 1e-9 and hi - lo < 2:
            self.report["kept_sqft"] += area
            return
        sleeping = self.rules.sleeping_types
        a, b = sides(lab, r, ax)
        per = [{x for x in (int(a[p]), int(b[p])) if x >= 0 and specs[x].space_type in sleeping}
               for p in range(hi - lo)]
        beds = set().union(*per) if per else set()
        around = ring(lab, r)
        facade = bool((around == OUT).any())
        if len(beds) >= 2:
            split = None
            n = hi - lo
            for s in range(1, n):
                for x in beds:
                    for y in beds - {x}:
                        if all(x in per[p] for p in range(s)) and all(y in per[p] for p in range(s, n)):
                            cost = abs(s - n / 2)
                            if split is None or cost < split[0]:
                                split = (cost, s, x, y)
            if split is not None:
                _, s, x, y = split
                self._closet_for(sub(r, ax, lo, lo + s), ax, x)
                self._closet_for(sub(r, ax, lo + s, hi), ax, y)
                return
            room = max(beds, key=lambda k: sum(k in q for q in per))
            self._closet_for(r, ax, room)
            return
        if len(beds) == 1:
            room = next(iter(beds))
            if facade and self.st["one_room"] == ROOF and area >= self.st["roof_min_sqft"]:
                self._roof(r)
            else:
                self._closet_for(r, ax, room)
            return
        if facade and self.st["no_room"] == ROOF and area >= self.st["roof_min_sqft"]:
            self._roof(r)
            return
        others = [int(x) for x in around if x >= 0 and specs[int(x)].space_type not in (HALL_TYPE, "stair")
                  and not specs[int(x)].fixed]
        if not others:
            self.report["kept_sqft"] += area
            return
        k = int(np.bincount(others).argmax())
        lab[mask] = k
        self.report["joined_sqft"] += area


def stair_cover_closet(layout: FloorLayout, rules: SpaceRules) -> tuple[FloorLayout | None, dict[str, Any]]:
    """S2.2i: the covered start of the stair (cells the upper floor covers over the first treads, left with the stair
    when no unit could take them square) as a closet of the space it touches most (a room first, else the hall);
    a new layout without doors, or None."""
    cover = getattr(layout.floor, "stair_cover", None)
    if cover is None or not cover.any():
        return None, {}
    lab = layout.labels
    ca = layout.floor.res ** 2
    area = int(cover.sum()) * ca
    if area < rules.closet_min_sqft - 1e-9:
        return None, {"stair_cover_sqft": round(area, 1), "applied": False, "reason": "small"}
    ring_ = np.zeros_like(cover)
    ring_[:, 1:] |= cover[:, :-1]
    ring_[:, :-1] |= cover[:, 1:]
    ring_[1:, :] |= cover[:-1, :]
    ring_[:-1, :] |= cover[1:, :]
    ring_ &= ~cover
    near = [int(x) for x in lab[ring_] if x >= 0 and not layout.specs[int(x)].fixed
            and layout.specs[int(x)].space_type not in ("stair", HALL_TYPE, rules.closet_type, WALK_IN)
            and layout.specs[int(x)].space_type not in BATH_TYPES]          # S2.2j: no closet by a shower
    halls = [int(x) for x in lab[ring_] if x >= 0 and layout.specs[int(x)].space_type == HALL_TYPE]
    pool = near or halls
    if not pool:
        return None, {"stair_cover_sqft": round(area, 1), "applied": False, "reason": "no neighbour"}
    host = int(np.bincount(pool).argmax())
    labels = lab.copy()
    specs = list(layout.specs)
    labels[cover] = len(specs)
    specs.append(_closet_spec(rules, specs[host], 0, area, "stair_closet"))
    out = FloorLayout(layout.floor, layout.options, specs, labels, layout.root, layout.landing_node,
                      open_air=list(layout.open_air))
    return out, {"stair_cover_sqft": round(area, 1), "host": specs[host].space_id}


def trim_hall(layout: FloorLayout, rules: SpaceRules) -> tuple[FloorLayout | None, dict[str, Any]]:
    """The floor with its hall trimmed (no doors yet; None when there is nothing to trim) and the report."""
    st = trim_settings(rules)
    if st is None or layout.floor.level == 0:
        return None, {}
    pieces = remainders(layout, st["margin_ft"])
    if not pieces:
        return None, {"dead_end_sqft": 0.0}
    t = _Trim(layout, rules, st)
    ca = t.ca
    before = sum((r[1] - r[0]) * (r[3] - r[2]) for r, _, _ in pieces) * ca
    pieces = sorted(pieces, key=lambda p: -((p[0][1] - p[0][0]) * (p[0][3] - p[0][2])))
    has_linen = any(s.space_id.endswith("_linen") for s in layout.specs)
    for n, (r, ax, inner) in enumerate(pieces):
        if n == 0 and st["linen"] and not has_linen:
            r = t.linen(r, ax, inner)
            if r is None:
                continue
        t.piece(r, ax)
    halls = hall_nodes(layout)
    hall_before = float(np.isin(layout.labels, halls).sum()) * ca
    hall_after = float(np.isin(t.labels, halls).sum()) * ca
    report = {**t.report, "dead_end_before_sqft": round(before, 1), "hall_before_sqft": round(hall_before, 1),
              "hall_after_sqft": round(hall_after, 1)}
    for k in ("linen_sqft", "roof_sqft", "joined_sqft", "kept_sqft"):
        report[k] = round(report[k], 1)
    out = FloorLayout(layout.floor, layout.options, t.specs, t.labels, layout.root, layout.landing_node,
                      open_air=t.open_air)
    return out, report


__all__ = ["dead_end_sqft", "door_gaps", "hall_nodes", "remainders", "stair_cover_closet", "trim_hall", "trim_settings"]
