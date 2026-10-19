"""Step V6.8 k4 (client 2026-10-17): every bedroom without a walk-in has a wall closet (2 ft deep, sliding door, 3 ft
clear in front) across a whole wall, never a piece of it; an interior wall first, an exterior side wall only as the
last resort, never the front or rear facade; the check is hard."""

from types import SimpleNamespace

import numpy as np
import pytest

from spaceplan.core.lib.catalog import load_catalog
from spaceplan.modules.design.lib.design_registry import load_registry
from spaceplan.modules.stacking.lib.door_placement import FloorLayout
from spaceplan.modules.stacking.lib.space_rules import (
    design_view,
    load_crc_ruleset,
    load_openings_ruleset,
    space_rules,
)
from spaceplan.modules.stacking.lib.stacking_catalog import load_stacking_catalog
from spaceplan.modules.stacking.lib.stair_access import load_client_ruleset
from spaceplan.modules.stacking.lib.stair_rules import load_stair_ruleset
from spaceplan.modules.stacking.lib.unit_frame import SpaceSpec
from spaceplan.modules.stacking.lib.wall_closets import (
    closet_report,
    closet_summary,
    wall_class,
    wall_closet_violation,
    wall_closets,
    wall_settings,
)
from spaceplan.modules.stacking.lib_aux.rect_grid import is_rect
from spaceplan.modules.stacking.lib_aux.space_grid import mask_bounds
from spaceplan.modules.stacking.lib_aux.wall_grid import (
    X_HIGH,
    X_LOW,
    Y_HIGH,
    Y_LOW,
    beyond,
    rest_rect,
    side_length,
    side_strip,
    strip_side,
)

RES = 0.5


@pytest.fixture(scope="module")
def rules():
    scat, cat = load_stacking_catalog(), load_catalog()
    return space_rules(scat, cat, load_crc_ruleset(), load_openings_ruleset(), load_stair_ruleset(),
                       load_client_ruleset(), design_view())


def _spec(sid, st, host=None, circ=False, fixed=False, min_sqft=0.0, min_side=0.0):
    return SpaceSpec(sid, st, "private", "u", 100.0, min_sqft, min_side, not circ, circ, circ, frozenset(), host,
                     fixed)


def _layout(labels, specs, doors=(), level=1):
    floor = SimpleNamespace(res=RES, level=level, landing=np.zeros(labels.shape, dtype=bool),
                            stair=np.zeros(labels.shape, dtype=bool))
    lay = FloorLayout(floor, (), list(specs), labels, 0, 0)
    lay.doors = list(doors)
    return lay


def _door(a, b, cells=6):
    return SimpleNamespace(a=a, b=b, run=object(), t0=0.0, t1=float(cells))


def _house():
    """A hall (x 1:9), a bedroom 13 x 12 ft (x 9:35, y 1:25) and a study on its right (x 35:47), outside around."""
    labels = np.full((26, 48), -1, dtype=np.int32)
    labels[1:25, 1:9] = 0
    labels[1:25, 9:35] = 1
    labels[1:25, 35:47] = 2
    specs = [_spec("hall", "hall", circ=True), _spec("bed", "bedroom", min_side=8.0, min_sqft=70.0),
             _spec("study", "study")]
    return labels, specs


# ------------------------------------------------------------------ registry


def test_the_registry_holds_the_wall_closet_decision(rules):
    reg = load_registry()
    p = reg.get("space.wall_closets.enabled")
    assert p.value is True and p.kind == "hard" and p.who == "client"
    assert reg.get("space.wall_closets.full_wall").kind == "hard"
    walls = reg.get("space.wall_closets.walls").value
    assert walls == ["interior", "side"] and "front" not in walls and "rear" not in walls
    st = wall_settings(rules)
    assert st["hard"] and st["depth_ft"] == 2.0 and st["front_ft"] == 3.0
    assert st["types"] == {"bedroom", "primary_suite"}


def test_an_empty_registry_is_pre_k4():
    values, kinds = design_view()
    off = SimpleNamespace(design={**values, "space.wall_closets.enabled": False}, design_kinds=kinds)
    assert wall_settings(off) is None


