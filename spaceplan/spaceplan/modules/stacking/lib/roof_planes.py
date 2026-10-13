"""Roofs in several planes (step 6.7a S2.2g): the pieces of roof of a spaced two-floor house, each with its plate
height, its slope and its top.

    upper    the built upper floor (the upper polygon less its open bays and roof strips): the roof stage S1 kept
             (pitched with its ridge, or flat), on the upper wall plate
    lower    the ground floor built outside the upper floor (one-story parts, bays left as roof included), cut on the
             lines of the upper floor's sides (one piece per side, and the corners): a lean-to (shed) falling away
             from the upper wall it leans on, or a gable along its long side, or flat; on the ground wall plate, at
             the registry pitch
    garage   the garage outside the upper floor, the same way as a lower piece
    porch    the covered porches of stage S2.2g (open ends of the ground bands): a lean-to falling away from the
             house, or flat
Pieces smaller than min_piece_sqft are left out (counted in the summary). Unbuilt ends have no roof.

Polygons are in world coordinates; slopes are given as the high and low lines (a lean-to), the ridge line (a gable)
or none (flat). Every value comes from the design registry and the stacking catalog.
"""

from __future__ import annotations

from typing import Any

from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from spaceplan.modules.stacking.lib_aux.plan_geometry import polygon_json
from spaceplan.modules.stacking.lib_aux.roof_geometry import (
    fall,
    far_edge,
    leaning_edge,
    long_axis,
    parts,
    split_on,
)

SHED, GABLE, FLAT, PITCHED = "shed", "gable", "flat", "pitched"


def roof_settings(values: dict[str, Any]) -> dict[str, Any] | None:
    """Settings of the roof pieces (None when multi-plane roofs are off)."""
    if not values.get("structure.roofs.multi_plane"):
        return None
    return {"lower_kind": str(values["structure.roofs.lower_kind"]), "porch_kind": str(values["structure.roofs.porch_kind"]),
            "pitch": float(values["structure.roofs.lower_pitch"]), "min_piece": float(values["structure.roofs.min_piece_sqft"])}


def _line(ls, nd: int) -> list[list[float]]:
    return [[round(x, nd), round(y, nd)] for x, y in ls.coords]


def _lean_to(piece, wall, kind: str, pitch: float, plate: float, parapet: float, nd: int) -> dict[str, Any]:
    """A lean-to on `wall` (falling away from it), a gable along the long side, or flat."""
    if kind == FLAT or pitch <= 0.0:
        return {"kind": FLAT, "pitch": 0.0, "top_ft": round(plate + parapet, 3)}
    if kind == GABLE:
        direction, length, width = long_axis(piece)
        c = piece.centroid
        half = 0.5 * length
        ridge = [[round(c.x - direction[0] * half, nd), round(c.y - direction[1] * half, nd)],
                 [round(c.x + direction[0] * half, nd), round(c.y + direction[1] * half, nd)]]
        return {"kind": GABLE, "pitch": pitch, "ridge": ridge, "top_ft": round(plate + pitch * width / 2.0, 3)}
    edge = leaning_edge(piece, wall)
    if edge is None:                                     # free-standing: fall across the long side
        direction, _, _ = long_axis(piece)
        across = (-direction[1], direction[0])
        edge = far_edge(piece, (-across[0], -across[1]))
    down, depth = fall(piece, edge)
    return {"kind": SHED, "pitch": pitch, "high_line": _line(edge, nd), "low_line": _line(far_edge(piece, down), nd),
            "fall": [round(down[0], 4), round(down[1], 4)], "depth_ft": round(depth, 3),
            "top_ft": round(plate + pitch * depth, 3)}


def roof_pieces(s1: dict[str, Any], scat, st: dict[str, Any] | None, upper_open: list[BaseGeometry],
                porches: list[BaseGeometry], unbuilt: list[BaseGeometry], nd: int) -> dict[str, Any]:
    """The roof pieces of a spaced cell (world coordinates). `upper_open`: parts of the upper polygon left unbuilt
    (open bays, roof strips, terraces); `porches` / `unbuilt`: open ends of the ground bands."""
    levels = s1["levels"]
    ground = shape(levels[0]["polygon"])
    upper = shape(levels[1]["polygon"]) if len(levels) > 1 else None
    roof = s1.get("roof") or {}
    kept = scat.roof(roof.get("kept_roof_id") or scat.default_roof)
    flat = scat.roof(scat.flat_roof_id)
    parapet = float(flat.get("parapet_ft", 0.0))
    pieces: list[dict[str, Any]] = []
    dropped = 0.0
    built_up = upper.difference(unary_union(upper_open)) if upper is not None and upper_open else upper
    if built_up is not None and not built_up.is_empty:
        top = next((c["top_ft"] for c in roof.get("checks", []) if c["roof_id"] == kept["roof_id"]
                    and c.get("ridge") == roof.get("kept_ridge")), None)
        pieces.append({"piece": "upper", "kind": kept["kind"], "roof_id": kept["roof_id"],
                       "ridge": roof.get("kept_ridge"), "pitch": float(kept.get("pitch_rise_per_run", 0.0)),
                       "plate_ft": float(levels[-1]["wall_top_ft"]), "top_ft": top,
                       "area_sqft": round(built_up.area, 1), "polygon": polygon_json(built_up, nd)})
    if st is None:
        return {"multi_plane": False, "pieces": pieces}
    plate = float(levels[0]["wall_top_ft"])
    garage = shape(s1["ground"]["garage_polygon"]) if (s1.get("ground") or {}).get("garage_polygon") else None
    open_ground = unary_union([*porches, *unbuilt]) if (porches or unbuilt) else None
    built_ground = ground.difference(open_ground) if open_ground is not None else ground
    low = built_ground.difference(built_up) if built_up is not None else built_ground
    regions = [("lower", low.difference(garage) if garage is not None else low)]
    if garage is not None:
        regions.append(("garage", low.intersection(garage)))
    for name, geom in regions:
        pieces_of = split_on(geom, built_up) if built_up is not None and not built_up.is_empty else parts(geom)
        for p in pieces_of:
            if p.area < st["min_piece"]:
                dropped += p.area
                continue
            pieces.append({"piece": name, **_lean_to(p, built_up, st["lower_kind"], st["pitch"], plate, parapet, nd),
                           "plate_ft": plate, "area_sqft": round(p.area, 1), "polygon": polygon_json(p, nd)})
    for p in parts(unary_union(porches)) if porches else []:
        if p.area < st["min_piece"]:
            dropped += p.area
            continue
        pieces.append({"piece": "porch", **_lean_to(p, built_ground, st["porch_kind"], st["pitch"], plate, parapet,
                                                    nd),
                       "plate_ft": plate, "area_sqft": round(p.area, 1), "polygon": polygon_json(p, nd)})
    return {"multi_plane": True, "pieces": pieces, "planes": len(pieces),
            "area_by_piece": {k: round(sum(x["area_sqft"] for x in pieces if x["piece"] == k), 1)
                              for k in ("upper", "lower", "garage", "porch")},
            "dropped_sqft": round(dropped, 1)}


__all__ = ["FLAT", "GABLE", "PITCHED", "SHED", "roof_pieces", "roof_settings"]
