"""A wall closet in every bedroom without a walk-in (V6.8 k4, client decision 2026-10-17, mandatory).

Every room of space.wall_closets.types (bedrooms and the primary suite) that has no walk-in closet gets a closet
space.wall_closets.depth_ft deep (sliding door: closets are sliding_space_types) across a whole wall of the room,
never a piece of it (full_wall, hard), with front_clear_ft free in front of it. The wall is chosen in the order of
space.wall_closets.walls: an interior wall first; an exterior side wall only as the last resort; never the front
or the rear facade (they are not in the list).

On a composed floor (after the rectangle pass of k3, every room a rectangle, before the doors are placed again):
  * a room whose closet already covers a whole wall of the right kind keeps it;
  * else its partial closets join the room again when the union stays a rectangle (merge_partial), and a strip of
    the closet depth along one whole wall becomes its wall closet, when the room keeps its least side, its minimum
    area, the clear front, its furniture (hard) and the contact its doors need with every neighbour;
  * the shortest such wall of the first kind in the order wins (the room loses the least area).
The final floor is measured again (closet_report); a room left without a whole-wall closet is a violation when the
registry marks the rule hard."""

from __future__ import annotations

from typing import Any

import numpy as np

from spaceplan.modules.stacking.lib.door_placement import FloorLayout
from spaceplan.modules.stacking.lib.space_rules import SpaceRules, wall_settings
from spaceplan.modules.stacking.lib.unit_frame import OUT
from spaceplan.modules.stacking.lib_aux.rect_grid import is_rect, rect_mask
from spaceplan.modules.stacking.lib_aux.space_grid import fits_in_mask, mask_bounds
from spaceplan.modules.stacking.lib_aux.strip_grid import relabel
from spaceplan.modules.stacking.lib_aux.wall_grid import (SIDES, Y_HIGH, Y_LOW, beyond, rest_rect, side_depth,
                                                          side_length, side_strip, strip_side)

WALK_IN = "walk_in_closet"
INTERIOR, SIDE, FRONT, REAR = "interior", "side", "front", "rear"
ROLE = "wall_closet"


def _cells(ft: float, res: float) -> int:
    return max(1, int(np.ceil(ft / res - 1e-9)))


def wall_class(labels: np.ndarray, r, side: str) -> str:
    """The kind of a rectangle's wall: interior when every cell beyond it is inside the house; else front (toward
    the street, -y of the local frame), rear (+y) or side (x)."""
    vals, off = beyond(labels, r, side)
    if off or (vals == OUT).any():
        return FRONT if side == Y_LOW else REAR if side == Y_HIGH else SIDE
    return INTERIOR


def _hosted(labels: np.ndarray, specs, room) -> list[int]:
    return [j for j, x in enumerate(specs) if x.host == room.space_id and (labels == j).any()]


def _whole_wall(labels: np.ndarray, k: int, j: int, st: dict[str, Any], res: float) -> str | None:
    """The wall kind of closet j when it covers a whole wall of room k (both rectangles, their union one, the closet
    a full strip of it at least the closet depth); None otherwise."""
    room, closet = labels == k, labels == j
    union = room | closet
    if not (is_rect(room) and is_rect(closet) and is_rect(union)):
        return None
    u, c = mask_bounds(union), mask_bounds(closet)
    side = strip_side(u, c)
    if side is None or side_depth(c, side) < _cells(st["depth_ft"], res):
        return None
    return wall_class(labels, u, side)