def test_closets_slide(rules):
    assert "closet" in rules.s21["doors"]["sliding_space_types"]


# ------------------------------------------------------------------ grid


def test_sides_of_a_rectangle():
    r = (2, 10, 4, 8)
    assert side_length(r, X_LOW) == 4 and side_length(r, Y_LOW) == 8
    assert side_strip(r, X_HIGH, 2) == (8, 10, 4, 8) and rest_rect(r, X_HIGH, 2) == (2, 8, 4, 8)
    assert side_strip(r, Y_LOW, 1) == (2, 10, 4, 5) and rest_rect(r, Y_LOW, 1) == (2, 10, 5, 8)
    assert strip_side(r, (2, 10, 6, 8)) == Y_HIGH and strip_side(r, (2, 3, 4, 8)) == X_LOW
    assert strip_side(r, (2, 5, 6, 8)) is None                       # a piece of a wall, not the whole
    labels = np.zeros((10, 12), dtype=np.int32)
    vals, off = beyond(labels, (0, 4, 0, 3), Y_LOW)
    assert len(vals) == 0 and off == 4


def test_the_kind_of_a_wall():
    labels, _ = _house()
    r = mask_bounds(labels == 1)
    assert wall_class(labels, r, X_LOW) == "interior" and wall_class(labels, r, X_HIGH) == "interior"
    assert wall_class(labels, r, Y_LOW) == "front" and wall_class(labels, r, Y_HIGH) == "rear"
    r2 = mask_bounds(labels == 2)
    assert wall_class(labels, r2, X_HIGH) == "side"


# ------------------------------------------------------------------ the floor pass


def test_the_closet_takes_a_whole_interior_wall_off_the_door(rules):
    labels, specs = _house()
    lay = _layout(labels, specs, doors=[_door(1, 0)])               # the bedroom opens onto the hall
    before = closet_report(lay, rules)
    assert before["rooms"][0]["status"] == "no_closet"
    assert wall_closet_violation(before, rules) == "wall_closet:bedroom:no_closet"
    new, rep = wall_closets(lay, rules)
    assert new is not None and rep["carved"][0]["wall"] == "interior" and not rep["failed"]
    c = new.node("bed_wall_closet")
    assert c is not None and new.specs[c].host == "bed" and new.specs[c].space_type == "closet"
    cm = new.labels == c
    assert is_rect(cm) and mask_bounds(cm) == (31, 35, 1, 25)       # the whole study wall, 2 ft deep
    assert is_rect(new.labels == new.node("bed"))
    after = closet_report(new, rules)
    assert after["rooms"][0]["status"] == "ok" and after["rooms"][0]["wall"] == "interior"
    assert wall_closet_violation(after, rules) is None
    s = closet_summary(after)
    assert s["whole_wall"] == 1 and s["walls"] == {"interior": 1} and s["status"] == {"ok": 1}


def test_the_hall_wall_is_kept_for_the_door(rules):
    labels, specs = _house()
    labels[1:25, 35:47] = -1                                         # no study: the right wall is a side facade
    specs = specs[:2]
    new, rep = wall_closets(_layout(labels, specs, doors=[_door(1, 0)]), rules)
    assert new is not None and rep["carved"][0]["wall"] == "side"   # the last resort, never the front or rear
    assert mask_bounds(new.labels == new.node("bed_wall_closet")) == (31, 35, 1, 25)


def test_never_on_the_front_or_rear_facade(rules):
    labels = np.full((26, 30), -1, dtype=np.int32)
    labels[1:25, 1:3] = 0                                            # hall on the left
    labels[1:25, 3:27] = 1                                           # the bedroom
    labels[1:25, 27:29] = 2                                          # a bath on the right
    specs = [_spec("hall", "hall", circ=True), _spec("bed", "bedroom", min_side=8.0), _spec("bath", "bathroom")]
    lay = _layout(labels, specs, doors=[_door(1, 0), _door(2, 1)])  # both interior walls carry a door
    new, rep = wall_closets(lay, rules)
    assert new is None and rep["failed"] == [{"space_id": "bed", "why": "no_wall"}]


