"""Polygonal extension, aware of the habitability rules (strategy B, polygonal mode).

The space level works on the core rectangle of every cell: adjacency, minimum sides (CRC habitable
dimension) and doors stay exact. The rest of the cell polygon, the slivers between the core and the
oblique lot lines, is handed out afterwards, piece by piece:

  1. A piece is the part of a sliver in front of one touching space (its y-range for a side sliver,
     its x-range for a front or rear sliver).
  2. Pieces thinner than min_piece_width_ft are not usable floor: they stay as residual (built-in
     storage, planting or wall thickness, decided in the architectural stage).
  3. Space types that tolerate an irregular outline (closets, storage, laundry, halls, open living
     areas) take their pieces.
  4. Rooms that need a regular outline (bedrooms, baths) take a piece only if the core stays the
     governing rectangle: the extension stays under habitable_max_extension_fraction of the core area
     and no corner sharper than min_corner_angle_deg appears.
  5. What a strict room refuses goes to a tolerant space touching the same sliver, else to residual.

Every decision is reported, so the drawing stage knows which rooms are trapezoids and why.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from shapely.geometry import box
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from spaceplan.core.lib_aux.geometry import polygon_parts

Rect = tuple[float, float, float, float]
_MIN_PIECE = 1e-6


@dataclass(frozen=True)
class ExtensionPolicy:
    tolerant_types: frozenset[str]
    min_piece_width: float
    max_fraction: float
    min_corner_angle: float


@dataclass(frozen=True)
class Member:
    rect: Rect
    space_type: str


def min_corner_angle(geom: BaseGeometry) -> float:
    """Smallest interior angle (degrees) of the largest polygon part; 180 for an empty geometry."""
    parts = polygon_parts(geom)
    if not parts:
        return 180.0
    poly = max(parts, key=lambda g: g.area).simplify(1e-6)
    pts = list(poly.exterior.coords)[:-1]
    n = len(pts)
    if n < 3:
        return 180.0
    ccw = poly.exterior.is_ccw
    best = 180.0
    for i in range(n):
        ax, ay = pts[i - 1]
        bx, by = pts[i]
        cx, cy = pts[(i + 1) % n]
        v1, v2 = (ax - bx, ay - by), (cx - bx, cy - by)
        cross = v1[0] * v2[1] - v1[1] * v2[0]
        dot = v1[0] * v2[0] + v1[1] * v2[1]
        ang = math.degrees(math.atan2(abs(cross), dot))
        convex = cross < 0 if ccw else cross > 0
        if not convex:
            ang = 360.0 - ang
        best = min(best, ang)
    return best


def _pieces(part: BaseGeometry, core_bounds, members: dict[str, Member]) -> list[tuple[str, BaseGeometry, float]]:
    """(member, piece, contact length) for every member touching the part, plus the unclaimed rest."""
    cx0, cy0, cx1, cy1 = core_bounds
    px0, py0, px1, py1 = part.bounds
    sideways = px1 <= cx0 + 1e-6 or px0 >= cx1 - 1e-6
    out, claimed = [], []
    for mid, m in members.items():
        x0, y0, x1, y1 = m.rect
        contact = box(x0, y0, x1, y1).buffer(1e-6).intersection(part.boundary).length
        if contact <= 1e-3:
            continue
        band = box(px0 - 1.0, y0, px1 + 1.0, y1) if sideways else box(x0, py0 - 1.0, x1, py1 + 1.0)
        piece = part.intersection(band)
        if piece.area > _MIN_PIECE:
            out.append((mid, piece, contact))
            claimed.append(piece)
    rest = part.difference(unary_union(claimed)) if claimed else part
    if rest.area > _MIN_PIECE:
        out.append(("", rest, 0.0))
    return out


def extend_members(cell: BaseGeometry, core: BaseGeometry, members: dict[str, Member], policy: ExtensionPolicy
                   ) -> tuple[dict[str, BaseGeometry], list[dict], list[dict]]:
    """Polygons of the members once the cell residual is distributed, the residual pieces, and the log."""
    polys = {mid: box(*m.rect) for mid, m in members.items()}
    residual: list[dict] = []
    log: list[dict] = []
    for part in polygon_parts(cell.difference(core)):
        if part.area < _MIN_PIECE:
            continue
        pieces = _pieces(part, core.bounds, members)
        tolerant_here = [mid for mid, _, _ in pieces if mid and members[mid].space_type in policy.tolerant_types]
        for mid, piece, contact in pieces:
            depth = piece.area / contact if contact > 1e-9 else 0.0
            target = None
            if not mid:
                decision = "unclaimed"
            elif depth < policy.min_piece_width - 1e-9:
                decision = "too_thin"
            elif members[mid].space_type in policy.tolerant_types:
                decision, target = "tolerant", mid
            else:
                core_area = box(*members[mid].rect).area
                grown = unary_union([polys[mid], piece])
                if grown.area - core_area > policy.max_fraction * core_area + 1e-9:
                    decision = "over_fraction"
                elif min_corner_angle(grown) < policy.min_corner_angle - 1e-9:
                    decision = "sharp_corner"
                else:
                    decision, target = "regular_room", mid
            if target is None and decision != "too_thin" and tolerant_here:
                target = max(tolerant_here, key=lambda t: box(*members[t].rect).area)
                decision = f"{decision}->tolerant_neighbour"
            if target is not None:
                parts = polygon_parts(unary_union([polys[target], piece]))
                if len(parts) == 1:
                    polys[target] = parts[0]
                else:  # touches only at a point: keep it as residual rather than split a room
                    target, decision = None, f"{decision}:disjoint"
            log.append({"space": mid or None, "area_sqft": piece.area, "mean_depth_ft": depth,
                        "decision": decision, "assigned_to": target})
            if target is None:
                residual.append({"near": mid or None, "area_sqft": piece.area, "geometry": piece,
                                 "reason": decision})
    return polys, residual, log


def policy_from_catalog(catalog_data: dict) -> ExtensionPolicy:
    p = catalog_data["polygonal_extension"]
    return ExtensionPolicy(frozenset(p["tolerant_space_types"]), p["min_piece_width_ft"],
                           p["habitable_max_extension_fraction"], p["min_corner_angle_deg"])


__all__ = ["ExtensionPolicy", "Member", "extend_members", "min_corner_angle", "policy_from_catalog"]
