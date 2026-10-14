"""No thin strips of space (step 6.7a S2.2j, client decision 2026-10-13 23:21, 6; sizes 23:30, c).

On a composed floor (after the hall trim and the stair closet, before the doors are placed again):
  * a part of a room or hall narrower than space.strips.min_part_ft (a closet or storage space: closet_min_part_ft)
    becomes a closet of its space when it is deep and long enough for one; a strip on the facade leaves the house
    (porch downstairs, roof upstairs); else it joins a neighbour: the stair (only a sliver thinner than a closet: its
    enclosure), or the neighbour it shares the most wall with in which it is no strip; fixed spaces never take it;
    a sliver thinner than a closet that no space takes becomes wall (a chase);
  * a closet whose front is under space.strips.closet_min_front_ft joins its room (else the neighbour it shares the
    most wall with) and disappears.
What cannot be joined stays and is reported; it is a violation when the registry marks the rule hard."""

from __future__ import annotations

from typing import Any

import numpy as np

from spaceplan.modules.stacking.lib.door_placement import FloorLayout
from spaceplan.modules.stacking.lib.space_rules import SpaceRules
from spaceplan.modules.stacking.lib.unit_frame import OUT, VOID, SpaceSpec
from spaceplan.modules.stacking.lib_aux.space_grid import mask_bounds
from spaceplan.modules.stacking.lib_aux.strip_grid import neighbours, relabel, strip_cells, strip_parts

STAIR = "stair"
PORCH, ROOF = "porch", "upper_roof"     # S2.2g / S2.2d open air: a facade strip leaves the house
MIN_PART_CELLS = 2                     # a one-cell step of the grid is no strip


def strip_settings(rules: SpaceRules) -> dict[str, Any] | None:
    d = rules.design
    if not d.get("space.strips.enabled"):
        return None
    return {"length_ft": float(d.get("space.strips.min_length_ft") or 0.0),
            "circulation_hard": bool(d.get("space.strips.circulation_hard")),
            "room_ft": float(d.get("space.strips.min_part_ft") or 3.0),
            "closet_ft": float(d.get("space.strips.closet_min_part_ft") or 2.0),
            "front_ft": float(d.get("space.strips.closet_min_front_ft") or 0.0),
            "storage": set(d.get("space.strips.storage_types") or ()),
            "hard": rules.design_kinds.get("space.strips.enabled") == "hard"}


def _width(st: dict[str, Any], space_type: str, res: float) -> int:
    ft = st["closet_ft"] if space_type in st["storage"] else st["room_ft"]
    return int(np.ceil(ft / res - 1e-9))


def _parts(mask: np.ndarray, st: dict[str, Any], space_type: str, res: float) -> list[np.ndarray]:
    """The strips of a space at least min_length_ft long (a shorter one is a jog of the wall)."""
    need = st["length_ft"] / res - 1e-9
    out = []
    for p in strip_parts(mask, _width(st, space_type, res), MIN_PART_CELLS):
        b = mask_bounds(p)
        if b is not None and max(b[1] - b[0], b[3] - b[2]) >= need:
            out.append(p)
    return out


def floor_strips(layout: FloorLayout, rules: SpaceRules) -> list[dict[str, Any]]:
    """The strips left on a floor: one row per space with any (space, type, sq ft)."""
    st = strip_settings(rules)
    if st is None:
        return []
    res = layout.floor.res
    out = []
    for k, s in enumerate(layout.specs):
        if s.fixed or s.space_type == STAIR:
            continue
        m = layout.labels == k
        cells = sum(int(p.sum()) for p in _parts(m, st, s.space_type, res))
        if cells:
            out.append({"space_id": s.space_id, "space_type": s.space_type, "sqft": round(cells * res * res, 1)})
    return out


def _thin(part: np.ndarray, st: dict[str, Any], res: float) -> bool:
    """Is the strip thinner than a closet (a sliver, not a usable strip)?"""
    b = mask_bounds(part)
    return b is not None and min(b[1] - b[0], b[3] - b[2]) * res < st["closet_ft"] - 1e-9


def _on_facade(lab: np.ndarray, part: np.ndarray) -> bool:
    """Does the strip stand on the facade along at least half its length (its outside neighbours)?"""
    b = mask_bounds(part)
    if b is None:
        return False
    long_ = max(b[1] - b[0], b[3] - b[2])
    out = lab == OUT
    nb = np.zeros_like(part)
    nb[:, 1:] |= out[:, :-1]
    nb[:, :-1] |= out[:, 1:]
    nb[1:, :] |= out[:-1, :]
    nb[:-1, :] |= out[1:, :]
    edge = part & nb
    if not edge.any():
        return False
    eb = mask_bounds(edge)
    return max(eb[1] - eb[0], eb[3] - eb[2]) >= 0.5 * long_


def _as_closet(part: np.ndarray, s, st: dict[str, Any], rules: SpaceRules, res: float, n: int = 0):
    """A closet of space `s` made of a strip: a full rectangle at least the closet's least width, front and area,
    off a space that is no closet itself; None otherwise."""
    if s.space_type in st["storage"] or s.space_type == STAIR:
        return None
    b = mask_bounds(part)
    if b is None or int(part.sum()) != (b[1] - b[0]) * (b[3] - b[2]):
        return None
    short, long_ = sorted((b[1] - b[0], b[3] - b[2]))
    area = int(part.sum()) * res * res
    if short * res < st["closet_ft"] - 1e-9 or long_ * res < st["front_ft"] - 1e-9:
        return None
    if not (rules.closet_min_sqft - 1e-9 <= area <= rules.closet_max_sqft + 1e-9):
        return None
    from spaceplan.modules.stacking.lib.unit_layout import _closet_spec
    return _closet_spec(rules, s, n, area, "strip_closet")


