"""Layer 1 - site protodistribution (spaceplan v1.1 sections 5-7).

For each candidate number of floors the lot is partitioned into footprint, garden, side
yards and the front (driveway, walkway, entry deck, front green). Exterior zones come from
polygon differences in the front-aligned local frame, so any lot shape works. Access variants
(walkway independent or from the driveway; deck centered or offset) are evaluated and the best
compliant one is kept. Normative checks: front paving <= limit and vehicle count (131.0447),
deck projection (131.0461(a)(6)), footprint inside the setback envelope.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Any

from shapely.geometry import LineString, Point, box
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from spaceplan.core.lib.catalog import Catalog, site_parameters
from spaceplan.core.lib.enums import BoundaryClass, Strategy
from spaceplan.core.lib.rules import RuleSet
from spaceplan.core.lib_aux.geometry import Frame, clip_y, polygon_parts
from spaceplan.core.lib_aux.quantity import PROVISIONAL, VERIFIED, worst_status
from spaceplan.core.lib_aux.section import SectionProfile, profile_of_largest
from spaceplan.core.lib_aux.tolerances import AREA_TIE_TOL_SQFT, COVER_TOL_FT
from spaceplan.modules.lotcap.lib import rule_variants as rv
from spaceplan.modules.lotcap.lib.boundaries import BoundaryModel
from spaceplan.modules.lotcap.lib.capacity import CapacityResult, SetbackEvaluation
from spaceplan.modules.lotcap.lib.lot import Lot, chain_endpoints
from spaceplan.modules.site.lib.orientation import (
    boundary_exposures,
    exposure,
    facade_affinity,
    local_normal_azimuth,
)

WALKWAY_VARIANTS = ("independent", "from_driveway")
DECK_POSITIONS = ("centered", "offset")
DEFAULT_CURB_CUT_POSITION = 0.75
EMPTY = box(0, 0, 0, 0).buffer(0)
FACADE_NORMALS = {"front": (0.0, -1.0), "right": (1.0, 0.0), "rear": (0.0, 1.0), "left": (-1.0, 0.0)}


@dataclass(frozen=True)
class SiteContext:
    frame: Frame
    lot_local: BaseGeometry
    envelope_local: BaseGeometry
    rect_bounds: tuple[float, float, float, float] | None
    front_setback: float
    front_yard: BaseGeometry
    chord: float
    rear_y: float
    side_lines_local: list[BaseGeometry]
    street_side_lines_local: list[BaseGeometry]
    cars: int
    lanes: int
    curb_position: float
    walkway_width: float
    walkway_max_breaks: int
    driveway_width_per_car: float
    deck_area: dict[str, float]
    equipment_depth: float
    paving: dict
    porch: dict
    equipment: dict
    lot_area: float


def envelope_profile(envelope_local: BaseGeometry) -> SectionProfile:
    """Section profile of the (largest part of the) setback envelope in the local frame."""
    return profile_of_largest(envelope_local)


def garage_lanes(catalog: Catalog, program: dict) -> int:
    """Driveway lanes: one per car, unless the garage space type parks cars one behind the other (tandem)."""
    cars = program["garage_cars"]
    for s in program["spaces"]:
        if s["zone"] == "garage" and catalog.has_space_type(s.get("space_type")):
            lanes = catalog.space_type(s["space_type"]).get("lanes")
            if lanes:
                return min(int(lanes), cars)
    return cars


def _context(rs, catalog, brief, lot, boundaries, ev) -> SiteContext:
    frame = boundaries.frame
    lot_local = frame.to_local(lot.polygon)
    front_setback = ev.decisions["front"].value
    p0, p1 = chain_endpoints(lot, boundaries.front_edge_ids)
    rear_ys = [frame.point_to_local(lot.edge(i).chord_midpoint)[1] for i in boundaries.edges_of(BoundaryClass.REAR)]

    def lines(cls: str) -> list[BaseGeometry]:
        return [frame.to_local(LineString(lot.edge(i).points)) for i in boundaries.edges_of(cls)]

    street = boundaries.primary_street
    cut = street.get("curb_cut")
    deck = site_parameters(catalog, "entry_deck")
    walkway = site_parameters(catalog, "walkway")
    return SiteContext(
        frame=frame,
        lot_local=lot_local,
        envelope_local=frame.to_local(ev.envelope),
        rect_bounds=None,
        front_setback=front_setback,
        front_yard=clip_y(lot_local, y_max=front_setback),
        chord=((p1[0] - p0[0]) ** 2 + (p1[1] - p0[1]) ** 2) ** 0.5,
        rear_y=sum(rear_ys) / len(rear_ys),
        side_lines_local=lines(BoundaryClass.SIDE),
        street_side_lines_local=lines(BoundaryClass.STREET_SIDE),
        cars=brief["program"]["garage_cars"],
        lanes=garage_lanes(catalog, brief["program"]),
        curb_position=cut["position"] if cut else DEFAULT_CURB_CUT_POSITION,
        walkway_width=walkway["width_ft"],
        walkway_max_breaks=walkway["max_breaks"],
        driveway_width_per_car=site_parameters(catalog, "driveway")["width_per_car_ft"],
        deck_area={"min": deck["area_min"], "target": deck["area_target"]},
        equipment_depth=site_parameters(catalog, "side_yard")["equipment_depth_ft"],
        paving=rv.front_pavement_limits(rs),
        porch=rv.porch_projection_limit(rs, front_setback),
        equipment=rv.equipment_clearance(rs),
        lot_area=lot.polygon.area,
    )


# --------------------------------------------------------------------------- access layout


def _below_front(ctx: SiteContext, x0: float, x1: float, y_top: float) -> BaseGeometry:
    """Strip from the street up to y_top between x0 and x1, clipped to the lot."""
    if x1 <= x0 or y_top <= ctx.lot_local.bounds[1]:
        return EMPTY
    return box(x0, ctx.lot_local.bounds[1] - 1.0, x1, y_top).intersection(ctx.lot_local)


def access_layout(
    ctx: SiteContext, face: tuple[float, float, float], deck_position: str, walkway_variant: str
) -> dict[str, Any]:
    """Driveway, entry deck and walkway on the footprint's front face (x0, x1, y)."""
    fx0, fx1, fy0 = face
    layout: dict[str, Any] = {"deck_position": deck_position, "walkway_variant": walkway_variant}
    width = ctx.lanes * ctx.driveway_width_per_car
    segments = [(fx0, fx1)]
    driveway, shift, drive_x = None, 0.0, None
    if ctx.cars > 0:
        if fx1 - fx0 < width:
            return {**layout, "error": f"front face {fx1 - fx0:.1f} ft narrower than a {width:g} ft driveway"}
        wanted = ctx.curb_position * ctx.chord - width / 2.0
        x0 = min(max(wanted, fx0), fx1 - width)
        shift, drive_x = x0 - wanted, (x0, x0 + width)
        driveway = _below_front(ctx, x0, x0 + width, fy0)
        segments = [s for s in ((fx0, x0), (x0 + width, fx1)) if s[1] - s[0] > 1e-9]
    elif walkway_variant == "from_driveway":
        return {**layout, "error": "no driveway to branch from"}

    depth = ctx.porch["max_projection_ft"]
    if not segments:
        return {**layout, "error": "no front face left for the entry deck"}
    if deck_position == "offset" and drive_x is not None:
        candidates = [s for s in segments if abs(s[1] - drive_x[0]) < 1e-9 or abs(s[0] - drive_x[1]) < 1e-9]
        seg = max(candidates or segments, key=lambda s: s[1] - s[0])
    else:
        seg = max(segments, key=lambda s: s[1] - s[0])
    available = seg[1] - seg[0]
    deck_width = min(ctx.deck_area["target"] / depth, available)
    if deck_width * depth < ctx.deck_area["min"] - 1e-9 or deck_width < ctx.walkway_width:
        return {**layout, "error": f"front face segment {available:.1f} ft too short for the entry deck"}
    if deck_position == "offset" and drive_x is not None:
        dx0 = seg[1] - deck_width if abs(seg[1] - drive_x[0]) < 1e-9 else seg[0]
    elif deck_position == "offset":
        dx0 = seg[0]
    else:
        dx0 = 0.5 * (seg[0] + seg[1]) - deck_width / 2.0
    deck = box(dx0, fy0 - depth, dx0 + deck_width, fy0).intersection(ctx.lot_local)

    if walkway_variant == "independent":
        cx = dx0 + deck_width / 2.0
        walkway = _below_front(ctx, cx - ctx.walkway_width / 2.0, cx + ctx.walkway_width / 2.0, fy0 - depth)
        breaks = 0
    else:
        gx0, gx1 = (drive_x[1], dx0) if dx0 >= drive_x[1] else (dx0 + deck_width, drive_x[0])
        walkway = (
            box(gx0, fy0 - ctx.walkway_width, gx1, fy0).intersection(ctx.lot_local)
            if gx1 - gx0 > 1e-9 else EMPTY
        )
        breaks = 1
    paved = [g for g in (driveway, walkway) if g is not None]
    if ctx.paving["deck_counts"]:
        paved.append(deck)
    paved_area = unary_union(paved).intersection(ctx.front_yard).area if paved else 0.0
    without_deck = unary_union([g for g in (driveway, walkway) if g is not None])
    alt_area = without_deck.intersection(ctx.front_yard).area if driveway is not None or not walkway.is_empty else 0.0
    yard = ctx.front_yard.area
    front_region = clip_y(ctx.lot_local, y_max=fy0)
    green = front_region.difference(unary_union([g for g in (driveway, walkway, deck) if g is not None]))
    return {
        **layout,
        "error": None,
        "driveway": driveway,
        "driveway_interval_ft": list(drive_x) if drive_x else None,
        "driveway_shift_ft": shift,
        "deck": deck,
        "deck_depth_ft": depth,
        "deck_width_ft": deck_width,
        "deck_projection_ft": max(0.0, ctx.front_setback - (fy0 - depth)),
        "deck_interval_ft": [dx0, dx0 + deck_width],
        "walkway": walkway,
        "walkway_breaks": breaks,
        "front_green": green,
        "paving_fraction": paved_area / yard if yard else 0.0,
        "paving_fraction_without_deck": alt_area / yard if yard else 0.0,
        "paved_area_sqft": paved_area,
    }


