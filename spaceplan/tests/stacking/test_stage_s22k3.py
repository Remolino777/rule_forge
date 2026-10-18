"""Step V6.8 k3 (client 2026-10-17, mandatory): every room and service space a rectangle; the hall and the foyer may be
composite (reading taken, to be confirmed); an L unit cut along the lines of its inner corners in S2.1; on the
composed floor the part of a space outside its rectangle goes to a hall or foyer, to a neighbour that stays a
rectangle, to a closet, out on the facade or, a sliver, to the wall; the check is hard."""

from types import SimpleNamespace

import numpy as np
import pytest

from spaceplan.core.lib.catalog import load_catalog
from spaceplan.modules.design.lib.design_registry import load_registry
from spaceplan.modules.stacking.lib.door_placement import FloorLayout
from spaceplan.modules.stacking.lib.rect_spaces import rect_summary, rect_violation, rectify
from spaceplan.modules.stacking.lib.space_rules import (
    design_view,
    load_crc_ruleset,
    load_openings_ruleset,
    must_be_rect,
    rect_settings,
    space_rules,
)
from spaceplan.modules.stacking.lib.stacking_catalog import load_stacking_catalog
from spaceplan.modules.stacking.lib.stair_access import load_client_ruleset
from spaceplan.modules.stacking.lib.stair_rules import load_stair_ruleset
from spaceplan.modules.stacking.lib.unit_frame import OUT, SpaceSpec
from spaceplan.modules.stacking.lib_aux.rect_grid import (
    candidate_rects,
    corner_lines,
    is_rect,
    merge_snap,
    rect_pieces,
    split_lines,
)

RES = 0.5


@pytest.fixture(scope="module")
def rules():
    scat, cat = load_stacking_catalog(), load_catalog()
    return space_rules(scat, cat, load_crc_ruleset(), load_openings_ruleset(), load_stair_ruleset(),
                       load_client_ruleset(), design_view())


def _spec(sid, st, host=None, circ=False, fixed=False, min_sqft=0.0):
    return SpaceSpec(sid, st, "private", "u", 100.0, min_sqft, 0.0, not circ, circ, circ, frozenset(), host, fixed)


def _layout(labels, specs, level=1):
    floor = SimpleNamespace(res=RES, level=level, landing=np.zeros(labels.shape, dtype=bool),
                            stair=np.zeros(labels.shape, dtype=bool))
    return FloorLayout(floor, (), list(specs), labels, 0, 0)


# ------------------------------------------------------------------ registry


def test_the_registry_holds_the_rectangle_decision(rules):
    reg = load_registry()
    p = reg.get("space.rectangles.enabled")
    assert p.value is True and p.kind == "hard" and p.who == "client"
    assert set(reg.get("space.rectangles.composite_types").value) == {"hall", "foyer"}
    st = rect_settings(rules)
    assert st["hard"] and st["split"] and st["order"][0] == "circulation" and st["order"][-1] == "chase"


def test_the_composite_types_and_fixed_spaces_are_free(rules):
    st = rect_settings(rules)
    assert must_be_rect(_spec("b", "bedroom"), st) and must_be_rect(_spec("c", "closet"), st)
    assert not must_be_rect(_spec("h", "hall", circ=True), st)
    assert not must_be_rect(_spec("f", "foyer", circ=True), st)
    assert not must_be_rect(_spec("g", "garage_2car", fixed=True), st)
    assert not must_be_rect(_spec("s", "stair", fixed=True), st)


def test_an_empty_registry_is_pre_k3():
    values, kinds = design_view()
    off = SimpleNamespace(design={**values, "space.rectangles.enabled": False}, design_kinds=kinds)
    assert rect_settings(off) is None


# ------------------------------------------------------------------ grid


def _l_mask():
    m = np.zeros((10, 10), dtype=bool)
    m[0:10, 0:4] = True                                    # an L: a column 4 wide and a foot 3 high
    m[7:10, 4:10] = True
    return m