def _room_rows(layout: FloorLayout, rules: SpaceRules, st: dict[str, Any]) -> list[dict[str, Any]]:
    """One row per room the rule holds: walk_in, or its closets (whole wall and kind, or partial) and the status
    (walk_in / ok / no_closet / partial / wrong_wall)."""
    res, lab, specs = layout.floor.res, layout.labels, layout.specs
    rows = []
    for k, s in enumerate(specs):
        if s.space_type not in st["types"] or s.fixed or not (lab == k).any():
            continue
        hosted = _hosted(lab, specs, s)
        row: dict[str, Any] = {"space_id": s.space_id, "space_type": s.space_type, "closets": []}
        if any(specs[j].space_type == WALK_IN for j in hosted):
            row["status"] = "walk_in"
            rows.append(row)
            continue
        for j in hosted:
            if specs[j].space_type != rules.closet_type:
                continue
            kind = _whole_wall(lab, k, j, st, res)
            row["closets"].append({"space_id": specs[j].space_id, "whole_wall": kind is not None, "wall": kind,
                                   "sqft": round(int((lab == j).sum()) * res * res, 1)})
        good = [c for c in row["closets"] if c["whole_wall"] and c["wall"] in st["walls"]]
        if good:
            row["status"], row["wall"] = "ok", good[0]["wall"]
        elif not row["closets"]:
            row["status"] = "no_closet"
        elif any(c["whole_wall"] for c in row["closets"]):
            row["status"] = "wrong_wall"
        else:
            row["status"] = "partial"
        rows.append(row)
    return rows


def closet_report(layout: FloorLayout, rules: SpaceRules) -> dict[str, Any] | None:
    """The rooms the rule holds on a floor and their closets (None when the rule is off)."""
    st = wall_settings(rules)
    if st is None:
        return None
    return {"rooms": _room_rows(layout, rules, st)}


def _door_need(layout: FloorLayout) -> dict[int, dict[int, float]]:
    """Node -> neighbour -> cells of wall its door there takes (the doors placed on the floor)."""
    need: dict[int, dict[int, float]] = {}
    for d in layout.doors:
        if d.run is None:
            continue
        w = float(d.t1 - d.t0)
        for a, b in ((d.a, d.b), (d.b, d.a)):
            need.setdefault(a, {})[b] = max(need.get(a, {}).get(b, 0.0), w)
    return need


def _contact(a: np.ndarray, b: np.ndarray) -> int:
    """Cell edges shared by two masks."""
    return int((a[:, :-1] & b[:, 1:]).sum() + (a[:, 1:] & b[:, :-1]).sum()
               + (a[:-1, :] & b[1:, :]).sum() + (a[1:, :] & b[:-1, :]).sum())


def _best_wall(lab: np.ndarray, k: int, s, st: dict[str, Any], rules: SpaceRules, res: float,
               need: dict[int, float]):
    """(wall kind, closet rect) of the closet room k takes: the first kind in the order with a valid wall, its
    shortest wall; None when no wall holds."""
    m = lab == k
    r = mask_bounds(m)
    d = _cells(st["depth_ft"], res)
    front = st["front_ft"] / res - 1e-9
    furniture = rules.furniture_of(s.space_type, s.master) if rules.furniture_hard_of(s.space_type, s.master) else []
    for kind in st["walls"]:
        best = None
        for side in SIDES:
            if wall_class(lab, r, side) != kind:
                continue
            strip, rest = side_strip(r, side, d), rest_rect(r, side, d)
            if side_depth(rest, side) < front or side_depth(r, side) <= d:
                continue
            w, h = rest[1] - rest[0], rest[3] - rest[2]
            if min(w, h) * res < s.min_side_ft - 1e-9 or w * h * res * res < s.min_sqft - 1e-6:
                continue
            area = (strip[1] - strip[0]) * (strip[3] - strip[2]) * res * res
            if area < rules.closet_min_sqft - 1e-9:
                continue
            rest_m = rect_mask(lab.shape, rest)
            if furniture and not any(fits_in_mask(rest_m, _cells(fw, res), _cells(fd, res)) for fw, fd in furniture):
                continue
            if any(_contact(rest_m, lab == j) < cells - 1e-9 for j, cells in need.items() if (lab == j).any()):
                continue
            cost = side_length(r, side)
            if best is None or cost < best[0]:
                best = (cost, strip)
        if best is not None:
            return kind, best[1]
    return None