# --------------------------------------------------------------------------- checks


def _check(check_id, kind, value, limit, passes, status, source, note=None) -> dict:
    return {"check_id": check_id, "kind": kind, "value": value, "limit": limit, "passes": passes,
            "status": status, "source": source, "note": note}


def layout_checks(ctx: SiteContext, layout: dict, footprint: BaseGeometry, envelope_status: str) -> list[dict]:
    pav, porch = ctx.paving, ctx.porch
    fraction = layout["paving_fraction"]
    paving_status = worst_status(pav["status"], pav["deck_status"]) if pav["deck_counts"] else pav["status"]
    checks = [
        _check("footprint_within_envelope", "normative", None, None,
               ctx.envelope_local.buffer(COVER_TOL_FT * 10).covers(footprint), envelope_status,
               "geometry:setback_envelope"),
        _check("front_paving_fraction", "normative", fraction, pav["max_fraction"],
               fraction <= pav["max_fraction"] + 1e-9, paving_status, pav["source"],
               f"without deck {layout['paving_fraction_without_deck']:.3f}"),
        _check("deck_projection", "normative", layout["deck_projection_ft"], porch["max_projection_ft"],
               layout["deck_projection_ft"] <= porch["max_projection_ft"] + 1e-9, porch["status"], porch["source"]),
        _check("deck_height", "deferred", None, porch["max_height_ft"], None, porch["status"], porch["source"],
               "verified in elevations (planogen / step 12)"),
        _check("deck_open_fraction", "deferred", None, porch["min_open_fraction"], None, porch["status"],
               porch["source"], "verified in elevations (planogen / step 12)"),
        _check("walkway_breaks", "design", layout["walkway_breaks"], ctx.walkway_max_breaks,
               layout["walkway_breaks"] <= ctx.walkway_max_breaks, PROVISIONAL, "catalog:walkway.max_breaks"),
    ]
    if ctx.lot_area < pav["vehicle_limit_lot_area_below_sqft"]:
        checks.append(_check("vehicle_count", "normative", ctx.cars, pav["vehicle_limit"],
                             ctx.cars <= pav["vehicle_limit"], pav["status"], pav["source"]))
    return checks