def clean_strips(layout: FloorLayout, rules: SpaceRules,
                 keep_circulation: bool = False) -> tuple[FloorLayout | None, dict[str, Any]]:
    """(the floor with its strips joined to their neighbours and its small closets joined to their rooms, without
    doors; None when nothing changed) and the report (joined, removed closets, strips left). `keep_circulation`:
    the strips of halls and foyers stay (reported as left)."""
    st = strip_settings(rules)
    if st is None:
        return None, {}
    specs = list(layout.specs)
    res = layout.floor.res
    ca = res * res
    lab = layout.labels.copy()
    stair = next((k for k, s in enumerate(specs) if s.space_type == STAIR), None)
    report: dict[str, Any] = {"joined": [], "closets_removed": [], "left": []}
    open_air = list(layout.open_air)
    changed = False
    by_id = {s.space_id: k for k, s in enumerate(specs)}

    def takes(j: int, part: np.ndarray) -> bool:
        if j == stair:                                    # only a sliver thinner than a closet: the stair's wall
            return _thin(part, st, res)
        s = specs[j]
        if s.fixed:
            return False
        merged = (lab == j) | part
        return not (strip_cells(merged, _width(st, s.space_type, res)) & part).any()

    # closets too small to open (front under the minimum) join their room
    front = int(np.floor(st["front_ft"] / res + 1e-9))
    for k, s in enumerate(specs):
        if s.space_type != rules.closet_type or s.fixed:
            continue
        m = lab == k
        b = mask_bounds(m)
        if b is None or max(b[1] - b[0], b[3] - b[2]) >= front:
            continue
        nb = neighbours(lab, m)
        host = by_id.get(s.host) if s.host else None
        pick = host if host is not None and host in nb else None
        if pick is None:
            cands = [j for j, _ in sorted(nb.items(), key=lambda kv: -kv[1]) if not specs[j].fixed]
            pick = cands[0] if cands else None
        if pick is None:
            continue
        lab[m] = pick
        changed = True
        report["closets_removed"].append({"space_id": s.space_id, "sqft": round(int(m.sum()) * ca, 1),
                                          "into": specs[pick].space_id})

    # strips of every space join a neighbour
    for k, s in enumerate(specs):
        if s.fixed or s.space_type == STAIR:
            continue
        for part in _parts(lab == k, st, s.space_type, res):
            if keep_circulation and s.circulation:
                report["left"].append({"space_id": s.space_id, "space_type": s.space_type,
                                       "sqft": round(int(part.sum()) * ca, 1), "circulation": True})
                continue
            closet = _as_closet(part, s, st, rules, res, sum(1 for x in specs if x.host == s.space_id
                                                              and x.space_id.startswith(f"{s.space_id}_strip_closet")))
            if closet is not None:                            # a strip deep enough for a closet: a closet of the
                lab[part] = len(specs)                        # space (a coat closet off the foyer)
                specs.append(closet)
                changed = True
                report["joined"].append({"from": s.space_id, "into": closet.space_id,
                                         "sqft": round(int(part.sum()) * ca, 1)})
                continue
            if _on_facade(lab, part):                         # a strip along the facade leaves the house:
                kind = PORCH if layout.floor.level == 0 else ROOF  # a porch downstairs, roof upstairs
                lab[part] = OUT
                open_air.append((SpaceSpec(f"{s.space_id}_{kind}{len(open_air)}", kind, "exterior", s.unit_id,
                                           int(part.sum()) * ca, 0.0, 0.0, False, False, False, frozenset(),
                                           s.space_id, False, True), part.copy()))
                changed = True
                report["joined"].append({"from": s.space_id, "into": kind, "sqft": round(int(part.sum()) * ca, 1)})
                continue
            nb = neighbours(lab, part)
            order = ([stair] if stair is not None and stair in nb else []) + \
                [j for j, _ in sorted(nb.items(), key=lambda kv: -kv[1]) if j != stair]
            pick = next((j for j in order if takes(j, part)), None)
            if pick is None and _thin(part, st, res):          # a sliver no space takes: wall (a chase)
                lab[part] = VOID
                changed = True
                report["joined"].append({"from": s.space_id, "into": "chase", "sqft": round(int(part.sum()) * ca, 1)})
                continue
            if pick is None:
                report["left"].append({"space_id": s.space_id, "space_type": s.space_type,
                                       "sqft": round(int(part.sum()) * ca, 1), "circulation": s.circulation})
                continue
            lab[part] = pick
            changed = True
            report["joined"].append({"from": s.space_id, "into": specs[pick].space_id,
                                     "sqft": round(int(part.sum()) * ca, 1)})
    if not changed:
        return None, report
    keep = [k for k in range(len(specs)) if (lab == k).any() or specs[k].fixed]
    new_lab, mapping = relabel(lab, keep)
    root = mapping.get(layout.root) if layout.root is not None else None
    landing = mapping.get(layout.landing_node) if layout.landing_node is not None else None
    out = FloorLayout(layout.floor, layout.options, [specs[k] for k in keep], new_lab, root, landing,
                      open_air=open_air)
    out.trim, out.stair_cover = layout.trim, layout.stair_cover
    return out, report


def strip_violation(report: dict[str, Any], rules: SpaceRules) -> str | None:
    """The first strip left that the rule forbids: any, but a hall or foyer strip only with circulation_hard."""
    st = strip_settings(rules)
    if st is None or not st["hard"]:
        return None
    bad = [x for x in report.get("left", []) if st["circulation_hard"] or not x.get("circulation")]
    return f"strip:{bad[0]['space_type']}" if bad else None


__all__ = ["clean_strips", "floor_strips", "strip_settings", "strip_violation"]
