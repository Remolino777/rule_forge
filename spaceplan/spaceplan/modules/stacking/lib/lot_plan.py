"""Plan geometry of one lot for stage S1, read from its lot_capacity contract (no lotcap code runs).

The lot frame of the contract (lot_metrics.frame) turns world coordinates into a local frame where x runs along
the front and y away from the street. The side lot lines carry their required setback: they are where the
131.0444 plane starts. The realizable footprint of each strategy is the polygon the ground floor is cut from.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from shapely.geometry import LineString, shape
from shapely.geometry.base import BaseGeometry

from spaceplan.core.lib_aux.geometry import Frame

SIDE_CLASSES = ("side",)          # 131.0444 starts on the side setback lines (S0 reading, rule V01)
FRONT_CLASS = "front"


@dataclass(frozen=True)
class SetbackLine:
    edge_id: str
    boundary_class: str
    line: LineString                 # local frame
    setback_ft: float


@dataclass(frozen=True)
class LotPlan:
    lot_id: str
    frame: Frame
    envelope: BaseGeometry           # local frame
    side_lines: tuple[SetbackLine, ...]
    front_lines: tuple[SetbackLine, ...]
    realizable: dict[tuple[str, int | None], BaseGeometry]   # (strategy, steps) -> local footprint polygon
    far_base_sqft: float

    def footprint_for(self, strategy: str | None, steps: int | None) -> BaseGeometry | None:
        if strategy is None:
            return None
        return self.realizable.get((strategy, steps)) or self.realizable.get((strategy, None))

    def to_world(self, geom: BaseGeometry | None) -> BaseGeometry | None:
        return None if geom is None or geom.is_empty else self.frame.to_world(geom)


def _edges(lot_capacity: dict[str, Any]) -> dict[str, LineString]:
    block = lot_capacity["lot"]["lot_block"]
    vertices = [tuple(v) for v in block["vertices"]]
    out = {}
    for i, edge in enumerate(block["edges"]):
        if edge.get("kind", "segment") != "segment":
            raise ValueError(f"stacking S1: edge {edge['edge_id']} of {lot_capacity['brief_id']} is not a segment")
        out[edge["edge_id"]] = LineString([vertices[i], vertices[(i + 1) % len(vertices)]])
    return out


def lot_plan(lot_capacity: dict[str, Any]) -> LotPlan:
    metrics = lot_capacity["lot_metrics"]
    frame = Frame(tuple(metrics["frame"]["origin"]), math.radians(metrics["frame"]["angle_deg"]))
    edges = _edges(lot_capacity)
    lines = []
    for b in lot_capacity["boundaries"]:
        edge = edges.get(b["edge_id"])
        if edge is None or b.get("setback_ft") is None:
            continue
        lines.append(SetbackLine(b["edge_id"], b["boundary_class"], frame.to_local(edge), float(b["setback_ft"])))
    realizable = {}
    for r in lot_capacity.get("realizable_capacity", []):
        if r.get("polygon"):
            realizable[(r["strategy"], r.get("steps"))] = frame.to_local(shape(r["polygon"]))
    cap = lot_capacity["capacity"]
    return LotPlan(
        lot_id=lot_capacity["brief_id"],
        frame=frame,
        envelope=frame.to_local(shape(cap["envelope"]["polygon"])),
        side_lines=tuple(sl for sl in lines if sl.boundary_class in SIDE_CLASSES),
        front_lines=tuple(sl for sl in lines if sl.boundary_class == FRONT_CLASS),
        realizable=realizable,
        far_base_sqft=float(cap["far_base_area"]["value"]),
    )


def strategy_key(lot_budget: dict[str, Any], strategy_id: str | None) -> tuple[str | None, int | None]:
    """(strategy name, steps) of an area-matrix strategy id (A, B2, B3, P) on a lot."""
    for s in lot_budget["strategies"]:
        if s["strategy_id"] == strategy_id:
            return s["strategy"], s.get("steps")
    return None, None


__all__ = ["FRONT_CLASS", "SIDE_CLASSES", "LotPlan", "SetbackLine", "lot_plan", "strategy_key"]