def test_a_room_with_a_walk_in_needs_none(rules):
    labels, specs = _house()
    specs[2] = _spec("wic", "walk_in_closet", host="bed")
    lay = _layout(labels, specs)
    rep = closet_report(lay, rules)
    assert rep["rooms"][0]["status"] == "walk_in" and wall_closet_violation(rep, rules) is None
    assert wall_closets(lay, rules)[0] is None


def test_a_whole_wall_closet_stays(rules):
    labels, specs = _house()
    specs.append(_spec("bed_closet", "closet", host="bed"))
    labels[1:25, 31:35] = 3                                          # already across the whole study wall
    lay = _layout(labels, specs, doors=[_door(1, 0)])
    rep = closet_report(lay, rules)
    assert rep["rooms"][0]["status"] == "ok" and rep["rooms"][0]["closets"][0]["whole_wall"]
    assert wall_closets(lay, rules)[0] is None


def test_a_piece_of_a_wall_joins_the_room_and_is_carved_again(rules):
    labels, specs = _house()
    specs.append(_spec("bed_closet", "closet", host="bed"))
    labels[13:25, 31:35] = 3                                         # half the study wall: a piece
    lay = _layout(labels, specs, doors=[_door(1, 0)])
    rep = closet_report(lay, rules)
    assert rep["rooms"][0]["status"] == "partial" and not rep["rooms"][0]["closets"][0]["whole_wall"]
    assert wall_closet_violation(rep, rules) == "wall_closet:bedroom:partial"
    new, rep2 = wall_closets(lay, rules)
    assert new is not None and rep2["merged"] == ["bed_closet"] and new.node("bed_closet") is None
    after = closet_report(new, rules)
    assert after["rooms"][0]["status"] == "ok" and wall_closet_violation(after, rules) is None


def test_a_piece_that_cannot_join_stays_beside_the_whole_wall_one(rules):
    labels, specs = _house()
    specs.append(_spec("bed_closet", "closet", host="bed"))
    labels[1:13, 35:39] = 3                                          # a closet piece of the bedroom in the study
    lay = _layout(labels, specs, doors=[_door(1, 0)])
    new, rep = wall_closets(lay, rules)
    assert new is not None and not rep["merged"] and rep["carved"][0]["wall"] == "interior"
    after = closet_report(new, rules)
    assert after["rooms"][0]["status"] == "ok"
    s = closet_summary(after)
    assert s["closets"] == 2 and s["whole_wall"] == 1 and s["walls"] == {"interior": 1, "partial": 1}


def test_a_small_room_keeps_its_bed(rules):
    labels = np.full((26, 48), -1, dtype=np.int32)
    labels[1:25, 1:9] = 0
    labels[1:21, 9:31] = 1                                           # 11 x 10 ft: the bed fills it
    labels[1:25, 31:47] = 2
    labels[21:25, 9:31] = 2
    specs = [_spec("hall", "hall", circ=True), _spec("bed", "bedroom"), _spec("study", "study")]
    new, rep = wall_closets(_layout(labels, specs, doors=[_door(1, 0)]), rules)
    assert new is None and rep["failed"][0]["why"] == "no_wall"


# ------------------------------------------------------------------ S2.1: the bedroom sized for its closet


def test_the_program_closet_is_the_wall_closet(rules):
    reg = load_registry()
    assert reg.get("space.wall_closets.in_room_program").value is True
    assert wall_settings(rules)["in_room_program"]


def test_a_bedroom_holds_its_bed_and_its_closet(rules):
    from spaceplan.modules.stacking.lib.unit_layout import UnitLayout

    bed, suite = _spec("bed", "bedroom"), _spec("suite", "primary_suite")
    me = SimpleNamespace(rules=rules, unit=SimpleNamespace(specs=[bed, suite, _spec("wic", "walk_in_closet",
                                                                                    host="suite")]))
    got = UnitLayout._with_wall_closet(me, bed, [(11.0, 10.0)])
    assert set(got) == {(11.0, 12.0), (13.0, 10.0)}
    assert UnitLayout._with_wall_closet(me, suite, [(12.5, 10.0)]) == [(12.5, 10.0)]   # a walk-in: no wall closet