def test_rectangles_of_a_mask():
    m = _l_mask()
    assert not is_rect(m) and is_rect(m[0:10, 0:4]) and not is_rect(np.zeros((3, 3), dtype=bool))
    assert corner_lines(m) == ((4,), (7,))
    cands = candidate_rects(m)
    assert cands[0] == (0, 4, 0, 10)                        # largest first
    assert (0, 10, 7, 10) in cands                          # the foot, below the corner line
    pieces = rect_pieces(m, cands[0])
    assert len(pieces) == 1 and is_rect(pieces[0]) and int(pieces[0].sum()) == 18


def test_an_l_unit_gives_its_corner_lines_as_cuts():
    m = np.zeros((14, 14), dtype=bool)
    m[2:12, 2:12] = _l_mask()
    got = split_lines(m, (2, 12, 2, 12), 6)
    assert got == ((6,), (9,), 6)
    assert split_lines(m[2:12, 2:6], (0, 4, 0, 10), 6) is None           # a rectangle: nothing to split
    assert merge_snap(((1,), (), 2), got) == ((1, 6), (9,), 6) and merge_snap(None, got) == got


# ------------------------------------------------------------------ the floor pass


def test_an_l_room_gives_its_foot_to_the_hall(rules):
    labels = np.full((24, 24), -1, dtype=np.int32)
    labels[1:23, 1:12] = 0                                 # hall on the left
    labels[1:23, 12:23] = 1                                # bedroom 5.5 x 11 ft
    labels[17:23, 6:12] = 1                                # its foot bites the hall: an L
    specs = [_spec("hall", "hall", circ=True), _spec("bed", "bedroom")]
    lay = _layout(labels, specs)
    assert rect_violation(lay, rules) == "rect:bedroom"
    new, report = rectify(lay, rules)
    assert new is not None and not report["left"]
    assert is_rect(new.labels == new.node("bed")) and rect_violation(new, rules) is None
    assert report["moves"][0]["to"] == "circulation" and report["moves"][0]["into"] == "hall"
    assert rect_summary(report)["by_destination"] == {"circulation": 9.0}


def test_a_leftover_completes_a_neighbour_or_leaves_on_the_facade(rules):
    labels = np.full((24, 24), -1, dtype=np.int32)
    labels[1:15, 1:12] = 0                                 # a study
    labels[1:7, 12:23] = 2                                 # a bath
    labels[7:23, 12:23] = 1                                # a bedroom below the bath ...
    labels[15:23, 1:12] = 1                                # ... in an L under the study
    specs = [_spec("study", "study"), _spec("bed", "bedroom"), _spec("bath", "bathroom")]
    new, report = rectify(_layout(labels, specs), rules)
    assert new is not None and not report["left"] and rect_violation(new, rules) is None
    assert {m["to"] for m in report["moves"]} == {"neighbour"}
    labels2 = np.full((24, 24), -1, dtype=np.int32)
    labels2[1:23, 1:12] = 0                                # bedroom with a 1 ft lip on the facade
    labels2[1:3, 12:20] = 0
    new2, report2 = rectify(_layout(labels2, [_spec("bed", "bedroom")]), rules)
    assert new2 is not None and report2["moves"][0]["to"] == "open_air" and new2.open_air
    assert (new2.labels == OUT).sum() > (labels2 == OUT).sum()


def test_a_leftover_without_destination_is_a_violation(rules):
    labels = np.full((30, 30), -1, dtype=np.int32)
    labels[1:29, 1:29] = 1                                 # a fixed garage around it
    labels[2:24, 2:14] = 0                                 # a bedroom in an L inside the house, both parts too
    labels[14:24, 14:28] = 0                               # large for a closet
    specs = [_spec("bed", "bedroom"), _spec("g", "garage_2car", fixed=True)]
    lay = _layout(labels, specs)
    new, report = rectify(lay, rules)
    assert new is None and report["left"] and report["left"][0]["space_id"] == "bed"
    assert rect_violation(lay, rules) == "rect:bedroom"


def test_the_rectangle_keeps_the_minimum_area(rules):
    labels = np.full((24, 24), -1, dtype=np.int32)
    labels[1:23, 1:12] = 0
    labels[1:23, 12:23] = 1
    labels[17:23, 6:12] = 1
    specs = [_spec("hall", "hall", circ=True), _spec("bed", "bedroom", min_sqft=70.0)]   # 60.5 sq ft rectangle
    new, report = rectify(_layout(labels, specs), rules)
    assert report["left"] and report["left"][0]["space_id"] == "bed"
