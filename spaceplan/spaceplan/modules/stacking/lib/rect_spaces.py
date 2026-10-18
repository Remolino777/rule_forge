"""Every space a rectangle (V6.8 k3, client decision 2026-10-17, mandatory).

Reading taken (to be confirmed by the client): every room and service space is one rectangle; the types of
space.rectangles.composite_types (the hall and the foyer) may be a union of rectangles. Fixed spaces (garage, stair,
the half bath and vestibule under the stair) keep the shape S1 drew.

On a composed floor (after the S2.2j strips, before the doors are placed again), a space that is no rectangle keeps
one of its candidate rectangles (largest first) that still holds its minimum area and least side; the part outside it,
cut into rectangles, goes in the order of space.rectangles.leftover_to:
  * circulation: a hall or foyer beside it (they may be composite);
  * neighbour: a space beside it that stays a rectangle with it;
  * closet: a closet of the space (the S2.2j strip-closet sizes);
  * open_air: out of the house when it stands on the facade (porch downstairs, roof upstairs);
  * chase: the wall, only a sliver thinner than a closet.
A space whose leftovers find no destination stays as it was and is reported; the check is a violation when the
registry marks the rule hard.

S2.1 also cuts an L unit along the lines of its inner corners (rect_grid.split_lines, read by unit_layout; the
settings live in space_rules.rect_settings)."""

from __future__ import annotations

from typing import Any

import numpy as np

from spaceplan.modules.stacking.lib.door_placement import FloorLayout
from spaceplan.modules.stacking.lib.space_rules import SpaceRules, must_be_rect, rect_settings
from spaceplan.modules.stacking.lib.strips import PORCH, ROOF, STAIR, _as_closet, _on_facade, _thin, strip_settings
from spaceplan.modules.stacking.lib.unit_frame import OUT, VOID, SpaceSpec
from spaceplan.modules.stacking.lib_aux.rect_grid import candidate_rects, is_rect, rect_pieces
from spaceplan.modules.stacking.lib_aux.strip_grid import neighbours, relabel

CIRCULATION, NEIGHBOUR, CLOSET, OPEN_AIR, CHASE = "circulation", "neighbour", "closet", "open_air", "chase"


def _keeps(spec: SpaceSpec, r, res: float) -> bool:
    """Does the rectangle keep the space's minimum area and least side?"""
    w, h = r[1] - r[0], r[3] - r[2]
    return min(w, h) * res >= spec.min_side_ft - 1e-9 and w * h * res * res >= spec.min_sqft - 1e-6


def _assign(lab: np.ndarray, specs: list[SpaceSpec], k: int, r, st: dict[str, Any], sst: dict[str, Any] | None,
            rules: SpaceRules, level: int, res: float):
    """(labels, new closet specs, new open-air entries, moves) with every leftover of space k outside rectangle r
    placed; None when one finds no destination."""
    s = specs[k]
    lab = lab.copy()
    extra: list[SpaceSpec] = []
    air: list[tuple[SpaceSpec, np.ndarray]] = []
    moves: list[dict[str, Any]] = []
    ca = res * res
    n_spec = len(specs)
    all_specs = specs

    def spec_of(j: int) -> SpaceSpec:
        return all_specs[j] if j < n_spec else extra[j - n_spec]

    for piece in rect_pieces(lab == k, r):
        sqft = round(int(piece.sum()) * ca, 1)
        done = False
        for dest in st["order"]:
            if dest in (CIRCULATION, NEIGHBOUR):
                nb = neighbours(lab, piece)
                cands = []
                for j, contact in nb.items():
                    sj = spec_of(j)
                    if j == k or sj.fixed or sj.space_type == STAIR:
                        continue
                    if dest == CIRCULATION and sj.space_type in st["composite"]:
                        cands.append((contact, j))
                    elif dest == NEIGHBOUR and must_be_rect(sj, st) and is_rect((lab == j) | piece):
                        cands.append((contact, j))
                if cands:
                    j = max(cands)[1]
                    lab[piece] = j
                    moves.append({"from": s.space_id, "into": spec_of(j).space_id, "to": dest, "sqft": sqft})
                    done = True
            elif dest == CLOSET and sst is not None:
                n = sum(1 for x in [*all_specs, *extra] if x.host == s.space_id
                        and x.space_id.startswith(f"{s.space_id}_rect_closet"))
                closet = _as_closet(piece, s, sst, rules, res, n)
                if closet is not None:
                    closet = SpaceSpec(**{**closet.__dict__,
                                          "space_id": closet.space_id.replace("strip_closet", "rect_closet")})
                    lab[piece] = n_spec + len(extra)
                    extra.append(closet)
                    moves.append({"from": s.space_id, "into": closet.space_id, "to": dest, "sqft": sqft})
                    done = True
            elif dest == OPEN_AIR and _on_facade(lab, piece):
                kind = PORCH if level == 0 else ROOF
                lab[piece] = OUT
                air.append((SpaceSpec(f"{s.space_id}_rect_{kind}{len(air)}", kind, "exterior", s.unit_id,
                                      int(piece.sum()) * ca, 0.0, 0.0, False, False, False, frozenset(),
                                      s.space_id, False, True), piece.copy()))
                moves.append({"from": s.space_id, "into": kind, "to": dest, "sqft": sqft})
                done = True
            elif dest == CHASE and sst is not None and _thin(piece, sst, res):
                lab[piece] = VOID
                moves.append({"from": s.space_id, "into": "chase", "to": dest, "sqft": sqft})
                done = True
            if done:
                break
        if not done:
            return None
    return lab, extra, air, moves