def paving_corrections(
    ctx: SiteContext, face: tuple[float, float, float], layout: dict, positions: list[str]
) -> list[str]:
    """Smallest changes that bring front paving under the limit (empty when it already complies)."""
    limit = ctx.paving["max_fraction"]
    if layout["paving_fraction"] <= limit + 1e-9:
        return []
    hints = []
    if ctx.paving["deck_counts"] and layout["paving_fraction_without_deck"] <= limit + 1e-9:
        hints.append(
            f"complies ({layout['paving_fraction_without_deck']:.0%}) if the entry deck does not count as paving "
            f"(131.0447 treatment pending)"
        )
    yard = ctx.front_yard.area
    other = layout["paved_area_sqft"] - (
        layout["driveway"].intersection(ctx.front_yard).area if layout["driveway"] is not None else 0.0
    )
    if ctx.cars > 0 and ctx.front_setback > 0:
        max_width = (limit * yard - other) / ctx.front_setback
        hints.append(f"driveway width at most {max_width:.1f} ft in the front yard (now "
                     f"{ctx.lanes * ctx.driveway_width_per_car:g} ft)")
    for cars in range(ctx.cars - 1, -1, -1):
        trial = replace(ctx, cars=cars, lanes=min(ctx.lanes, cars))
        fractions = [
            access_layout(trial, face, pos, wv)
            for wv in WALKWAY_VARIANTS for pos in positions
        ]
        fractions = [f["paving_fraction"] for f in fractions if not f["error"]]
        if fractions and min(fractions) <= limit + 1e-9:
            hints.append(f"complies ({min(fractions):.0%}) with a {cars}-car driveway")
            break
    return hints


def _normative_ok(checks: list[dict]) -> bool:
    return all(c["passes"] for c in checks if c["kind"] == "normative")


# --------------------------------------------------------------------------- facades


