"""Lot measurements with named methods (width and depth are ambiguous on irregular lots)."""

from __future__ import annotations

import math
from dataclasses import dataclass

from spaceplan.modules.lotcap.lib.boundaries import BoundaryModel
from spaceplan.core.lib.enums import BoundaryClass, DepthMethod, WidthMethod
from spaceplan.modules.lotcap.lib.lot import Lot, chain_endpoints
from spaceplan.core.lib_aux.geometry import chord_length_at_y, midpoint


@dataclass(frozen=True)
class LotMetrics:
    area_sqft: float
    frontage_ft: float
    front_chord_ft: float
    front_curve_radius_ft: float | None
    widths_ft: dict[str, float]
    depths_ft: dict[str, float]
    is_convex: bool
    is_corner: bool

    def to_dict(self, width_method: str, depth_method: str, frame) -> dict:
        return {
            "area_sqft": self.area_sqft,
            "frontage_ft": self.frontage_ft,
            "front_chord_ft": self.front_chord_ft,
            "front_curve_radius_ft": self.front_curve_radius_ft,
            "is_convex": self.is_convex,
            "is_corner": self.is_corner,
            "widths_ft": dict(self.widths_ft),
            "depths_ft": dict(self.depths_ft),
            "width_method": width_method,
            "depth_method": depth_method,
            "frame": {"origin": list(frame.origin), "angle_deg": math.degrees(frame.angle)},
        }


def measure_lot(
    lot: Lot, boundaries: BoundaryModel, front_setback_ft: float, front_curve_radius_ft: float | None
) -> LotMetrics:
    """Width/depth under every method.

    depth  front_rear_midpoints: distance between the front-chord midpoint and the rear midpoint.
    depth  max_extent: extent of the lot along the front normal.
    width  mean_width: area / front_rear_midpoints depth.
    width  frontage: length along the primary street (arc length if curved).
    width  at_front_setback: width of the lot on the line parallel to the front at the setback.
    """
    frame = boundaries.frame
    local = frame.to_local(lot.polygon)
    area = lot.polygon.area
    front_edges = [lot.edge(i) for i in boundaries.front_edge_ids]
    frontage = sum(e.length for e in front_edges)
    p0, p1 = chain_endpoints(lot, boundaries.front_edge_ids)
    front_mid = frame.point_to_local(midpoint(p0, p1))
    rear_mids = [frame.point_to_local(lot.edge(i).chord_midpoint) for i in boundaries.edges_of(BoundaryClass.REAR)]
    rear_mid = (
        sum(p[0] for p in rear_mids) / len(rear_mids),
        sum(p[1] for p in rear_mids) / len(rear_mids),
    )
    depth_mid = math.dist(front_mid, rear_mid)
    depths = {
        DepthMethod.FRONT_REAR_MIDPOINTS.value: depth_mid,
        DepthMethod.MAX_EXTENT.value: local.bounds[3] - local.bounds[1],
    }
    widths = {
        WidthMethod.MEAN_WIDTH.value: area / depth_mid,
        WidthMethod.FRONTAGE.value: frontage,
        WidthMethod.AT_FRONT_SETBACK.value: chord_length_at_y(local, front_setback_ft),
    }
    return LotMetrics(
        area_sqft=area,
        frontage_ft=frontage,
        front_chord_ft=math.dist(p0, p1),
        front_curve_radius_ft=front_curve_radius_ft,
        widths_ft=widths,
        depths_ft=depths,
        is_convex=lot.is_convex,
        is_corner=boundaries.is_corner,
    )