def wall_closets(layout: FloorLayout, rules: SpaceRules,
                 only: set[str] | None = None) -> tuple[FloorLayout | None, dict[str, Any]]:
    """(the floor with a whole-wall closet carved in every room of the rule that lacks one, without doors; None when
    nothing changed) and the report (carved: room, wall kind, sq ft; merged: partial closets joined to their room;
    failed: rooms with no valid wall). `only`: the room ids to work on (all when None)."""
    st = wall_settings(rules)
    if st is None:
        return None, {}
    res = layout.floor.res
    lab = layout.labels.copy()
    specs = list(layout.specs)
    need = _door_need(layout)
    report: dict[str, Any] = {"carved": [], "merged": [], "failed": []}
    changed = False
    for row in _room_rows(layout, rules, st):
        if row["status"] in ("walk_in", "ok") or (only is not None and row["space_id"] not in only):
            continue
        k = next(i for i, x in enumerate(specs) if x.space_id == row["space_id"])
        s = specs[k]
        trial = lab.copy()
        merged = []
        if st["merge_partial"]:
            for j in _hosted(trial, specs, s):
                if specs[j].space_type == rules.closet_type and is_rect((trial == k) | (trial == j)):
                    trial[trial == j] = k
                    merged.append(specs[j].space_id)
        if not is_rect(trial == k):
            report["failed"].append({"space_id": s.space_id, "why": "not_rect"})
            continue
        got = _best_wall(trial, k, s, st, rules, res, need.get(k, {}))
        if got is None:
            report["failed"].append({"space_id": s.space_id, "why": "no_wall"})
            continue
        kind, strip = got
        from spaceplan.modules.stacking.lib.unit_layout import _closet_spec
        n = sum(1 for x in specs if x.host == s.space_id and ROLE in x.space_id)
        area = (strip[1] - strip[0]) * (strip[3] - strip[2]) * res * res
        trial[rect_mask(lab.shape, strip)] = len(specs)
        specs.append(_closet_spec(rules, s, n, area, ROLE))
        lab = trial
        report["merged"] += merged
        report["carved"].append({"space_id": s.space_id, "wall": kind, "sqft": round(area, 1)})
        changed = True
    if not changed:
        return None, report
    keep = [k for k in range(len(specs)) if (lab == k).any() or specs[k].fixed]
    new_lab, mapping = relabel(lab, keep)
    root = mapping.get(layout.root) if layout.root is not None else None
    landing = mapping.get(layout.landing_node) if layout.landing_node is not None else None
    out = FloorLayout(layout.floor, layout.options, [specs[k] for k in keep], new_lab, root, landing,
                      open_air=list(layout.open_air))
    out.trim, out.stair_cover, out.strips, out.rectangles = (layout.trim, layout.stair_cover, layout.strips,
                                                             layout.rectangles)
    return out, report


def wall_closet_violation(report: dict[str, Any] | None, rules: SpaceRules) -> str | None:
    """The first room of the hard rule left without a whole-wall closet of an allowed wall."""
    st = wall_settings(rules)
    if st is None or not st["hard"] or not report:
        return None
    for row in report.get("rooms", []):
        if row["status"] not in ("walk_in", "ok"):
            return f"wall_closet:{row['space_type']}:{row['status']}"
    return None


def closet_summary(report: dict[str, Any] | None) -> dict[str, Any]:
    """Counts of a floor's report: rooms by status, closets by wall kind, whole-wall closets, rooms carved."""
    out: dict[str, Any] = {"rooms": 0, "status": {}, "walls": {}, "closets": 0, "whole_wall": 0, "carved": 0}
    if not report:
        return out
    for row in report.get("rooms", []):
        out["rooms"] += 1
        out["status"][row["status"]] = out["status"].get(row["status"], 0) + 1
        for c in row["closets"]:
            out["closets"] += 1
            out["whole_wall"] += int(c["whole_wall"])
            key = c["wall"] or "partial"
            out["walls"][key] = out["walls"].get(key, 0) + 1
    out["carved"] = len(report.get("carved", []))
    return out


__all__ = ["closet_report", "closet_summary", "wall_class", "wall_closet_violation", "wall_closets",
           "wall_settings"]