def _facades(ctx: SiteContext, fp: tuple[float, float, float, float], brief: dict, model: dict,
             shoulders: bool = False) -> list[dict]:
    x0, y0, x1, y1 = fp
    north, lat = brief["orientation"]["north_azimuth_deg"], brief["orientation"]["latitude_deg"]
    mids = {"front": (0.5 * (x0 + x1), y0), "rear": (0.5 * (x0 + x1), y1),
            "left": (x0, 0.5 * (y0 + y1)), "right": (x1, 0.5 * (y0 + y1))}
    lengths = {"front": x1 - x0, "rear": x1 - x0, "left": y1 - y0, "right": y1 - y0}
    rows = []
    for fid, (nx, ny) in FACADE_NORMALS.items():
        if fid == "front":
            faces, street = "front_yard", 1.0
        elif fid == "rear":
            faces, street = "garden", 0.0
        else:
            mid = Point(mids[fid])
            nearest_street = min((ln.distance(mid) for ln in ctx.street_side_lines_local), default=float("inf"))
            nearest_side = min((ln.distance(mid) for ln in ctx.side_lines_local), default=float("inf"))
            street = 1.0 if nearest_street < nearest_side else 0.0
            faces = "street_side_yard" if street else "side_yard"
        az = local_normal_azimuth(ctx.frame, nx, ny, north)
        rows.append({"facade_id": fid, "length_ft": lengths[fid], "azimuth_deg": az, "faces": faces,
                     **exposure(az, lat, model), "street_exposure": street,
                     "garden": 1.0 if fid == "rear" else 0.0})
    if shoulders:
        # strategy B: set-back faces of a wider step look the same way as the front / rear facades;
        # their length is only known once the zones are realized
        for fid, parent in (("front_shoulder", "front"), ("rear_shoulder", "rear")):
            base = next(r for r in rows if r["facade_id"] == parent)
            rows.append({**base, "facade_id": fid, "length_ft": 0.0, "faces": fid,
                         "street_exposure": 0.5 * base["street_exposure"], "garden": 0.5 * base["garden"]})
    return rows


# --------------------------------------------------------------------------- options


def _world(ctx: SiteContext, geom: BaseGeometry | None):
    if geom is None or geom.is_empty:
        return None
    parts = polygon_parts(geom)
    if not parts:
        return None
    return ctx.frame.to_world(geom)


def footprint_variants(ctx: SiteContext, area: float, positions: list[str]) -> list[tuple[str, float, float]]:
    """Full strategy-A width, plus a narrower footprint that leaves equipment room on one side.

    The reserved side is the one away from the driveway; the variant is kept only if the deeper
    footprint still fits the rectangle.
    """
    rx0, ry0, rx1, ry1 = ctx.rect_bounds
    variants = [("full_width", rx0, rx1)]
    need = ctx.equipment["min_distance_to_line_ft"] + ctx.equipment_depth
    full = box(rx0, ry0, rx1, ry0 + area / (rx1 - rx0))
    drive_center = ctx.curb_position * ctx.chord if ctx.cars > 0 else rx1
    side = "left" if drive_center >= 0.5 * (rx0 + rx1) else "right"
    face_x = rx0 if side == "left" else rx1
    lines = [ln for ln in ctx.side_lines_local
             if ln.distance(Point(face_x, full.centroid.y)) < ln.distance(Point(rx0 + rx1 - face_x, full.centroid.y))]
    if not lines:
        return variants
    shrink = need - min(ln.distance(full) for ln in lines)
    if shrink <= 1e-9:
        return variants
    nx0, nx1 = (rx0 + shrink, rx1) if side == "left" else (rx0, rx1 - shrink)
    if nx1 - nx0 > 0 and area / (nx1 - nx0) <= ry1 - ry0 + 1e-9:
        variants.append((f"equipment_room_{side}", nx0, nx1))
    return variants


