"""Step 6.7a S2.2h: the upper hall trimmed to what it serves (vestibule, linen closet, remainders to closets, rooms or
roof)."""

from types import SimpleNamespace

import numpy as np
import pytest

from spaceplan.modules.design.lib.design_registry import load_registry
from spaceplan.modules.stacking.lib.door_placement import Door
from spaceplan.modules.stacking.lib.hall_trim import (
    dead_end_sqft,
    door_gaps,
    remainders,
    trim_hall,
    trim_settings,
)
from spaceplan.modules.stacking.lib.unit_frame import OUT, SpaceSpec
from spaceplan.modules.stacking.lib_aux.hall_geometry import rectangles, ring, run_cells, sides
from spaceplan.modules.stacking.lib_aux.space_grid import WallRun


def _spec(sid, st, host=None, circ=False):
    return SpaceSpec(sid, st, "private", "u", 100.0, 0.0, 0.0, not circ, circ, circ, frozenset(), host)


@pytest.fixture(scope="module")
def values():
    return load_registry().baseline()


def _rules(values, **over):
    return SimpleNamespace(design={**values, **over}, closet_min_sqft=6.0, closet_min_side_ft=2.0, closet_type="closet",
                           sleeping_types=frozenset({"bedroom", "primary_suite"}))


# ------------------------------------------------------------------ data


def test_registry_carries_the_upper_hall(values):
    reg = load_registry()
    assert reg.self_check() == []
    assert values["circulation.upper_hall.vestibule_min_ft"] == 3.0
    assert values["circulation.upper_hall.vestibule_pref_ft"] == 4.0
    assert values["circulation.upper_hall.tail_one_room"] == "roof"
    assert values["circulation.upper_hall.walk_in_from_ft"] == 5.0
    assert reg.kinds()["circulation.upper_hall.vestibule_min_ft"] == "hard"
    st = trim_settings(_rules(values))
    assert st["linen_ft"] == 2.0 and st["closet_ft"] == 2.0 and st["linen"]
    assert trim_settings(_rules(values, **{"circulation.upper_hall.trim": False})) is None


def test_the_llm_reaches_the_upper_hall():
    from spaceplan.modules.design.lib import design_profile as dp
    from spaceplan.modules.design.lib.llm_tools import dispatch

    reg = load_registry()
    prof = dp.new_profile(reg, "llm")
    res, _ = dispatch(reg, prof, "get_criteria", {"group": "structure"}, "llm", "2026-10-12")
    assert "circulation.upper_hall.vestibule_min_ft" in {r["id"] for r in res["rules"]}
    res, prof = dispatch(reg, prof, "set_criteria", {"group": "structure", "changes": {
        "circulation.upper_hall.tail_one_room": "closet"}, "reason": "no roof notches"}, "llm", "2026-10-12")
    assert res["ok"] and dp.effective_values(reg, prof)["circulation.upper_hall.tail_one_room"] == "closet"


# ------------------------------------------------------------------ geometry


def test_hall_geometry():
    m = np.zeros((6, 8), dtype=bool)
    m[1:3, 0:8] = True
    m[3:6, 5:7] = True
    assert rectangles(m) == [(0, 8, 1, 3), (5, 7, 3, 6)]
    lab = np.arange(48).reshape(6, 8)
    lo, hi = sides(lab, (2, 5, 1, 3), "x")
    assert list(lo) == [2, 3, 4] and list(hi) == [26, 27, 28]
    assert len(ring(lab, (2, 5, 1, 3))) == 10
    assert run_cells((6, 8), True, 3, 1.0, 3.0, True)[1:3, 3].all()


# ------------------------------------------------------------------ the trim on a small floor
#
#   row 0      outside (facade)
#   rows 1-8   bed A (cols 0-11) | hall (cols 12-18, 3.5 ft) ... the hall runs down to row 23
#   rows 12-31 bed B on the left of the hall; bed C on its right (rows 1-31)
#   the stair lands at the top of the hall; doors near it; the hall below row 16 is dead


def _floor():
    ny, nx = 34, 31
    lab = np.full((ny, nx), OUT, dtype=np.int32)
    specs = [_spec("hall", "hall", circ=True), _spec("bed_a", "bedroom"), _spec("bed_b", "bedroom"),
             _spec("bed_c", "bedroom")]
    lab[1:32, 12:19] = 0                 # hall, 7 cells (3.5 ft) wide, rows 1..31
    lab[1:12, 0:12] = 1
    lab[12:32, 0:12] = 2
    lab[1:32, 19:30] = 3
    landing = np.zeros((ny, nx), dtype=bool)
    landing[1:4, 12:19] = True
    floor = SimpleNamespace(level=1, res=0.5, landing=landing)
    doors = [Door(1, 0, "door", WallRun(1, 0, True, 12, 7, 9), 7.0, 9.0),
             Door(2, 0, "door", WallRun(2, 0, True, 12, 13, 15), 13.0, 15.0),
             Door(3, 0, "door", WallRun(0, 3, True, 19, 13, 15), 13.0, 15.0)]
    return SimpleNamespace(floor=floor, labels=lab, specs=specs, doors=doors, options=(), root=0, landing_node=0,
                           open_air=[])


def test_remainders_and_dead_end(values):
    lay = _floor()
    rem = remainders(lay, 0.5)
    assert len(rem) == 1
    (i0, i1, j0, j1), ax, inner = rem[0]
    assert (i0, i1) == (12, 19) and j0 == 16 and j1 == 32 and ax == "y" and inner == "lo"
    assert dead_end_sqft(lay, 0.5) == pytest.approx(7 * 16 * 0.25)
    gaps = door_gaps(lay, _rules(values))
    assert gaps == sorted(gaps) and gaps[0] == pytest.approx(1.5, abs=0.05)        # A's door 1.5 ft below the landing


def test_trim_makes_a_linen_and_the_closets_of_the_rooms_beside_it(values):
    lay = _floor()
    out, rep = trim_hall(lay, _rules(values))
    assert out is not None and rep["dead_end_before_sqft"] == pytest.approx(28.0)
    types = {s.space_id: s.space_type for s in out.specs}
    assert "hall_linen" in types
    linen = out.labels == next(k for k, s in enumerate(out.specs) if s.space_id == "hall_linen")
    rows, cols = np.nonzero(linen)
    assert cols.min() == 12 and cols.max() == 18 and rows.max() - rows.min() + 1 == 4   # wall to wall, 2 ft deep
    hosts = {c["host"] for c in rep["closets"]}
    assert hosts == {"bed_b", "bed_c"}                         # the rest between B and C: one closet each
    assert rep["roof_sqft"] == 0.0 and not (out.labels[16:32, 12:19] == 0).any()


def test_a_remainder_beside_one_room_on_the_facade_becomes_roof(values):
    lay = _floor()
    lay.labels[1:32, 19:30] = OUT                              # no room C: the hall's right side is the facade
    lay.doors = lay.doors[:2]
    lay.specs = lay.specs[:3]
    out, rep = trim_hall(lay, _rules(values))
    assert rep["roof_sqft"] > 0 and out.open_air and out.open_air[0][0].space_type == "upper_roof"
    _, rep2 = trim_hall(lay, _rules(values, **{"circulation.upper_hall.tail_one_room": "closet"}))
    assert rep2["roof_sqft"] == 0 and rep2["closets"]
