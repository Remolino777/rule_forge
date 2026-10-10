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
from spaceplan.modules.stacking.lib.stair import StairCandidate, StairShape, candidates

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
    light = stair_light(c.geom, walls, stair_rs, acc["light"]["min_contact_ft"], well)
    if required.get(strategy, False) and light.source == NONE:
        return None, "K06"
    net_ground = c.under["footprint_sqft"] - c.under["recovered_sqft"]
    occupied = net_ground + fp.area + (well.area if well is not None else 0.0)
    entry = door.vestibule.centroid.distance(c.bottom_zone.centroid)
    stacked = c.bottom_zone.centroid.distance(c.top_zone.centroid)
    return AccessCandidate(c, strategy, wall, light, well, occupied, entry, stacked, fallback), None


def access_candidates(upper, ground, garage, door: EntryDoor, walls: list[Wall], shapes: dict[str, StairShape],
                      cfg: dict[str, Any], acc: dict[str, Any], stair_rs,
                      required: dict[str, bool]) -> tuple[list[AccessCandidate], Counter]:
    """Valid candidates of every strategy on one upper-floor placement, and the count of discards by cause."""
    stats: Counter = Counter()
    out: list[AccessCandidate] = []
    search = {**cfg, "max_positions": int(acc["positions"]["max_positions"])}
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
            chosen = [shapes[sid] for sid in ids if sid in shapes]
            found = candidates(chosen, [w.line for w in lines], upper, ground, garage, search)
            stats[f"{strategy}:placed"] += len(found)
            for c in found:
                a, why = _evaluate(c, strategy, lines[c.joint_index], walls, upper, ground, garage, door, acc,
                                   stair_rs, required, fallback)
                if a is None:
                    stats[f"{strategy}:{why}"] += 1
                else:
                    out.append(a)
    return out, stats


def preselect(cands: list[AccessCandidate], top_k: int) -> list[AccessCandidate]:
    """Best few of each strategy by occupied area, then distance from the vestibule to the start (distinct
    stair configurations first, so a strategy offers its U and its L when both fit)."""
    out = []
    for strategy in sorted({a.strategy for a in cands}):
        mine = sorted((a for a in cands if a.strategy == strategy),
                      key=lambda a: (round(a.occupied_sqft), round(a.entry_ft, 1), a.cand.key))
        picked, seen = [], set()
        for a in mine:
            if a.stair_id not in seen:
                picked.append(a)
                seen.add(a.stair_id)
            if len(picked) >= top_k:
                break
        for a in mine:
            if len(picked) >= top_k:
                break
            if a not in picked:
                picked.append(a)
        out += picked
    return out


__all__ = ["AccessCandidate", "access_candidates", "preselect"]