def _evaluate_footprint(ctx, fp_bounds, floors, prefs, positions, env_status, footprint=None,
                        face=None) -> dict | None:
    """Access variants, checks and exterior zones of one footprint (a rectangle, or a given geometry whose
    front face is face = (x0, x1, y))."""
    footprint = box(*fp_bounds) if footprint is None else footprint
    fx0, fy0, fx1, fy1 = fp_bounds
    face = face or (fx0, fx1, fy0)
    evaluated, best = [], None
    compliant: dict[tuple, tuple] = {}
    for walkway_variant in WALKWAY_VARIANTS:
        for position in positions:
            layout = access_layout(ctx, face, position, walkway_variant)
            if layout["error"]:
                evaluated.append({"walkway_variant": walkway_variant, "deck_position": position,
                                  "paving_fraction": None, "normative_ok": False, "error": layout["error"]})
                continue
            checks = layout_checks(ctx, layout, footprint, env_status)
            ok = _normative_ok(checks)
            evaluated.append({"walkway_variant": walkway_variant, "deck_position": position,
                              "paving_fraction": layout["paving_fraction"], "normative_ok": ok, "error": None})
            key = (not ok, round(layout["paving_fraction"], 6), layout["walkway_breaks"],
                   WALKWAY_VARIANTS.index(walkway_variant), DECK_POSITIONS.index(position))
            if best is None or key < best[0]:
                best = (key, layout, checks)
            deck_key = (position, tuple(round(v, 6) for v in layout["deck_interval_ft"]))
            if ok and (deck_key not in compliant or key < compliant[deck_key][0]):
                compliant[deck_key] = (key, layout)
    if best is None:
        return None
    key, layout, checks = best
    garden = clip_y(ctx.lot_local, y_min=fy1)
    side_yards = clip_y(ctx.lot_local, y_min=fy0, y_max=fy1).difference(footprint)
    garden_depth = ctx.rear_y - fy1
    min_garden, min_depth = prefs.get("min_garden_area_sqft"), prefs.get("min_garden_depth_ft")
    if min_garden is not None:
        checks.append(_check("garden_area", "preference", garden.area, min_garden,
                             garden.area >= min_garden - 1e-6, VERIFIED, "brief:preferences.min_garden_area_sqft"))
    if min_depth is not None:
        checks.append(_check("garden_depth", "preference", garden_depth, min_depth,
                             garden_depth >= min_depth - 1e-6, VERIFIED, "brief:preferences.min_garden_depth_ft"))
    if prefs.get("max_floors") is not None:
        checks.append(_check("max_floors", "preference", floors, prefs["max_floors"],
                             floors <= prefs["max_floors"], VERIFIED, "brief:preferences.max_floors"))
    lines = ctx.side_lines_local or ctx.street_side_lines_local
    clearance = max((ln.distance(footprint) for ln in lines), default=0.0)
    room = clearance - ctx.equipment["min_distance_to_line_ft"]
    equipment_ok = room >= ctx.equipment_depth - 1e-9
    checks.append(_check("side_yard_equipment_room", "info", room, ctx.equipment_depth, equipment_ok,
                         ctx.equipment["status"], ctx.equipment["source"],
                         f"widest side clearance {clearance:.2f} ft; equipment must stay "
                         f"{ctx.equipment['min_distance_to_line_ft']:g} ft from the lot line"))
    access_options = [{"deck_position": k[0], "deck_interval_ft": list(k[1]),
                       "driveway_interval_ft": v[1]["driveway_interval_ft"], "paving_fraction": v[1]["paving_fraction"],
                       "walkway_variant": v[1]["walkway_variant"]} for k, v in sorted(compliant.items())]
    return {"key": key, "layout": layout, "checks": checks, "evaluated": evaluated, "fp_bounds": fp_bounds,
            "face": face,
            "access_options": access_options,
            "footprint": footprint, "garden": garden, "side_yards": side_yards, "garden_depth": garden_depth,
            "clearance": clearance, "equipment_ok": equipment_ok,
            "prefs_ok": all(c["passes"] for c in checks if c["kind"] == "preference")}


def _fill_option(option, ctx, chosen, fp_variant, candidates_out, positions, brief, catalog, model, area,
                 shoulders: bool = False) -> None:
    """Write the chosen footprint candidate (access, checks, exterior zones, facades) into the option."""
    fp_bounds, layout, checks = chosen["fp_bounds"], chosen["layout"], chosen["checks"]
    footprint, garden, side_yards = chosen["footprint"], chosen["garden"], chosen["side_yards"]
    garden_depth, clearance = chosen["garden_depth"], chosen["clearance"]
    option["variants_evaluated"] = chosen["evaluated"]
    option["footprint_variant"] = fp_variant
    option["footprint_candidates"] = candidates_out
    option["corrections"] = paving_corrections(ctx, chosen["face"], layout, positions)

    facades = _facades(ctx, fp_bounds, brief, model, shoulders)
    green_parts = [p for p in polygon_parts(layout["front_green"]) if p.area > 1.0]
    option.update(
        feasible=_normative_ok(checks),
        preferences_met=all(c["passes"] for c in checks if c["kind"] == "preference"),
        footprint_width_ft=fp_bounds[2] - fp_bounds[0],
        footprint_depth_ft=fp_bounds[3] - fp_bounds[1],
        coverage_ratio=area / ctx.lot_area,
        zones={
            "footprint": {"area_sqft": footprint.area, "polygon": _world(ctx, footprint)},
            "garden": {"area_sqft": garden.area, "depth_ft": garden_depth, "polygon": _world(ctx, garden)},
            "side_yards": {"area_sqft": side_yards.area, "clearance_ft": clearance, "polygon": _world(ctx, side_yards)},
            "front_green": {"area_sqft": layout["front_green"].area, "parts": len(green_parts),
                            "polygon": _world(ctx, layout["front_green"])},
            "driveway": {"area_sqft": layout["driveway"].area if layout["driveway"] is not None else 0.0,
                         "polygon": _world(ctx, layout["driveway"])},
            "walkway": {"area_sqft": layout["walkway"].area, "polygon": _world(ctx, layout["walkway"])},
            "entry_deck": {"area_sqft": layout["deck"].area, "polygon": _world(ctx, layout["deck"])},
        },
        front_yard_area_sqft=ctx.front_yard.area,
        access={
            "walkway_variant": layout["walkway_variant"],
            "deck_position": layout["deck_position"],
            "walkway_breaks": layout["walkway_breaks"],
            "deck_width_ft": layout["deck_width_ft"],
            "deck_depth_ft": layout["deck_depth_ft"],
            "deck_interval_ft": layout["deck_interval_ft"],
            "deck_visible_from_street": True,
            "deck_afternoon_shade": next(f["afternoon_shade"] for f in facades if f["facade_id"] == "front"),
            "driveway_interval_ft": layout["driveway_interval_ft"],
            "driveway_shift_ft": layout["driveway_shift_ft"],
            "garage_face_constraint": (
                None if layout["driveway_interval_ft"] is None
                else "garage must occupy the front facade over driveway_interval_ft (local x)"
            ),
        },
        checks=checks,
        facades=facades,
        zone_facade_affinity=facade_affinity(catalog, facades),
    )


