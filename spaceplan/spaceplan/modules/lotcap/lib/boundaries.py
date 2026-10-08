"""Boundary (lot line) classification: front, side, street side, rear."""

from __future__ import annotations

import math
from dataclasses import dataclass

from spaceplan.core.lib.enums import BoundaryClass, StreetRole
from spaceplan.modules.lotcap.lib.lot import Lot, LotGeometryError, front_frame
from spaceplan.core.lib_aux.geometry import Frame
from spaceplan.core.lib_aux.quantity import PROVISIONAL, VERIFIED
from spaceplan.core.lib_aux.tolerances import REAR_CLEAR_TOL_DEG, REAR_PARALLEL_TOL_DEG


@dataclass(frozen=True)
class BoundaryAssignment:
    edge_id: str
    boundary_class: str
    inferred: bool
    status: str
    note: str | None = None


@dataclass(frozen=True)
class BoundaryModel:
    assignments: dict[str, BoundaryAssignment]
    frame: Frame
    primary_street: dict
    secondary_street: dict | None
    front_edge_ids: tuple[str, ...]

    @property
    def is_corner(self) -> bool:
        return self.secondary_street is not None

    def edges_of(self, boundary_class: str) -> list[str]:
        return [eid for eid, a in self.assignments.items() if a.boundary_class == boundary_class]


def _deviation_from_front_deg(frame: Frame, edge) -> float:
    a, b = frame.point_to_local(edge.start), frame.point_to_local(edge.end)
    angle = abs(math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))) % 180.0
    return min(angle, 180.0 - angle)


def classify_boundaries(lot: Lot, streets: list[dict]) -> BoundaryModel:
    """Street edges come from the street nodes; the rest is declared or inferred.

    Inference: a non-street edge roughly parallel to the front (within REAR_PARALLEL_TOL_DEG)
    and in the back half of the lot is rear; others are side. Near-triangular lots fall back to
    the farthest edge as rear, flagged provisional (Chapter 11 definitions pending).
    """
    primary = next(s for s in streets if s["role"] == StreetRole.PRIMARY)
    secondary = next((s for s in streets if s["role"] == StreetRole.SECONDARY), None)
    order = {e.edge_id: e.index for e in lot.edges}
    front_ids = tuple(sorted(primary["frontage_edge_ids"], key=order.__getitem__))
    street_side_ids = set(secondary["frontage_edge_ids"]) if secondary else set()
    frame = front_frame(lot, front_ids)
    top = frame.to_local(lot.polygon).bounds[3]

    assignments: dict[str, BoundaryAssignment] = {}
    pending = []
    for edge in lot.edges:
        inferred = edge.declared_class is None
        if edge.edge_id in front_ids:
            assignments[edge.edge_id] = BoundaryAssignment(edge.edge_id, BoundaryClass.FRONT, inferred, VERIFIED)
        elif edge.edge_id in street_side_ids:
            assignments[edge.edge_id] = BoundaryAssignment(
                edge.edge_id, BoundaryClass.STREET_SIDE, inferred, VERIFIED
            )
        elif edge.declared_class is not None:
            assignments[edge.edge_id] = BoundaryAssignment(edge.edge_id, edge.declared_class, False, VERIFIED)
        else:
            pending.append(edge)

    has_declared_rear = any(a.boundary_class == BoundaryClass.REAR for a in assignments.values())
    rear: dict[str, tuple[str, str | None]] = {}
    if not has_declared_rear and pending:
        candidates = []
        for edge in pending:
            deviation = _deviation_from_front_deg(frame, edge)
            mid_y = frame.point_to_local(edge.chord_midpoint)[1]
            if deviation <= REAR_PARALLEL_TOL_DEG and mid_y >= 0.5 * top:
                candidates.append((edge, deviation))
        if candidates:
            clear = len(candidates) == 1 and candidates[0][1] <= REAR_CLEAR_TOL_DEG
            for edge, deviation in candidates:
                note = None if clear else f"rear inferred with {deviation:.1f} deg deviation from the front"
                rear[edge.edge_id] = (VERIFIED if clear else PROVISIONAL, note)
        else:
            far_edge = max(pending, key=lambda e: frame.point_to_local(e.chord_midpoint)[1])
            rear[far_edge.edge_id] = (
                PROVISIONAL,
                "no edge parallel to the front: farthest edge taken as rear (SDMC Ch. 11 pending)",
            )
    for edge in pending:
        if edge.edge_id in rear:
            status, note = rear[edge.edge_id]
            assignments[edge.edge_id] = BoundaryAssignment(edge.edge_id, BoundaryClass.REAR, True, status, note)
        else:
            assignments[edge.edge_id] = BoundaryAssignment(edge.edge_id, BoundaryClass.SIDE, True, VERIFIED)

    if not any(a.boundary_class == BoundaryClass.REAR for a in assignments.values()):
        raise LotGeometryError("no rear boundary could be determined")
    ordered = {e.edge_id: assignments[e.edge_id] for e in lot.edges}
    return BoundaryModel(ordered, frame, primary, secondary, front_ids)
