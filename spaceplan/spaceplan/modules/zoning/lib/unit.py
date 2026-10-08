"""Apartment unit: envelope polygon, facade roles and entrance (space-planning input, no capacity layer).

The access edge holding the entrance defines the local frame (front = corridor side), so the same
two-band zoning used for houses applies: the front band faces the corridor, the rear band the far side.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from shapely.geometry import LineString, Point, Polygon

from spaceplan.core.lib_aux.geometry import Frame, max_inscribed_rect, signed_area

ROLE_TO_FACADE_ROLES = {"access": ("access",), "exterior": ("exterior",), "party_wall": ("party_wall",)}
FACADE_MATCH_TOL_FT = 1.0
INTERIOR_ROLE = "interior"


class UnitGeometryError(ValueError):
    pass


@dataclass(frozen=True)
class UnitModel:
    polygon: Polygon
    frame: Frame
    rect_local: tuple[float, float, float, float]
    facade_roles: dict[str, frozenset[str]]
    entrance_interval: tuple[float, float]
    edges: tuple[dict, ...]

    @property
    def rect_area(self) -> float:
        x0, y0, x1, y1 = self.rect_local
        return (x1 - x0) * (y1 - y0)


def build_unit(spec: dict) -> UnitModel:
    vertices = [(float(x), float(y)) for x, y in spec["vertices"]]
    if signed_area(vertices) <= 0:
        raise UnitGeometryError("unit vertices must be counter-clockwise")
    n = len(vertices)
    edges = [{"edge_id": e["edge_id"], "role": e["role"], "start": vertices[i], "end": vertices[(i + 1) % n]}
             for i, e in enumerate(spec["edges"])]
    polygon = Polygon(vertices)
    if not polygon.is_valid:
        raise UnitGeometryError("unit polygon is not simple")
    entrance = spec["entrance"]
    door_edge = next(e for e in edges if e["edge_id"] == entrance["edge_id"])
    (ax, ay), (bx, by) = door_edge["start"], door_edge["end"]
    frame = Frame(origin=door_edge["start"], angle=math.atan2(by - ay, bx - ax))
    rect = max_inscribed_rect(polygon, frame)
    if rect is None:
        raise UnitGeometryError("no rectangle fits the unit")
    x0, y0, x1, y1 = frame.to_local(rect.polygon).bounds
    local_edges = [(e, frame.to_local(LineString([e["start"], e["end"]]))) for e in edges]
    mids = {"front": ((x0 + x1) / 2, y0), "rear": ((x0 + x1) / 2, y1),
            "left": (x0, (y0 + y1) / 2), "right": (x1, (y0 + y1) / 2)}
    roles = {}
    for facade, mid in mids.items():
        e, line = min(local_edges, key=lambda item: item[1].distance(Point(mid)))
        roles[facade] = frozenset(ROLE_TO_FACADE_ROLES[e["role"]]) if line.distance(Point(mid)) <= FACADE_MATCH_TOL_FT \
            else frozenset({INTERIOR_ROLE})
    length = math.dist(door_edge["start"], door_edge["end"])
    center = entrance["position"] * length
    half = entrance["width_ft"] / 2.0
    return UnitModel(polygon, frame, (x0, y0, x1, y1), roles, (center - half, center + half), tuple(edges))
