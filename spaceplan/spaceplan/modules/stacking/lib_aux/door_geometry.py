"""Exact door geometry and interference checks (step 6.7a S2.2e, P2): shapely polygons, not raster cells or
distances.

Per door (a block of the s21 floor contract: segment, hinge, leaf_ft, swing polygon, kind, a / b):

  swing      the quarter disc the leaf sweeps (hinged doors only; drawn by the contract);
  leaf       the closed leaf: the doorway segment from the hinge, as thick as the leaf;
  approach   the approach zone: the doorway segment widened to `approach_depth_ft` on both sides.

Rules (design_circulation_doors P03, parameters door.conflicts.*):

  R1   two swings cross (area above the tolerance): the leaves collide when both doors are open;
       exception E1 (same_suite_exception): both doors serve the same private suite and neither leaf reaches the
       other closed leaf, so one person opens them in turn;
  R1b  a swing reaches the closed leaf of another door: the leaves strike even one at a time (never excepted);
  R2   a swing leaves the space it serves: the leaf hits a wall;
  R3   a swing enters the approach zone of another doorway (openings and sliders included): a person going through
       that doorway meets the leaf.

Stair links carry no geometry. Exterior doors count with their segment.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from shapely.geometry import LineString, Point, Polygon, shape
from shapely.ops import substring
from shapely.strtree import STRtree

INCH_FT = 1.0 / 12.0
R1, R1B, R2, R3, E1 = "R1", "R1b", "R2", "R3", "E1"


@dataclass(frozen=True)
class DoorShape:
    index: int
    a: str
    b: str
    kind: str
    segment: LineString
    swing: Polygon | None
    leaf: Polygon | None
    approach: Polygon
    swing_into: str | None


def closed_leaf(segment: LineString, hinge: tuple[float, float], leaf_ft: float, thickness_ft: float) -> Polygon:
    """The closed leaf: from the hinge along the doorway (toward its far end), `leaf_ft` long, `thickness_ft`
    thick."""
    d0 = segment.project(Point(hinge))
    if d0 <= segment.length / 2.0:
        start, end = d0, min(segment.length, d0 + leaf_ft)
    else:
        start, end = max(0.0, d0 - leaf_ft), d0
    return substring(segment, start, end).buffer(thickness_ft / 2.0, cap_style="flat")


def approach_zone(segment: LineString, depth_ft: float) -> Polygon:
    """The doorway widened to `depth_ft` on both sides (flat ends: the zone is as wide as the doorway)."""
    return segment.buffer(depth_ft, cap_style="flat")


def door_shapes(doors: Iterable[dict[str, Any]], approach_depth_ft: float, thickness_ft: float,
                doorway_max_ft: float | None = None) -> list[DoorShape]:
    """Shapes of the doors with a segment; a leafless opening wider than `doorway_max_ft` is an open boundary (the
    great room) and gets no approach zone."""
    out = []
    for k, d in enumerate(doors):
        seg = d.get("segment")
        if not seg or len(seg) < 2:
            continue
        line = LineString(seg)
        if line.length <= 0:
            continue
        swing = shape(d["swing"]) if d.get("swing") else None
        leaf = None
        if swing is not None and d.get("hinge") and d.get("leaf_ft"):
            leaf = closed_leaf(line, tuple(d["hinge"]), float(d["leaf_ft"]), thickness_ft)
        wide = swing is None and doorway_max_ft is not None and line.length > doorway_max_ft + 1e-9
        out.append(DoorShape(k, d["a"], d["b"], d.get("kind", ""), line, swing, leaf,
                             Polygon() if wide else approach_zone(line, approach_depth_ft), d.get("swing_into")))
    return out


def _suite_of(space_id: str, hosts: dict[str, str | None], private: set[str]) -> str | None:
    """The private suite of a space: the top of its host chain, when that room is private (a bedroom, the
    primary suite); None otherwise."""
    seen: set[str] = set()
    s = space_id
    while hosts.get(s) and s not in seen:
        seen.add(s)
        s = hosts[s]
    return s if s in private else None


def floor_conflicts(doors: list[dict[str, Any]], spaces: list[dict[str, Any]], params: dict[str, Any],
                    private_types: Iterable[str] = ()) -> list[dict[str, Any]]:
    """Interference findings of one floor: {rule, doors (indices), spaces (a-b of each door), area_sqft, exception}.
    `params`: the door.conflicts.* values without the prefix."""
    tol = float(params.get("overlap_tolerance_sqft", 0.0) or 0.0)
    depth = float(params.get("approach_depth_ft", 3.0) or 0.0)
    thick = float(params.get("leaf_thickness_in", 1.75) or 0.0) * INCH_FT
    wide = params.get("doorway_max_width_ft")
    shapes = door_shapes(doors, depth, thick, None if wide is None else float(wide))
    rooms = {s["space_id"]: shape(s["polygon"]) for s in spaces if s.get("polygon")}
    hosts = {s["space_id"]: s.get("host") for s in spaces}
    private = {s["space_id"] for s in spaces if s.get("space_type") in set(private_types)}
    findings: list[dict[str, Any]] = []

    def pair(rule: str, x: DoorShape, y: DoorShape | None, area: float, exception: str | None = None) -> None:
        findings.append({"rule": rule, "doors": [x.index] + ([y.index] if y else []),
                         "spaces": [f"{x.a}|{x.b}"] + ([f"{y.a}|{y.b}"] if y else []),
                         "area_sqft": round(area, 3), "exception": exception})

    swinging = [d for d in shapes if d.swing is not None]
    # R2: the swing inside the space it serves
    if params.get("no_swing_outside_room", True):
        for d in swinging:
            room = rooms.get(d.swing_into or d.a)
            if room is None:
                continue
            out_area = d.swing.difference(room).area
            if out_area > tol:
                pair(R2, d, None, out_area)
    # R1 / R1b: swing against swing and against the closed leaf
    tree = STRtree([d.swing for d in swinging]) if swinging else None
    for i, d in enumerate(swinging):
        for j in tree.query(d.swing) if tree is not None else ():
            j = int(j)
            if j <= i:
                continue
            e = swinging[j]
            if params.get("no_swing_overlap", True):
                area = d.swing.intersection(e.swing).area
                if area > tol:
                    strike = (e.leaf is not None and d.swing.intersection(e.leaf).area > tol) or \
                             (d.leaf is not None and e.swing.intersection(d.leaf).area > tol)
                    sa = _suite_of(d.swing_into or d.a, hosts, private)
                    se = _suite_of(e.swing_into or e.a, hosts, private)
                    same = sa is not None and sa == se
                    exc = E1 if params.get("same_suite_exception", False) and same and not strike else None
                    pair(R1, d, e, area, exc)
    for d in swinging:
        for e in swinging:
            if d.index == e.index or e.leaf is None:
                continue
            area = d.swing.intersection(e.leaf).area
            if area > tol:
                pair(R1B, d, e, area)
    # R3: a swing on the approach zone of another doorway
    if params.get("no_swing_on_doorway", True) and swinging:
        zoned = [z for z in shapes if not z.approach.is_empty]
        ztree = STRtree([z.approach for z in zoned])
        for d in swinging:
            for j in ztree.query(d.swing):
                e = zoned[int(j)]
                if e.index == d.index:
                    continue
                area = d.swing.intersection(e.approach).area
                if area > tol:
                    pair(R3, d, e, area)
    return findings


def summarize(findings: list[dict[str, Any]]) -> dict[str, int]:
    """Counts per rule; R1 split into conflicts and E1 exceptions."""
    out = {R1: 0, E1: 0, R1B: 0, R2: 0, R3: 0}
    for f in findings:
        if f["rule"] == R1 and f["exception"] == E1:
            out[E1] += 1
        else:
            out[f["rule"]] += 1
    return out


__all__ = ["E1", "R1", "R1B", "R2", "R3", "DoorShape", "approach_zone", "closed_leaf", "door_shapes",
           "floor_conflicts", "summarize"]
