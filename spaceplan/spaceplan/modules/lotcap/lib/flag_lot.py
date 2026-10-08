"""Flag lots (step 6.6, PROVISIONAL reading of the SDMC).

A flag lot is a body behind an access strip (the "pole") that reaches the street. Until the SDMC
flag-lot definitions are verified, the pipeline reads it as follows:

* the dwelling is planned on the body; the body edge nearest the street acts as the front lot line,
  so the front setback is measured from it and the other body edges get side and rear setbacks;
* the access strip is a driveway outside the buildable area: it is reported as exterior paving and
  never enters the front-yard paving fraction (131.0447 is read on the body's front yard);
* the FAR applies to the body area by default (conservative); the full-lot reading is reported as an
  alternative so the decision can be checked against it.

The transform is pure: it returns a brief whose lot is the body plus a record of what was assumed.
"""

from __future__ import annotations

import copy
from typing import Any

from shapely.geometry import LineString, Polygon

from spaceplan.core.lib_aux.quantity import PROVISIONAL

AREA_TOL_FRACTION = 0.01


class FlagLotError(ValueError):
    pass


def _rotate(vertices: list, start: int) -> list:
    if not 0 <= start < len(vertices):
        raise FlagLotError(f"body_front_edge_index {start} out of range for {len(vertices)} body vertices")
    return [list(v) for v in vertices[start:] + vertices[:start]]


def _street_frontage(brief: dict, lot: Polygon) -> float:
    """Length of the original street edges (the strip mouth)."""
    verts = brief["lot"]["vertices"]
    n = len(verts)
    street_ids = set(brief["streets"][0]["frontage_edge_ids"])
    total = 0.0
    for i, edge in enumerate(brief["lot"]["edges"]):
        if edge["edge_id"] in street_ids:
            total += LineString([verts[i], verts[(i + 1) % n]]).length
    return total


def resolve_flag_lot(brief: dict) -> tuple[dict, dict[str, Any] | None]:
    """(body brief, flag record) for a flag lot; (brief, None) otherwise."""
    flag = brief.get("lot", {}).get("flag")
    if not flag:
        return brief, None
    lot = Polygon(brief["lot"]["vertices"])
    body = Polygon(flag["body_vertices"])
    strip = Polygon(flag["access_strip_vertices"])
    if not (lot.is_valid and body.is_valid and strip.is_valid):
        raise FlagLotError("flag lot polygons must be valid")
    tol = AREA_TOL_FRACTION * lot.area
    if body.intersection(strip).area > tol:
        raise FlagLotError("body and access strip overlap")
    if body.union(strip).symmetric_difference(lot).area > tol:
        raise FlagLotError("body + access strip must reproduce the lot polygon")

    verts = _rotate(flag["body_vertices"], flag["body_front_edge_index"])
    out = copy.deepcopy(brief)
    out["lot"] = {
        "vertices": verts,
        "edges": [{"edge_id": f"e{i}", "kind": "segment", "boundary_class": "front" if i == 0 else None,
                   "street_id": out["streets"][0]["street_id"] if i == 0 else None, "alley_width_ft": 0}
                  for i in range(len(verts))],
    }
    front = LineString([verts[0], verts[1]])
    mouth = front.project(strip.centroid) / front.length
    primary = out["streets"][0]
    primary["frontage_edge_ids"] = ["e0"]
    frontage = _street_frontage(brief, lot)
    if primary.get("curb_cut"):
        primary["curb_cut"] = {**primary["curb_cut"], "edge_id": "e0", "position": round(mouth, 4),
                               "width_ft": min(primary["curb_cut"]["width_ft"], frontage)}
    for other in out["streets"][1:]:
        other["frontage_edge_ids"] = []
    record = {
        "status": PROVISIONAL,
        "reading": "body planned as the lot; body edge nearest the street is the front line; access strip is "
                   "exterior paving outside the buildable area (SDMC flag-lot definitions pending)",
        "lot_area_sqft": round(lot.area, 1),
        "body_area_sqft": round(body.area, 1),
        "access_strip_area_sqft": round(strip.area, 1),
        "street_frontage_ft": round(frontage, 2),
        "far_area_basis": flag.get("far_area_basis", "body"),
    }
    return out, record


__all__ = ["FlagLotError", "resolve_flag_lot"]