def _option(ctx, floors, required, gross_max, footprint_norm, brief, catalog, model, env_status) -> dict:
    prefs = brief["preferences"]
    area = required / floors
    option: dict[str, Any] = {"option_id": f"n{floors}", "floors": floors, "footprint_area_sqft": area,
                              "feasible": False, "preferences_met": False, "reasons": []}
    if required > gross_max + AREA_TIE_TOL_SQFT:
        option["reasons"].append(f"required gross {required:.0f} exceeds FAR limit {gross_max:.0f}")
    if area > footprint_norm + AREA_TIE_TOL_SQFT:
        option["reasons"].append(f"footprint {area:.0f} exceeds normative footprint {footprint_norm:.0f}")
    if ctx.rect_bounds is None:
        option["reasons"].append("no realizable rectangle (strategy A)")
    else:
        rx0, ry0, rx1, ry1 = ctx.rect_bounds
        if area / (rx1 - rx0) > ry1 - ry0 + 1e-9:
            option["reasons"].append(
                f"footprint depth {area / (rx1 - rx0):.1f} ft exceeds strategy A depth {ry1 - ry0:.1f} ft (realization)")
    if option["reasons"]:
        return option

    positions = [prefs.get("deck_position")] if prefs.get("deck_position") in DECK_POSITIONS else list(DECK_POSITIONS)
    best = None
    candidates_out = []
    for fp_variant, fx0, fx1 in footprint_variants(ctx, area, positions):
        candidate = _evaluate_footprint(ctx, (fx0, ry0, fx1, ry0 + area / (fx1 - fx0)), floors, prefs,
                                        positions, env_status)
        if candidate is None:
            continue
        candidates_out.append({
            "footprint_variant": fp_variant,
            "rect_local": list(candidate["fp_bounds"]),
            "normative_ok": not candidate["key"][0],
            "preferences_met": candidate["prefs_ok"],
            "intervals": {"entry_deck": candidate["layout"]["deck_interval_ft"],
                          "driveway": candidate["layout"]["driveway_interval_ft"]},
            "access_options": candidate["access_options"],
        })
        key = (candidate["key"][0], not candidate["prefs_ok"], not candidate["equipment_ok"], *candidate["key"][1:])
        if best is None or key < best[0]:
            best = (key, fp_variant, candidate)
    if best is None:
        option["reasons"].append("no access layout fits the front face")
        return option
    _, fp_variant, chosen = best
    _fill_option(option, ctx, chosen, fp_variant, candidates_out, positions, brief, catalog, model, area)
    return option


