"""Access core of stage S1.2 (step 6.7a): main door, swing, vestibule, permitted walls and the light of the stair.

Client definition (2026-10-10), in order:
  0. the street facade of the ground floor (its front edge in the lot frame);
  1. the main door on it, centred on the site's entry deck measured from the driveway (the garage side follows the
     driveway), with its clear width and an inward swing hinged on the side nearer a wall;
  2. a vestibule behind the door (fixed object; the circulation zone opens onto it in S2);
  4. stair candidates against the permitted walls (exterior side and rear walls of the ground floor that continue on
     the upper floor; the joint only as the last resort), by strategy A side wall, D rear facade, C interior void
     (U around a void under a skylight), B centre;
  5. candidates that hit the door swing, the vestibule or cut the free floor off the vestibule are discarded (no
     structure yet);
  6. light: a window on the landing (else a flight) where CRC Table R302.1 allows openings (rule S13, unverified), or
     the skylight of the void; client rule K06 requires it for A, C and D. The code's artificial light (S12) is
     always required and traced apart (RuleForge two-layer rule).
Comparison by occupied area and route length (step 7) happens after S2 has zoned each candidate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from shapely.geometry import LineString, Point, box
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from spaceplan.modules.stacking.lib_aux.plan_geometry import is_axis_aligned, joint_lines, lines_of, segments_of

TOL = 1e-3
IN_PER_FT = 12.0                     # unit conversion
SIDE, REAR, FRONT, JOINT = "side", "rear", "front", "joint"
WINDOW, SKYLIGHT, NONE = "window", "skylight", "none"
OPENINGS_RULE, LIGHTING_RULE = "S13-EXTERIOR-WALL-OPENINGS", "S12-STAIR-LIGHTING"


# ------------------------------------------------------------------ site: garage side and entry deck


def site_entry(site_plan: dict[str, Any]) -> dict[str, Any]:
    """Garage side and entry-deck interval (measured from the inner edge of the driveway) of the first feasible
    site option."""
    options = site_plan["site_partition"]["options"]
    opt = next((o for o in options if o.get("feasible")), options[0])
    zones = opt["zones"]

    def xs(name):
        poly = (zones.get(name) or {}).get("polygon")
        if not poly:
            return None
        pts = [p[0] for p in poly["coordinates"][0]]
        return min(pts), max(pts)

    deck, drive = xs("entry_deck"), xs("driveway")
    if deck is None:
        return {"garage_side": None, "deck_offset_ft": None, "option_id": opt.get("option_id")}
    if drive is None:
        return {"garage_side": None, "deck_offset_ft": (0.0, deck[1] - deck[0]), "option_id": opt.get("option_id")}
    right = (drive[0] + drive[1]) > (deck[0] + deck[1])
    edge = drive[0] if right else drive[1]
    near, far = sorted((abs(edge - deck[0]), abs(edge - deck[1])))
    return {"garage_side": "right" if right else "left", "deck_offset_ft": (near, far),
            "option_id": opt.get("option_id")}


# ------------------------------------------------------------------ door, swing, vestibule


@dataclass(frozen=True)
class EntryDoor:
    segment: LineString
    hinge: tuple[float, float]
    swing: BaseGeometry
    vestibule: BaseGeometry
    notes: tuple[str, ...] = ()


def entry_door(ground: BaseGeometry, garage: BaseGeometry | None, garage_side: str | None,
               deck_offset: tuple[float, float] | None, cfg: dict[str, Any]) -> EntryDoor | None:
    """Main door on the street facade (front edge of the ground floor), its inward swing and the vestibule."""
    x0, y0, x1, y1 = ground.bounds
    width = cfg["door"]["clear_width_in"] / IN_PER_FT
    vw, vd = cfg["vestibule"]["width_ft"], cfg["vestibule"]["depth_ft"]
    lo, hi = x0, x1
    if garage is not None and not garage.is_empty:
        gx0, _, gx1, _ = garage.bounds
        lo, hi = (x0, gx0) if garage_side != "left" else (gx1, x1)
    notes = []
    if hi - lo < max(width, vw) - TOL:
        return None
    if deck_offset is not None and garage is not None and not garage.is_empty:
        mid = 0.5 * (deck_offset[0] + deck_offset[1])
        xc = hi - mid if garage_side != "left" else lo + mid
    else:
        xc = 0.5 * (lo + hi)
        notes.append("no entry deck: door centred on the free front")
    half = max(width, vw) / 2.0
    xc = min(max(xc, lo + half), hi - half)
    segment = LineString([(xc - width / 2, y0), (xc + width / 2, y0)])
    hinge_x = xc - width / 2 if (xc - lo) <= (hi - xc) else xc + width / 2
    swing = Point(hinge_x, y0).buffer(width).intersection(box(min(hinge_x, xc - width / 2), y0,
                                                              max(hinge_x, xc + width / 2), y0 + width))
    vestibule = box(xc - vw / 2, y0, xc + vw / 2, y0 + vd).intersection(ground)
    return EntryDoor(segment, (hinge_x, y0), swing, vestibule, tuple(notes))


# ------------------------------------------------------------------ permitted walls


@dataclass(frozen=True)
class Wall:
    line: LineString
    kind: str                      # side / rear / joint
    fire_separation_ft: float | None


def fire_separation_ft(wall: LineString, ground: BaseGeometry, lot: BaseGeometry, samples=(0.1, 0.5, 0.9),
                       reach_ft: float = 1000.0) -> float | None:
    """Fire separation distance of an exterior wall: measured at right angles to its face, from points along it, to
    the lot line it faces (the least of the samples). The nearest point of the lot would give 0 ft for any wall whose
    end meets a side lot line."""
    (x0, y0), (x1, y1) = wall.coords[0], wall.coords[-1]
    length = wall.length or 1.0
    nx, ny = (y1 - y0) / length, -(x1 - x0) / length          # a unit normal; flipped below to point outside
    mid = wall.interpolate(0.5, normalized=True)
    probe = 10 * TOL                                          # a point just off the face, to tell inside from outside
    if ground.contains(Point(mid.x + nx * probe, mid.y + ny * probe)):
        nx, ny = -nx, -ny
    best = None
    for f in samples:
        p = wall.interpolate(f, normalized=True)
        ray = LineString([(p.x, p.y), (p.x + nx * reach_ft, p.y + ny * reach_ft)])
        hit = ray.intersection(lot.exterior)
        if hit.is_empty:
            continue
        d = p.distance(hit)
        best = d if best is None else min(best, d)
    return best


def _common_exterior(ground: BaseGeometry, upper: BaseGeometry) -> list[LineString]:
    shared = ground.boundary.intersection(upper.boundary.buffer(TOL)).intersection(ground.boundary)
    return [s for line in lines_of(shared, 10 * TOL) for s in segments_of(line)]


def permitted_walls(ground: BaseGeometry, upper: BaseGeometry, garage: BaseGeometry | None, lot: BaseGeometry,
                    cfg: dict[str, Any]) -> list[Wall]:
    """Exterior walls common to both floors (side or rear, never the street facade nor the garage wall), with the
    distance to the nearest lot line, plus the joint as the last resort."""
    x0, y0, x1, y1 = ground.bounds
    walls = []
    garage_edge = garage.boundary.buffer(TOL) if garage is not None and not garage.is_empty else None
    for seg in _common_exterior(ground, upper):
        if garage_edge is not None:
            seg_parts = lines_of(seg.difference(garage_edge), 10 * TOL)
        else:
            seg_parts = [seg]
        for part in seg_parts:
            axis = is_axis_aligned(part)
            if axis == "y":
                kind = SIDE
            elif axis == "x":
                mid_y = part.coords[0][1]
                kind = REAR if abs(mid_y - y1) <= abs(mid_y - y0) else FRONT
            else:
                kind = SIDE
            if kind in cfg["walls"]["excluded"] or kind not in cfg["walls"]["permitted"]:
                continue
            walls.append(Wall(part, kind, fire_separation_ft(part, ground, lot)))
    if JOINT in cfg["walls"]["fallback"]:
        walls += [Wall(j, JOINT, None) for j in joint_lines(upper, ground)]
    return walls


def openings_allowed(stair_rs, fire_separation_ft: float | None) -> str:
    """'none', 'limited' or 'unlimited' by rule S13 (CRC Table R302.1, unverified)."""
    if fire_separation_ft is None:
        return "none"
    p = stair_rs.params(OPENINGS_RULE)
    if fire_separation_ft < p["not_permitted_below_ft"]:
        return "none"
    return "limited" if fire_separation_ft < p["unlimited_from_ft"] else "unlimited"


# ------------------------------------------------------------------ light of a placed stair


@dataclass(frozen=True)
class StairLight:
    source: str                    # window / skylight / none
    part: str | None               # landing / flight
    wall_kind: str | None
    openings: str | None
    contact_ft: float = 0.0


def stair_light(geom, walls: list[Wall], stair_rs, min_contact_ft: float, well: BaseGeometry | None,
                skylight: bool = False) -> StairLight:
    """Window on the landing, else on a flight, along an exterior wall that may have openings; else the skylight of
    the void when the catalog allows one (no skylight since 2026-10-10); else none."""
    for kind in ("landing", "flight"):
        best = None
        for part in (p for p in geom.parts if p.kind == kind):
            rect = box(*part.rect) if not hasattr(part.rect, "bounds") else part.rect
            for w in walls:
                if w.kind == JOINT:
                    continue
                allowed = openings_allowed(stair_rs, w.fire_separation_ft)
                if allowed == "none":
                    continue
                contact = rect.boundary.intersection(w.line.buffer(TOL)).length
                if contact >= min_contact_ft - TOL and (best is None or contact > best.contact_ft):
                    best = StairLight(WINDOW, kind, w.kind, allowed, round(contact, 2))
        if best is not None:
            return best
    if skylight and well is not None and not well.is_empty:
        return StairLight(SKYLIGHT, None, None, None)
    return StairLight(NONE, None, None, None)


def free_cut_off(floor: BaseGeometry, taken: BaseGeometry, anchor: BaseGeometry) -> float:
    """Share of the free floor (floor minus `taken`) not connected to the piece that holds the anchor."""
    free = floor.difference(taken)
    parts = [free] if free.geom_type == "Polygon" else list(getattr(free, "geoms", []))
    total = sum(p.area for p in parts) or 1.0
    holder = max((p for p in parts if p.buffer(TOL).intersects(anchor)), key=lambda p: p.area, default=None)
    return 1.0 - (holder.area / total if holder is not None else 0.0)


def well_of(geom, min_side_ft: float) -> BaseGeometry | None:
    """The void between the flights of a U: the pieces of the bounding box outside the footprint whose shorter side
    reaches the well width (the notch left by a shorter second flight is not a void), or None."""
    x0, y0, x1, y1 = geom.bounds
    rest = box(x0, y0, x1, y1).difference(geom.footprint)
    pieces = [rest] if rest.geom_type == "Polygon" else list(getattr(rest, "geoms", []))

    def short_side(p):
        bx0, by0, bx1, by1 = p.bounds
        return min(bx1 - bx0, by1 - by0)

    pieces = [p for p in pieces if p.area > TOL and short_side(p) >= min_side_ft - TOL]
    return unary_union(pieces) if pieces else None


__all__ = ["FRONT", "JOINT", "LIGHTING_RULE", "NONE", "OPENINGS_RULE", "REAR", "SIDE", "SKYLIGHT", "WINDOW",
           "EntryDoor", "StairLight", "Wall", "entry_door", "fire_separation_ft", "free_cut_off", "openings_allowed", "permitted_walls",
           "site_entry", "stair_light", "well_of"]
