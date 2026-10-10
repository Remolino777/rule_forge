"""The stair as an object (step 6.7a, stages S1 and S1.1): configurations, ends, the space under it and the choice
of configuration, direction and position at the joint.

Configurations (catalog `stair.types`): straight (one flight), straight with a mid landing, L-turn and U-turn with a
landing. Risers: the fewest equal risers at or below the maximum riser (S01) for the floor-to-floor height; treads at
the design depth (>= S02); width and landing at the design values (>= S03, S05). The footprint is the flights and the
intermediate landing; the floor at each end is the arrival zone of a receiving space (client rules K01, K02), not part
of the stair. The same footprint is the stair on the ground floor and its opening in the upper floor.

Clear height under the stair = nosing line - structure depth: bands (low, storage, half bath) tell how much of the
ground-floor footprint is recovered and whether a vestibulated half bath fits under the high end.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from shapely.geometry import box
from shapely.geometry.base import BaseGeometry
from shapely.prepared import prep

from spaceplan.modules.stacking.lib.stair_rules import StairLimits
from spaceplan.modules.stacking.lib_aux.plan_geometry import overlap_area, rects_along_line
from spaceplan.modules.stacking.lib_aux.stair_geometry import (
    ALIGNS,
    End,
    Part,
    StairGeometry,
    band_area,
    band_rect,
    extend_rect,
    place,
    transforms_for,
    zone_beyond,
)

INCH_FT = 1.0 / 12.0
TOL = 1e-3


@dataclass(frozen=True)
class StairShape:
    """One configuration for a floor-to-floor height, in its own frame (bounding box length x span)."""

    stair_id: str
    risers: int
    riser_ft: float
    treads: int
    tread_ft: float
    width_ft: float
    landing_ft: float
    length_ft: float
    span_ft: float
    area_sqft: float
    max_flight_rise_ft: float
    geometry: StairGeometry

    def to_dict(self) -> dict[str, Any]:
        return {"stair_id": self.stair_id, "risers": self.risers, "riser_in": round(self.riser_ft / INCH_FT, 3),
                "treads": self.treads, "tread_in": round(self.tread_ft / INCH_FT, 3),
                "width_ft": round(self.width_ft, 3), "landing_ft": round(self.landing_ft, 3),
                "length_ft": round(self.length_ft, 3), "span_ft": round(self.span_ft, 3),
                "area_sqft": round(self.area_sqft, 2),
                "max_flight_rise_in": round(self.max_flight_rise_ft / INCH_FT, 3)}


def risers_for(floor_to_floor_ft: float, riser_max_ft: float) -> int:
    return max(1, math.ceil(floor_to_floor_ft / riser_max_ft - 1e-9))


def _flight(rect, axis, sign, origin, base_h, r, t, depth) -> Part:
    """Under a flight that starts at height base_h: nosing line base_h + r (1 + s / t), minus the structure."""
    return Part("flight", rect, axis, sign, origin, base_h + r - depth, r / t)


def _landing(rect, h, depth) -> Part:
    return Part("landing", rect, "u", 1, 0.0, h - depth, 0.0)


def stair_shape(stair_type: dict[str, Any], floor_to_floor_ft: float, limits: StairLimits,
                design: dict[str, Any]) -> StairShape:
    n = risers_for(floor_to_floor_ft, limits.riser_max_ft)
    r = floor_to_floor_ft / n
    t = max(design["tread_in"] * INCH_FT, limits.tread_min_ft)
    w = max(design["width_ft"], limits.width_min_ft)
    ld = max(design["landing_ft"], limits.landing_min_ft, w)
    d = design.get("structure_depth_ft", 0.0)
    sid = stair_type["stair_id"]
    if sid == "straight":
        run = (n - 1) * t
        parts = (_flight((0, 0, run, w), "u", 1, 0.0, 0.0, r, t, d),)
        bottom, top = End(((0, 0), (0, w)), (-1, 0)), End(((run, 0), (run, w)), (1, 0))
        treads, flight_rise = n - 1, n * r
    else:
        r1 = math.ceil(n / 2)
        t1, t2 = (r1 - 1) * t, (n - r1 - 1) * t
        h_land = r1 * r
        treads, flight_rise = (r1 - 1) + (n - r1 - 1), max(r1, n - r1) * r
        f1 = _flight((0, 0, t1, w), "u", 1, 0.0, 0.0, r, t, d)
        if sid == "straight_landing":
            parts = (f1, _landing((t1, 0, t1 + ld, w), h_land, d),
                     _flight((t1 + ld, 0, t1 + ld + t2, w), "u", 1, t1 + ld, h_land, r, t, d))
            bottom, top = End(((0, 0), (0, w)), (-1, 0)), End(((t1 + ld + t2, 0), (t1 + ld + t2, w)), (1, 0))
        elif sid == "l_turn":
            parts = (f1, _landing((t1, 0, t1 + w, w), h_land, d),
                     _flight((t1, w, t1 + w, w + t2), "v", 1, w, h_land, r, t, d))
            bottom, top = End(((0, 0), (0, w)), (-1, 0)), End(((t1, w + t2), (t1 + w, w + t2)), (0, 1))
        elif sid == "u_turn":
            gap = design.get("u_turn_gap_ft", 0.0)
            span = 2 * w + gap
            parts = (f1, _landing((t1, 0, t1 + ld, span), h_land, d),
                     _flight((t1 - t2, w + gap, t1, span), "u", -1, t1, h_land, r, t, d))
            bottom, top = End(((0, 0), (0, w)), (-1, 0)), End(((t1 - t2, w + gap), (t1 - t2, span)), (-1, 0))
        else:
            raise ValueError(f"unknown stair type {sid!r}")
    geom = StairGeometry(parts, bottom, top)
    x0, y0, x1, y1 = geom.bounds
    return StairShape(sid, n, r, treads, t, w, ld, x1 - x0, y1 - y0, geom.footprint.area, flight_rise, geom)


# ------------------------------------------------------------------ under the stair


def under_stair(geom: StairGeometry, storage_ft: float, half_bath_ft: float) -> dict[str, Any]:
    """Areas of the clear-height bands under a placed stair."""
    total = geom.footprint.area
    return {"footprint_sqft": total,
            "low_sqft": band_area(geom, -1e9, storage_ft),
            "storage_sqft": band_area(geom, storage_ft, half_bath_ft),
            "half_bath_band_sqft": band_area(geom, half_bath_ft),
            "recovered_sqft": band_area(geom, storage_ft)}


def half_bath_spot(geom: StairGeometry, half_bath_ft: float, need_sqft: float, min_side_ft: float,
                   extension_max_ft: float, free: BaseGeometry, vestibule_ft: float, step: float):
    """A half bath under the high end of the last flight (extended beyond the stair end if needed) with a vestibule
    square beside it; None when it does not fit. `free` is the ground floor available outside the stair."""
    top_flight = [p for p in geom.parts if p.kind == "flight"][-1]
    rect = band_rect(top_flight, half_bath_ft)
    if rect is None:
        return None
    w, h = rect[2] - rect[0], rect[3] - rect[1]
    across, along = (h, w) if top_flight.axis == "x" else (w, h)
    if across < min_side_ft - TOL:
        return None
    extra = max(0.0, need_sqft / across - along)
    if extra > extension_max_ft + TOL:
        return None
    hb_rect = extend_rect(rect, top_flight.axis, top_flight.sign, extra)
    hb = box(*hb_rect)
    beyond = hb.difference(box(*rect))
    if beyond.area > TOL and not free.buffer(TOL).contains(beyond):
        return None
    room = free.difference(hb)
    for edge in _edges(hb_rect):
        for placed in rects_along_line(edge, vestibule_ft, vestibule_ft, step, room):
            return {"half_bath": hb, "vestibule": placed.rect, "extension_ft": extra,
                    "ascent_axis": top_flight.axis, "ascent_sign": top_flight.sign}
    return None


def _edges(rect):
    from shapely.geometry import LineString

    x0, y0, x1, y1 = rect
    return [LineString([(x0, y0), (x1, y0)]), LineString([(x1, y0), (x1, y1)]),
            LineString([(x0, y1), (x1, y1)]), LineString([(x0, y0), (x0, y1)])]


# ------------------------------------------------------------------ candidates and choice


@dataclass(frozen=True)
class StairCandidate:
    shape: StairShape
    geom: StairGeometry
    joint_index: int
    offset_ft: float
    bottom_zone: Any
    top_zone: Any
    under: dict[str, Any]
    half_bath: dict[str, Any] | None
    entry_distance_ft: float
    key: tuple


def _first_zone(end, depth, width, holder, footprint):
    for align in ALIGNS:
        z = zone_beyond(end, depth, width, align)
        if holder.contains(z) and overlap_area(z, footprint) <= TOL:
            return z
    return None


def _key(cfg, net, hb_fit, entry, offset, rect_bounds, sid) -> tuple:
    parts = {"net_ground_bucket": math.floor(net / cfg["bucket_sqft"] + 1e-9), "half_bath_fit": 0 if hb_fit else 1,
             "entry_distance_ft": round(entry), "joint_offset_ft": round(offset, 3)}
    return tuple(parts[k] for k in cfg["choice"]) + (rect_bounds, sid)


def candidates(shapes: list[StairShape], joints: list, upper: BaseGeometry, ground: BaseGeometry,
               garage: BaseGeometry | None, cfg: dict[str, Any]) -> list[StairCandidate]:
    """Valid placements of every configuration against the joints, each with its choice key.

    Phase 1 keeps the placements whose footprint lies in both floors out of the garage and whose arrival zones fit.
    Phase 2 looks for a vestibulated half bath under the stair only in the best `half_bath_trials` placements of
    each configuration (by the key without the half bath), which is where the choice is made."""
    no_garage = ground if garage is None else ground.difference(garage)
    inside = upper.intersection(no_garage)   # positions are searched out of the garage before they are capped
    in_both, in_upper, in_ground = prep(inside.buffer(TOL)), prep(upper.buffer(TOL)), prep(no_garage.buffer(TOL))
    garage_p = prep(garage) if garage is not None and not garage.is_empty else None
    raw: dict[str, list] = {}
    for shape in shapes:
        size = (shape.length_ft, shape.span_ft)
        under = under_stair(shape.geometry, cfg["storage_ft"], cfg["half_bath_ft"])
        net = under["footprint_sqft"] - under["recovered_sqft"]
        for orient in ((size[0], size[1]), (size[1], size[0])):
            for j, joint in enumerate(joints):
                placed = rects_along_line(joint, orient[0], orient[1], cfg["step"], inside)[: cfg["max_positions"]]
                for p in placed:
                    for m in transforms_for(size, p.rect.bounds):
                        g = place(shape.geometry, size, m, p.rect.bounds)
                        fp = g.footprint
                        if not in_both.contains(fp) or (garage_p is not None and garage_p.intersects(fp)
                                                         and overlap_area(fp, garage) > TOL):
                            continue
                        bz = _first_zone(g.bottom, cfg["landing_ft"], shape.width_ft, in_ground, fp)
                        if bz is None:
                            continue
                        tz = _first_zone(g.top, cfg["top_depth_ft"], cfg["top_width_ft"], in_upper, fp)
                        if tz is None:
                            continue
                        entry = bz.centroid.y - ground.bounds[1]
                        raw.setdefault(shape.stair_id, []).append(
                            (_key(cfg, net, True, entry, p.offset_ft, p.rect.bounds, shape.stair_id),
                             shape, g, j, p.offset_ft, bz, tz, under, entry))
    out = []
    for items in raw.values():
        items.sort(key=lambda it: it[0])
        for k, (_, shape, g, j, offset, bz, tz, under, entry) in enumerate(items):
            hb = None
            if k < cfg["half_bath_trials"]:
                free = no_garage.difference(g.footprint).difference(bz)
                hb = half_bath_spot(g, cfg["half_bath_ft"], cfg["half_bath_sqft"], cfg["half_bath_side_ft"],
                                    cfg["extension_ft"], free.union(bz), cfg["vestibule_ft"], cfg["step"])
            net = under["footprint_sqft"] - under["recovered_sqft"]
            key = _key(cfg, net, hb is not None, entry, offset, items[k][0][-2], shape.stair_id)
            out.append(StairCandidate(shape, g, j, offset, bz, tz, under, hb, entry, key))
    return out


def choose(cands: list[StairCandidate]) -> StairCandidate | None:
    return min(cands, key=lambda c: c.key) if cands else None


def best_by_type(cands: list[StairCandidate]) -> dict[str, StairCandidate]:
    best: dict[str, StairCandidate] = {}
    for c in cands:
        b = best.get(c.shape.stair_id)
        if b is None or c.key < b.key:
            best[c.shape.stair_id] = c
    return best


__all__ = ["StairCandidate", "StairShape", "best_by_type", "candidates", "choose", "half_bath_spot", "risers_for",
           "stair_shape", "under_stair"]