def _option_b(ctx, floors, required, gross_max, footprint_norm, brief, catalog, model, env_status,
              profile: SectionProfile, y_front: float, recess: float, strategy_name: str, mode: str,
              steps: int = 2) -> dict:
    """Strategy B: the front face is the envelope section at the front line (plus any recess).

    The footprint shape depends on the zone areas, so the site checks use a nominal footprint: the
    envelope slab from the front line holding the footprint area. Zoning realizes the real steps or
    slabs later and reports their garden, shoulders and polygonal reserve.
    """
    prefs = brief["preferences"]
    area = required / floors
    option: dict[str, Any] = {"option_id": f"n{floors}", "floors": floors, "footprint_area_sqft": area,
                              "feasible": False, "preferences_met": False, "reasons": []}
    if required > gross_max + AREA_TIE_TOL_SQFT:
        option["reasons"].append(f"required gross {required:.0f} exceeds FAR limit {gross_max:.0f}")
    if area > footprint_norm + AREA_TIE_TOL_SQFT:
        option["reasons"].append(f"footprint {area:.0f} exceeds normative footprint {footprint_norm:.0f}")
    if y_front >= profile.ymax:
        option["reasons"].append(f"front line {y_front:.1f} ft is behind the envelope")
        return option
    held = profile.strip_area(y_front, profile.ymax) if mode == "polygonal" else profile.best_steps(y_front, steps)[0]
    if area > held + AREA_TIE_TOL_SQFT:
        option["reasons"].append(
            f"footprint {area:.0f} sq ft exceeds what {strategy_name} holds behind the front line ({held:.0f})")
    if option["reasons"]:
        return option
    depth = profile.depth_for_area(y_front, area, "polygonal")
    nominal = clip_y(ctx.envelope_local, y_min=y_front, y_max=y_front + depth)
    xl, xr = profile.interval(y_front)
    nb = nominal.bounds
    fp_bounds = (nb[0], y_front, nb[2], y_front + depth)
    positions = [prefs.get("deck_position")] if prefs.get("deck_position") in DECK_POSITIONS else list(DECK_POSITIONS)
    chosen = _evaluate_footprint(ctx, fp_bounds, floors, prefs, positions, env_status, nominal, (xl, xr, y_front))
    if chosen is None:
        option["reasons"].append("no access layout fits the front face")
        return option
    variant = f"{'stepped' if mode == 'rectangle' else 'polygonal'}/recess_{recess:g}"
    candidates_out = [{
        "footprint_variant": variant,
        "rect_local": [xl, y_front, xr, y_front + depth],
        "normative_ok": not chosen["key"][0],
        "preferences_met": chosen["prefs_ok"],
        "intervals": {"entry_deck": chosen["layout"]["deck_interval_ft"],
                      "driveway": chosen["layout"]["driveway_interval_ft"]},
        "access_options": chosen["access_options"],
        "realization": {"strategy": strategy_name, "y_front": y_front, "recess_ft": recess,
                        "front_width_ft": xr - xl, "nominal": "envelope slab holding the footprint area"},
    }]
    _fill_option(option, ctx, chosen, variant, candidates_out, positions, brief, catalog, model, area, shoulders=True)
    return option


def site_context(rs: RuleSet, catalog: Catalog, brief: dict, lot: Lot, boundaries: BoundaryModel,
                 ev: SetbackEvaluation, capacity: CapacityResult) -> SiteContext:
    """Site context of a lot, reusable across programs (step 6.6 measures many footprints on it)."""
    ctx = _context(rs, catalog, brief, lot, boundaries, ev)
    rect = capacity.realizable[0]["polygon"]
    if rect is not None:
        ctx = replace(ctx, rect_bounds=tuple(boundaries.frame.to_local(rect).bounds))
    return ctx


def front_yard_area(ctx: SiteContext) -> float:
    """Front yard area (sq ft) of a site context (public accessor used by the area analysis)."""
    return ctx.front_yard.area


def measure_footprint(ctx: SiteContext, catalog: Catalog, brief: dict, program: dict, strategy_name: str,
                      footprint_area: float, floors: int, footprint_norm: float, env_status: str,
                      steps: int = 2) -> dict[str, Any]:
    """Stage E1 of the area analysis: access, paving and garden of a given ground footprint.

    The FAR is checked by the caller (it depends on the gross-area variant); here only the site checks
    of layer 1 run, with the garage lanes of the program being evaluated."""
    ctx = replace(ctx, cars=program.get("garage_cars", 0), lanes=garage_lanes(catalog, program))
    model = catalog.data["orientation_model"]
    required = footprint_area * floors
    if strategy_name == Strategy.A_INSCRIBED_RECTANGLE.value:
        option = _option(ctx, floors, required, math.inf, footprint_norm, brief, catalog, model, env_status)
    else:
        profile = envelope_profile(ctx.envelope_local)
        mode = "polygonal" if strategy_name == Strategy.B_POLYGONAL_FOOTPRINT.value else "rectangle"
        option = _option_b(ctx, floors, required, math.inf, footprint_norm, brief, catalog, model, env_status,
                           profile, profile.ymin, 0.0, strategy_name, mode, steps)
    zones = option.get("zones") or {}

    def zone_area(name: str) -> float:
        z = zones.get(name)
        return float(z["area_sqft"]) if z else 0.0

    failed = [c["check_id"] for c in option.get("checks", []) if c["kind"] == "normative" and not c["passes"]]
    paving = next((c["value"] for c in option.get("checks", []) if c["check_id"] == "front_paving_fraction"), None)
    return {
        "feasible": bool(option["feasible"]),
        "reasons": list(option["reasons"]),
        "failed_checks": failed,
        "garden_sqft": round(zone_area("garden"), 1),
        "garden_depth_ft": round((zones.get("garden") or {}).get("depth_ft", 0.0), 2),
        "paving_sqft": round(zone_area("driveway") + zone_area("walkway"), 1),
        "deck_sqft": round(zone_area("entry_deck"), 1),
        "side_yards_sqft": round(zone_area("side_yards"), 1),
        "front_paving_fraction": None if paving is None else round(paving, 4),
    }


