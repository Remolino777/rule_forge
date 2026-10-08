"""Lot model: edges (segments or arcs), polygon and the front-aligned frame."""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass

from shapely.geometry import Polygon

from spaceplan.lib_aux.geometry import (
    Frame,
    Point,
    discretize_arc,
    is_convex,
    midpoint,
    outward_bearing_deg,
    polyline_length,
    signed_area,
)
from spaceplan.lib_aux.tolerances import ARC_CHORD_TOL_FT


class LotGeometryError(ValueError):
    pass


@dataclass(frozen=True)
class LotEdge:
    edge_id: str
    index: int
    start: Point
    end: Point
    kind: str
    points: tuple[Point, ...]
    arc_radius_ft: float | None
    declared_class: str | None
    street_id: str | None
    alley_width_ft: float

    @property
    def length(self) -> float:
        """Length along the boundary (arc length for arcs)."""
        return polyline_length(self.points)

    @property
    def chord(self) -> float:
        return math.dist(self.start, self.end)

    @property
    def chord_midpoint(self) -> Point:
        return midpoint(self.start, self.end)

    @property
    def outward_bearing_deg(self) -> float:
        return outward_bearing_deg(self.start, self.end)


@dataclass(frozen=True)
class Lot:
    edges: tuple[LotEdge, ...]
    polygon: Polygon

    def edge(self, edge_id: str) -> LotEdge:
        for e in self.edges:
            if e.edge_id == edge_id:
                return e
        raise KeyError(edge_id)

    @property
    def is_convex(self) -> bool:
        return is_convex(self.polygon)


def build_lot(spec: dict) -> Lot:
    """Build the lot from brief.lot. Vertices must be counter-clockwise; edge i goes v[i] -> v[i+1]."""
    vertices = [(float(x), float(y)) for x, y in spec["vertices"]]
    n = len(vertices)
    if len(spec["edges"]) != n:
        raise LotGeometryError("one edge per vertex is required")
    if signed_area(vertices) <= 0:
        raise LotGeometryError("lot vertices must be counter-clockwise")
    edges, ring = [], []
    for i, e in enumerate(spec["edges"]):
        p0, p1 = vertices[i], vertices[(i + 1) % n]
        if e["kind"] == "arc":
            arc = e["arc"]
            points = discretize_arc(p0, p1, arc["radius_ft"], arc["bulge"], ARC_CHORD_TOL_FT)
            radius = float(arc["radius_ft"])
        else:
            points, radius = [p0, p1], None
        ring.extend(points[:-1])
        edges.append(
            LotEdge(
                edge_id=e["edge_id"],
                index=i,
                start=p0,
                end=p1,
                kind=e["kind"],
                points=tuple(points),
                arc_radius_ft=radius,
                declared_class=e["boundary_class"],
                street_id=e["street_id"],
                alley_width_ft=float(e.get("alley_width_ft", 0.0)),
            )
        )
    polygon = Polygon(ring)
    if not polygon.is_valid or polygon.area <= 0:
        raise LotGeometryError("lot polygon is not simple/valid")
    return Lot(edges=tuple(edges), polygon=polygon)


def chain_endpoints(lot: Lot, edge_ids: Iterable[str]) -> tuple[Point, Point]:
    """Start and end of a contiguous chain of edges (handles wrap-around in the ring)."""
    chain = [lot.edge(i) for i in edge_ids]
    starts = {e.start for e in chain}
    ends = {e.end for e in chain}
    first = [e for e in chain if e.start not in ends]
    last = [e for e in chain if e.end not in starts]
    if len(first) != 1 or len(last) != 1:
        raise LotGeometryError(f"edges {list(edge_ids)} are not one contiguous chain")
    return first[0].start, last[0].end


def front_frame(lot: Lot, front_edge_ids: Iterable[str]) -> Frame:
    """Local frame: origin at the start of the front chord, +x along it, +y into the lot."""
    p0, p1 = chain_endpoints(lot, front_edge_ids)
    return Frame(origin=p0, angle=math.atan2(p1[1] - p0[1], p1[0] - p0[0]))
