"""Step 9a (2026-10-10): balanced split between floors and trimmed maximum against the design footprint."""

import pytest

from spaceplan.core.lib.catalog import load_catalog
from spaceplan.modules.areas.lib.floor_balance import (
    BALANCE_KIND,
    balance_split,
    balanced,
    fits_ground,
    min_ground,
)
from spaceplan.modules.areas.lib.sensitivity import EXCEEDS, ONE, SPLIT, TWO, classify
from spaceplan.modules.areas.lib.vertical_split import split_program
from spaceplan.pipeline.main.run_area_analysis import run_area_matrix

CAT = load_catalog()
V1 = next(s for s in CAT.data["vertical_schemes"]["schemes"] if s["scheme_id"] == "V1")


def space(sid, st, zone, area, **kw):
    return {"space_id": sid, "space_type": st, "zone": zone, "target_area_sqft": area, **kw}


def program():
    return {"spaces": [
        space("garage", "garage_2car", "garage", 420), space("living", "living_room", "social", 320),
        space("kitchen", "kitchen", "kitchen", 185), space("dining", "dining_room", "social", 170),
        space("family", "family_room", "social", 345), space("study", "study", "social", 130),
        space("hall", "hall", "circulation", 90),
        space("suite", "primary_suite", "private", 290, household_role="primary"),
        space("bed1", "bedroom", "private", 140, household_role="child"),
        space("bed2", "bedroom", "private", 140, household_role="child"),
        space("bath", "bathroom", "private", 55)]}


@pytest.fixture(scope="module")
def v1():
    return split_program(CAT, program(), V1, {})


def test_split_that_fits_is_untouched(v1):
    assert balance_split(CAT, program(), v1, v1.ground + 1) is v1
    assert balance_split(CAT, program(), v1, None) is v1


def test_family_room_goes_up_first(v1):
    sp = balance_split(CAT, program(), v1, v1.ground - 100)
    assert balanced(sp) == ["family"] and sp.floor_of["family"] == 1
    assert sp.ground < v1.ground and sp.gross == pytest.approx(v1.gross)
    e = next(x for x in sp.exceptions if x.get("kind") == BALANCE_KIND)
    assert e["rule_id"] == "VB01-GROUND-BALANCE" and "family_room" in e["reason"]


def test_order_and_kitchen_never_moves(v1):
    sp = balance_split(CAT, program(), v1, 0.0)
    assert balanced(sp)[:1] == ["family"]
    for sid in ("garage", "kitchen", "living", "dining"):
        assert sp.floor_of[sid] == 0
    assert sp.upper <= sp.ground + 1e-6  # the upper floor never becomes larger


def test_floor_preference_is_kept():
    p = program()
    p["spaces"][4]["floor_preference"] = 0
    sp = balance_split(CAT, p, split_program(CAT, p, V1, {}), 0.0)
    assert sp.floor_of["family"] == 0 and "family" not in balanced(sp)


def test_hosted_spaces_follow_the_host():
    p = program()
    p["spaces"].append(space("closet_f", "closet", "private", 12, host_space_id="family"))
    base = split_program(CAT, p, V1, {})
    sp = balance_split(CAT, p, base, base.ground - 50)
    assert sp.floor_of["closet_f"] == 1


def test_min_ground_and_split_class(v1):
    g = min_ground(CAT, program(), {})
    assert g is not None and g < v1.ground
    assert classify(2500, 1814, 3000, 88, ground_min_sqft=1900) == SPLIT
    assert classify(2500, 1814, 3000, 88, ground_min_sqft=1700) == TWO
    assert classify(1500, 1814, 3000, 88, ground_min_sqft=1900) == ONE
    assert classify(2950, 1814, 3000, 88, ground_min_sqft=1700) == EXCEEDS


@pytest.fixture(scope="module")
def interior():
    return run_area_matrix(lots=["interior_50x100"],
                           households=[("multigenerational", None), ("empty_nest", "anglo")], zone_top=0)


def test_every_maximum_has_a_feasible_scheme(interior):
    fp = interior["lots"][0]["budget"]["footprint_design_sqft"]
    best = [c for c in interior["cells"] if c["profile"] == "maximum" and c["best"]]
    assert {c["household_id"] for c in best} == {"multigenerational.none", "empty_nest.anglo"}
    for c in best:
        assert c["ground_sqft"] <= fp + 1e-6 and c["status"] in ("fits", "fits_small_garden")


def test_multigenerational_balances_and_empty_nest_is_trimmed(interior):
    by_h = {c["household_id"]: c for c in interior["cells"] if c["profile"] == "maximum" and c["best"]}
    assert by_h["multigenerational.none"]["balanced_up"] == ["family_room"]
    trim = by_h["empty_nest.anglo"]["maximum_trim"]
    assert trim and trim["fits"] and trim["to_step"] < trim["from_step"]
    assert by_h["empty_nest.anglo"]["gross_sqft"] < trim["from_gross_sqft"]
    assert by_h["empty_nest.anglo"]["split"]["exceptions"][0]["reason"].startswith("floor_preference")


def test_fits_ground(v1):
    assert fits_ground(v1, v1.ground) and not fits_ground(v1, v1.ground - 1)
