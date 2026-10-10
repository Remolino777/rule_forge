"""Stair candidates of stage S1.2 (step 6.7a): U and L stairs against the permitted walls, from the main door.

For each strategy of the catalog (A side wall, D rear facade, C U around an interior void, B joint as the last
resort) the stair configurations of that strategy are placed against its walls with the same search as S1 (both
orientations, every direction and hand, positions along the whole wall) and filtered:

  door          the footprint or the half bath under it hits the door swing or the vestibule;
  circulation   the stair (and the void) cut off more than the catalog share of the free floor from the vestibule
                (ground) or from the arrival (upper);
  K06           no natural light where the client requires it (A, C, D).
Survivors are pre-ranked inside each strategy by occupied area, then by the distance from the vestibule to the
stair start; the best few of each strategy go on to S2, which zones them and measures the routes (client step 7).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any

from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from spaceplan.modules.stacking.lib.access_core import (
    NONE,
    EntryDoor,
    StairLight,
    Wall,
    free_cut_off,
    stair_light,
    well_of,
)
from spaceplan.modules.stacking.lib.stair import StairCandidate, StairShape, candidates, half_bath_spot

TOL = 1e-3
U_WELL = "u_well"


@dataclass(frozen=True)
class AccessCandidate:
    cand: StairCandidate
    strategy: str
    wall: Wall
    light: StairLight
    well: BaseGeometry | None
    occupied_sqft: float
    entry_ft: float
    stacked_ft: float
    fallback: bool

    @property
    def stair_id(self) -> str:
        return self.cand.shape.stair_id

    def summary(self) -> dict[str, Any]:
        return {"strategy": self.strategy, "stair_id": self.stair_id, "wall": self.wall.kind,
                "fire_separation_ft": None if self.wall.fire_separation_ft is None
                else round(self.wall.fire_separation_ft, 2),
                "light": self.light.source, "light_part": self.light.part, "openings": self.light.openings,
                "occupied_sqft": round(self.occupied_sqft, 1), "entry_ft": round(self.entry_ft, 2),
                "stacked_ft": round(self.stacked_ft, 2), "fallback": self.fallback,
                "void_sqft": round(self.well.area, 1) if self.well is not None else 0.0}


def _evaluate(c: StairCandidate, strategy: str, wall: Wall, walls: list[Wall], upper, ground, garage,
              door: EntryDoor, acc: dict[str, Any], stair_rs, required: dict[str, bool],
              fallback: bool) -> tuple[AccessCandidate | None, str | None]:
    fp = c.geom.footprint
    blocked = unary_union([door.swing, door.vestibule])
    if fp.intersection(blocked).area > TOL:
        return None, "door"
    if c.half_bath is not None:
        hb = unary_union([c.half_bath["half_bath"], c.half_bath["vestibule"]])
        if hb.intersection(blocked).area > TOL:
            return None, "door"
    well = well_of(c.geom, acc["void"]["well_ft"]) if c.shape.stair_id == U_WELL else None
    taken_g = fp if garage is None else unary_union([fp, garage])
    limit = acc["circulation"]["max_cut_off_fraction"]
    if free_cut_off(ground, taken_g, door.vestibule) > limit:
        return None, "circulation"
    taken_u = fp if well is None else unary_union([fp, well])
    if free_cut_off(upper, taken_u, c.top_zone) > limit:
        return None, "circulation"
    light = stair_light(c.geom, walls, stair_rs, acc["light"]["min_contact_ft"], well,
                        bool(acc["void"].get("skylight", False)))
    if required.get(strategy, False) and light.source == NONE:
        return None, "K06"
    net_ground = c.under["footprint_sqft"] - c.under["recovered_sqft"]
    occupied = net_ground + fp.area + (well.area if well is not None else 0.0)
    entry = door.vestibule.centroid.distance(c.bottom_zone.centroid)
    stacked = c.bottom_zone.centroid.distance(c.top_zone.centroid)
    return AccessCandidate(c, strategy, wall, light, well, occupied, entry, stacked, fallback), None


def _sub_line(line, bounds, window: float):
    """Piece of an axis-aligned wall around a placed footprint, `window` beyond each end (fine search)."""
    from shapely.geometry import LineString

    from spaceplan.modules.stacking.lib_aux.plan_geometry import is_axis_aligned

    (x0, y0), (x1, y1) = line.coords[0], line.coords[-1]
    bx0, by0, bx1, by1 = bounds
    if is_axis_aligned(line) == "x":
        lo, hi = sorted((x0, x1))
        a, b = max(lo, bx0 - window), min(hi, bx1 + window)
        return LineString([(a, y0), (b, y0)]) if b > a else None
    lo, hi = sorted((y0, y1))
    a, b = max(lo, by0 - window), min(hi, by1 + window)
    return LineString([(x0, a), (x0, b)]) if b > a else None


def _signature(c: StairCandidate) -> tuple:
    return (c.shape.stair_id, tuple(round(v, 2) for v in c.geom.footprint.bounds),
            tuple(round(v, 2) for v in c.bottom_zone.centroid.coords[0]))


def access_candidates(upper, ground, garage, door: EntryDoor, walls: list[Wall], shapes: dict[str, StairShape],
                      cfg: dict[str, Any], acc: dict[str, Any], stair_rs,
                      required: dict[str, bool]) -> tuple[list[AccessCandidate], Counter]:
    """Valid candidates of every strategy on one upper-floor placement, and the count of discards by cause.

    Two-level search per wall and configuration: every coarse step along the wall, then every fine step within
    the refine window of the best seeds (by occupied area, then distance to the vestibule). The half bath (a
    preference, client rule K09) is looked for afterwards, in the preselected candidates (`with_half_bath`)."""
    pos = acc["positions"]
    coarse = {**cfg, "step": float(pos["coarse_step_ft"]), "max_positions": int(pos["max_positions"]),
              "half_bath_trials": 0}             # the half bath is looked for after the preselection (K09)
    fine = {**coarse, "step": float(pos["fine_step_ft"])}
    stats: Counter = Counter()
    out: list[AccessCandidate] = []
    seen: set = set()

    def take(found, strategy, wall, fallback) -> list[AccessCandidate]:
        kept = []
        for c in found:
            sig = _signature(c)
            if sig in seen:
                continue
            seen.add(sig)
            stats[f"{strategy}:placed"] += 1
            a, why = _evaluate(c, strategy, wall, walls, upper, ground, garage, door, acc, stair_rs, required,
                               fallback)
            if a is None:
                stats[f"{strategy}:{why}"] += 1
            else:
                kept.append(a)
        return kept

    for strategy, spec in acc["strategies"].items():
        if strategy == "fallback_stair_ids":
            continue
        lines = [w for w in walls if w.kind in spec["walls"]]
        if not lines:
            stats[f"{strategy}:no_wall"] += 1
            continue
        for ids, fallback in ((spec["stair_ids"], False), (acc["strategies"]["fallback_stair_ids"], True)):
            if fallback and (strategy == "C" or any(a.strategy == strategy for a in out)):
                break
            for wall in lines:
                for sid in ids:
                    if sid not in shapes:
                        continue
                    shape = shapes[sid]
                    kept = take(candidates([shape], [wall.line], upper, ground, garage, coarse), strategy, wall,
                                fallback)
                    seeds = sorted(kept, key=lambda a: (round(a.occupied_sqft), a.entry_ft))[: int(pos["seeds_per_wall"])]
                    for seed in seeds:
                        sub = _sub_line(wall.line, seed.cand.geom.footprint.bounds, float(pos["refine_window_ft"]))
                        if sub is not None:
                            kept += take(candidates([shape], [sub], upper, ground, garage, fine), strategy, wall,
                                         fallback)
                    out += kept
    return out, stats


def preselect(cands: list[AccessCandidate], top_k: int) -> list[AccessCandidate]:
    """Few candidates of each strategy for S2: the least occupied, the nearest start to the vestibule, then other
    configurations (so a strategy offers its U and its L) and the half bath under the stair when one fits."""
    out = []
    for strategy in sorted({a.strategy for a in cands}):
        mine = [a for a in cands if a.strategy == strategy]
        orders = [sorted(mine, key=lambda a: (round(a.occupied_sqft), a.entry_ft, a.cand.key)),
                  sorted(mine, key=lambda a: (a.entry_ft, a.occupied_sqft, a.cand.key))]
        picked: list[AccessCandidate] = []

        def add(a):
            if a not in picked and len(picked) < top_k:
                picked.append(a)

        for order in orders:
            if order:
                add(order[0])
        for sid in sorted({a.stair_id for a in mine}):
            add(next(a for a in orders[0] if a.stair_id == sid))
        hb = [a for a in orders[0] if a.cand.half_bath is not None]
        if hb:
            add(hb[0])
        for a in orders[0]:
            add(a)
        out += picked
    return out


def with_half_bath(cands: list[AccessCandidate], ground, garage, door: EntryDoor,
                   cfg: dict[str, Any]) -> list[AccessCandidate]:
    """The same candidates with a vestibulated half bath under the stair where one fits clear of the main door
    (same search as S1.1)."""
    from dataclasses import replace

    no_garage = ground if garage is None else ground.difference(garage)
    blocked = unary_union([door.swing, door.vestibule])
    out = []
    for a in cands:
        c = a.cand
        free = no_garage.difference(c.geom.footprint).difference(c.bottom_zone).difference(blocked)
        hb = half_bath_spot(c.geom, cfg["half_bath_ft"], cfg["half_bath_sqft"], cfg["half_bath_side_ft"],
                            cfg["extension_ft"], free.union(c.bottom_zone), cfg["vestibule_ft"], cfg["step"])
        if hb is not None and unary_union([hb["half_bath"], hb["vestibule"]]).intersection(blocked).area > TOL:
            hb = None
        out.append(replace(a, cand=replace(c, half_bath=hb)) if hb is not None else a)
    return out


__all__ = ["AccessCandidate", "access_candidates", "preselect", "with_half_bath"]
