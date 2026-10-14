"""Step 6.7a S2.2i: upper floor rules: main bedroom with a walk-in, doors that slide off another doorway, bedrooms
near the stair, baths on the side walls, and the stair opening (the covered first treads)."""

import pytest
from shapely.geometry import box

from spaceplan.core.lib.catalog import load_catalog
from spaceplan.modules.design.lib.design_registry import load_registry
from spaceplan.modules.stacking.lib.floor_frame import CellFloors, stair_cover_ft, with_stair_opening
from spaceplan.modules.stacking.lib.program_adjust import adjust_program
from spaceplan.modules.stacking.lib.stacking_catalog import load_stacking_catalog
from spaceplan.modules.stacking.lib.stair_access import load_client_ruleset
from spaceplan.modules.stacking.lib_aux.stair_geometry import covered_start


@pytest.fixture(scope="module")
def values():
    return load_registry().baseline()


def test_registry_carries_the_upper_floor_rules(values):
    reg = load_registry()
    assert reg.self_check() == []
    assert values["space.master_bedroom.enabled"] and values["space.master_bedroom.walk_in"]
    assert values["door.conflicts.shift_on_placement"]
    assert values["circulation.upper_rooms.bed_near_weight"] > 0
    assert values["circulation.upper_rooms.bath_walls"] == ["low_x", "high_x"]
    assert values["structure.stair_opening"] and values["structure.floor_depth_in"] == 12.0


# ------------------------------------------------------------------ case 5: the stair opening


def _s1(risers=16, riser=7.5, tread=10.0):
    return {"stair": {"risers": risers, "riser_in": riser, "tread_in": tread, "rules": {"headroom_min_in": 80.0}}}


def test_the_first_treads_keep_their_headroom_under_the_upper_floor():
    assert stair_cover_ft(_s1(), 12.0) == pytest.approx(2.5)        # 120 - 12 - 80 = 28 in: 3 risers
    assert stair_cover_ft(_s1(16, 7.75), 12.0) == pytest.approx(10.0 / 3)
    assert stair_cover_ft(_s1(12, 7.5), 12.0) == 0.0                 # a short rise: nothing covered


def test_covered_start_is_cut_from_the_start_edge():
    footprint, start = box(0, 0, 3, 12.5), box(0, -3, 3, 0)          # one steps on at y = 0
    c = covered_start(footprint, start, 2.5)
    assert c.bounds == pytest.approx((0, 0, 3, 2.5))
    assert covered_start(footprint, box(10, 10, 12, 12), 2.5) is None


def test_with_stair_opening_keeps_the_rest_open():
    floors = CellFloors(ground=box(0, 0, 40, 40), upper=box(0, 0, 40, 30), garage=None, stair=box(10, 5, 13, 17.5),
                        bottom_zone=box(10, 2, 13, 5), top_zone=box(10, 17.5, 13, 20.5), half_bath=None,
                        vestibule=None)
    out = with_stair_opening(floors, _s1(), 12.0)
    assert out.stair_opening.bounds == pytest.approx((10, 7.5, 13, 17.5))
    assert with_stair_opening(floors, _s1(), None) is floors


# ------------------------------------------------------------------ case 1: the main bedroom


def _cell(bedrooms):
    rows = [{"space_id": sid, "space_type": "bedroom", "zone": "private", "household_role": "general",
             "host_space_id": None, "floor": 1, "area_sqft": a} for sid, a in bedrooms]
    rows += [{"space_id": "living", "space_type": "living_room", "zone": "social", "household_role": "general",
              "host_space_id": None, "floor": 0, "area_sqft": 300.0}]
    return {"floors": 2, "space_split": rows, "gross_sqft": 2000.0, "split": {}}


def test_the_largest_upper_bedroom_becomes_the_main_one_with_a_walk_in(values):
    cat, scat, crs = load_catalog(), load_stacking_catalog(), load_client_ruleset()
    out, rep = adjust_program(_cell([("bedroom_primary", 130.0), ("bedroom_kid", 130.0)]), 2000.0, cat, scat, crs,
                              values)
    rows = {r["space_id"]: r for r in out["space_split"]}
    walk = [r for r in out["space_split"] if r["space_type"] == "walk_in_closet"]
    assert len(walk) == 1 and walk[0]["host_space_id"] == "bedroom_primary"
    assert rows["bedroom_primary"]["area_sqft"] > rows["bedroom_kid"]["area_sqft"]
    assert rows["bedroom_kid"]["area_sqft"] >= float(cat.space_type("bedroom")["area"]["min"]) - 1e-6
    assert rep["master"][0]["bedroom"] == "bedroom_primary" and out["gross_sqft"] == 2000.0   # stage S1 unchanged
    off, rep2 = adjust_program(_cell([("bedroom_a", 130.0), ("bedroom_b", 130.0)]), 2000.0, cat, scat, crs,
                               {**values, "space.master_bedroom.enabled": False})
    assert "master" not in rep2 and not [r for r in off["space_split"] if r["space_type"] == "walk_in_closet"]