def build_site_partition(
    rs: RuleSet,
    catalog: Catalog,
    brief: dict,
    lot: Lot,
    boundaries: BoundaryModel,
    ev: SetbackEvaluation,
    capacity: CapacityResult,
    strategy_name: str = Strategy.A_INSCRIBED_RECTANGLE.value,
    front_recess: float = 0.0,
) -> tuple[dict, list[str]]:
    """Site options per number of floors.

    strategy_name selects how the footprint is realized (A: inscribed rectangle; B: stepped or polygonal
    footprint from the front line); front_recess moves the B front line behind the front setback.
    """
    model = catalog.data["orientation_model"]
    ctx = _context(rs, catalog, brief, lot, boundaries, ev)
    rect = capacity.realizable[0]["polygon"]
    if rect is not None:
        ctx = replace(ctx, rect_bounds=tuple(boundaries.frame.to_local(rect).bounds))
    cap = capacity.capacity
    required = cap["required_gross_area"].value
    floors_height = int(cap["floors_max_height"].value)
    env_status = cap["envelope"]["area"].status
    if strategy_name == Strategy.A_INSCRIBED_RECTANGLE.value:
        options = [
            _option(ctx, n, required, cap["gross_area_max"].value, cap["footprint_max_normative"].value,
                    brief, catalog, model, env_status)
            for n in range(1, floors_height + 1)
        ]
    else:
        profile = envelope_profile(ctx.envelope_local)
        mode = "polygonal" if strategy_name == Strategy.B_POLYGONAL_FOOTPRINT.value else "rectangle"
        options = [
            _option_b(ctx, n, required, cap["gross_area_max"].value, cap["footprint_max_normative"].value,
                      brief, catalog, model, env_status, profile, profile.ymin + front_recess, front_recess,
                      strategy_name, mode)
            for n in range(1, floors_height + 1)
        ]
    chosen = next((o for o in options if o["feasible"] and o["preferences_met"]), None)
    chosen = chosen or next((o for o in options if o["feasible"]), None)
    warnings = []
    if chosen is None:
        warnings.append("site partition: no option satisfies the normative site checks")
    elif not chosen["preferences_met"]:
        warnings.append(f"site partition: option {chosen['option_id']} is compliant but misses client preferences")
    for o in options:
        for c in o.get("checks", []):
            if c["check_id"] == "front_paving_fraction" and not c["passes"]:
                warnings.append(f"option {o['option_id']}: front paving {c['value']:.0%} > {c['limit']:.0%} (131.0447)")
    street = boundaries.primary_street
    partition = {
        "frame": {"origin": list(ctx.frame.origin), "angle_rad": ctx.frame.angle},
        "streets": [
            {"street_id": s["street_id"], "role": s["role"], "street_type": s["street_type"],
             "noise_level": s["noise_level"], "curb_cut": s["curb_cut"], "grade_offset_ft": s["grade_offset_ft"]}
            for s in brief["streets"]
        ],
        "front_yard_area_sqft": ctx.front_yard.area,
        "orientation": {
            "latitude_deg": brief["orientation"]["latitude_deg"],
            "north_azimuth_deg": brief["orientation"]["north_azimuth_deg"],
            "boundaries": boundary_exposures(lot, boundaries, brief, model),
        },
        "limits": {
            "max_paving_fraction": ctx.paving["max_fraction"],
            "deck_counts_as_paving": ctx.paving["deck_counts"],
            "deck_max_projection_ft": ctx.porch["max_projection_ft"],
            "deck_max_height_ft": ctx.porch["max_height_ft"],
            "deck_min_open_fraction": ctx.porch["min_open_fraction"],
            "equipment_min_distance_ft": ctx.equipment["min_distance_to_line_ft"],
        },
        "options": options,
        "strategy": strategy_name,
        "front_recess_ft": front_recess,
        "selected_option_id": chosen["option_id"] if chosen else None,
        "primary_street_id": street["street_id"],
    }
    return partition, warnings


# Public interface of the site module (refactor tanda 3): other modules use only these names.
__all__ = ["DECK_POSITIONS", "WALKWAY_VARIANTS", "SiteContext", "access_layout", "build_site_partition",
           "envelope_profile", "footprint_variants", "front_yard_area", "garage_lanes", "layout_checks",
           "measure_footprint", "paving_corrections", "site_context"]