def rectify(layout: FloorLayout, rules: SpaceRules) -> tuple[FloorLayout | None, dict[str, Any]]:
    """(the floor with every space the rule holds to a rectangle cut to one, without doors; None when nothing
    changed) and the report (moves by destination, spaces left)."""
    st = rect_settings(rules)
    if st is None:
        return None, {}
    sst = strip_settings(rules)
    res = layout.floor.res
    lab = layout.labels.copy()
    specs = list(layout.specs)
    open_air = list(layout.open_air)
    report: dict[str, Any] = {"moves": [], "left": []}
    changed = False
    for k in range(len(layout.specs)):
        s = specs[k]
        if not must_be_rect(s, st):
            continue
        m = lab == k
        if not m.any() or is_rect(m):
            continue
        got = None
        for r in candidate_rects(m):
            if not _keeps(s, r, res):
                continue
            got = _assign(lab, specs, k, r, st, sst, rules, layout.floor.level, res)
            if got is not None:
                break
        if got is None:
            report["left"].append({"space_id": s.space_id, "space_type": s.space_type,
                                   "sqft": round(int(m.sum()) * res * res, 1)})
            continue
        lab, extra, air, moves = got
        specs += extra
        open_air += air
        report["moves"] += moves
        changed = True
    if not changed:
        return None, report
    keep = [k for k in range(len(specs)) if (lab == k).any() or specs[k].fixed]
    new_lab, mapping = relabel(lab, keep)
    root = mapping.get(layout.root) if layout.root is not None else None
    landing = mapping.get(layout.landing_node) if layout.landing_node is not None else None
    out = FloorLayout(layout.floor, layout.options, [specs[k] for k in keep], new_lab, root, landing,
                      open_air=open_air)
    out.trim, out.stair_cover, out.strips = layout.trim, layout.stair_cover, layout.strips
    return out, report


def rect_violation(layout: FloorLayout, rules: SpaceRules) -> str | None:
    """The first space the hard rule holds to a rectangle that is not one."""
    st = rect_settings(rules)
    if st is None or not st["hard"]:
        return None
    for k, s in enumerate(layout.specs):
        if must_be_rect(s, st):
            m = layout.labels == k
            if m.any() and not is_rect(m):
                return f"rect:{s.space_type}"
    return None


def rect_summary(report: dict[str, Any] | None) -> dict[str, Any]:
    """Leftover square feet by destination and the spaces left, from a floor's report."""
    out: dict[str, Any] = {"by_destination": {}, "left": 0}
    if not report:
        return out
    for mv in report.get("moves", []):
        out["by_destination"][mv["to"]] = round(out["by_destination"].get(mv["to"], 0.0) + mv["sqft"], 1)
    out["left"] = len(report.get("left", []))
    return out


__all__ = ["rect_summary", "rect_violation", "rectify"]
