"""Fixtures of the full baths of a floor (step 6.7a S2.2j, client decision 2026-10-13 23:21, 7).

Fixtures stand in line along the bath (space.bath_fixtures): the shower or tub across the short side at one end
(wet_depth_ft deep), then the toilet (toilet_ft), then the vanity. The wet end is the short end that:
  * the bath's own closet does not touch (closet_not_wet_side: the closet is never on the shower side), and
  * the door's swing does not reach (door_not_wet: the door never opens over the shower or tub);
the end farther from the door first. `wet_keep_out` gives the door placer the end chosen by the closet before the
door exists; `bath_fixtures` lays the fixtures out once the doors are placed and reports a bath with no good end."""

from __future__ import annotations

from typing import Any

import numpy as np

from spaceplan.modules.stacking.lib.space_rules import SpaceRules
from spaceplan.modules.stacking.lib_aux.bath_geometry import band, length, touches
from spaceplan.modules.stacking.lib_aux.space_grid import swing_cells

ENDS = ("low", "high")


def fixture_settings(rules: SpaceRules) -> dict[str, Any] | None:
    d = rules.design
    if not d.get("space.bath_fixtures.enabled"):
        return None
    kinds = rules.design_kinds
    return {"types": set(d.get("space.bath_fixtures.types") or ()),
            "wet_ft": float(d["space.bath_fixtures.wet_depth_ft"]),
            "toilet_ft": float(d["space.bath_fixtures.toilet_ft"]),
            "closet_rule": bool(d.get("space.bath_fixtures.closet_not_wet_side")),
            "door_rule": bool(d.get("space.bath_fixtures.door_not_wet")),
            "hard": (kinds.get("space.bath_fixtures.closet_not_wet_side") == "hard"
                     or kinds.get("space.bath_fixtures.door_not_wet") == "hard")}


def _cells(ft: float, res: float) -> int:
    return int(np.ceil(ft / res - 1e-9))


def _closets(labels: np.ndarray, specs, k: int) -> np.ndarray:
    sid = specs[k].space_id
    m = np.zeros(labels.shape, dtype=bool)
    for j, s in enumerate(specs):
        if s.host == sid and s.space_type != specs[k].space_type:
            m |= labels == j
    return m


def wet_keep_out(labels: np.ndarray, specs, rules: SpaceRules, res: float) -> dict[int, np.ndarray]:
    """Bath node -> its wet zone, for the baths whose closet decides the wet end (the end it does not touch)."""
    st = fixture_settings(rules)
    if st is None or not st["closet_rule"]:
        return {}
    out = {}
    wet = _cells(st["wet_ft"], res)
    for k, s in enumerate(specs):
        if s.space_type not in st["types"]:
            continue
        m = labels == k
        if length(m) < 2 * wet:
            continue
        closet = _closets(labels, specs, k)
        if not closet.any():
            continue
        free = [e for e in ENDS if not touches(band(m, e, 0, wet), closet)]
        if len(free) == 1:
            out[k] = band(m, free[0], 0, wet)
    return out


def _door_swing(layout, k: int) -> tuple[np.ndarray, list]:
    sw = np.zeros(layout.labels.shape, dtype=bool)
    doors = [d for d in layout.doors if d.run is not None and k in (d.a, d.b)]
    for d in doors:
        if d.hinge_t is not None and d.leaf_cells > 0 and d.a == k:
            sw |= swing_cells(layout.labels.shape, d.run, d.into_high, d.hinge_t, d.leaf_cells, d.toward_plus)
    return sw, doors


def _door_centre(d) -> tuple[float, float]:
    t = 0.5 * (d.t0 + d.t1)
    return (d.run.k, t) if d.run.vertical else (t, d.run.k)


def bath_fixtures(layout, rules: SpaceRules) -> tuple[list[dict[str, Any]], str | None]:
    """(fixtures per full bath: the wet end and the bands of wet zone, toilet and vanity as masks, first violation)."""
    st = fixture_settings(rules)
    if st is None:
        return [], None
    res = layout.floor.res
    labels, specs = layout.labels, layout.specs
    wet, toilet = _cells(st["wet_ft"], res), _cells(st["toilet_ft"], res)
    out, bad = [], None
    for k, s in enumerate(specs):
        if s.space_type not in st["types"]:
            continue
        m = labels == k
        n = length(m)
        if n < wet + toilet:
            continue
        closet = _closets(labels, specs, k)
        swing, doors = _door_swing(layout, k)
        door_pts = [_door_centre(d) for d in doors if d.a == k or d.b == k]
        ends = []
        for e in ENDS:
            zone = band(m, e, 0, wet)
            ok_closet = not (st["closet_rule"] and closet.any() and touches(zone, closet))
            ok_door = not (st["door_rule"] and (zone & swing).any())
            rows, cols = np.nonzero(zone)
            far = min((np.hypot(cols.mean() + 0.5 - x, rows.mean() + 0.5 - y) for x, y in door_pts), default=0.0)
            ends.append((not (ok_closet and ok_door), -far, e, ok_closet, ok_door))
        ends.sort()
        _, _, e, ok_closet, ok_door = ends[0]
        good = ok_closet and ok_door
        rec = {"space_id": s.space_id, "space_type": s.space_type, "wet_end": e, "closet_ok": ok_closet,
               "door_ok": ok_door, "has_closet": bool(closet.any()),
               "masks": {"wet": band(m, e, 0, wet), "toilet": band(m, e, wet, wet + toilet),
                         "vanity": band(m, e, wet + toilet, n)}}
        out.append(rec)
        if not good and st["hard"] and bad is None:
            bad = f"bath:{'closet_on_wet_side' if not ok_closet else 'door_over_wet'}"
    return out, bad


__all__ = ["bath_fixtures", "fixture_settings", "wet_keep_out"]
