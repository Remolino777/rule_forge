"""Stage S1.2 of the stacking module (step 6.7a): the stair placed from the main door against the permitted walls,
natural light (K06, no skylight), U stairs at least 2.5 m wide (K08), arrival and half bath as preferences, the
stair hall in S2 and the choice in three levels. Cases T1-T8 of the client's review (2026-10-10)."""

from dataclasses import replace

import pytest
from shapely.geometry import box

from spaceplan.core.lib.catalog import load_catalog
from spaceplan.modules.stacking.lib.access_core import (
    NONE,
    WINDOW,
    entry_door,
    free_cut_off,
    permitted_walls,
    stair_light,
    well_of,
)
from spaceplan.modules.stacking.lib.access_rank import rank_stair_candidates
from spaceplan.modules.stacking.lib.access_stair import access_candidates
from spaceplan.modules.stacking.lib.cell_geometry import S1Context, _stair_cfg
from spaceplan.modules.stacking.lib.core_zoning import FloorSearch
from spaceplan.modules.stacking.lib.floor_frame import (
    FAMILY_ROOM,
    HALL,
    VESTIBULE,
    CellFloors,
    ZoneUnit,
    arrival_of,
    ground_frame,
    upper_arrival,
    upper_frame,
)
from spaceplan.modules.stacking.lib.stacking_catalog import load_stacking_catalog
from spaceplan.modules.stacking.lib.stair import stair_shape
from spaceplan.modules.stacking.lib.stair_access import TOP_RULE, load_client_ruleset, relations, u_min_span_ft
from spaceplan.modules.stacking.lib.stair_rules import load_stair_ruleset, stair_limits
from spaceplan.modules.stacking.lib.zone_cell import s2_context
from spaceplan.modules.stacking.lib.zone_relations import build_matrix

GROUND = box(0, 0, 40, 36)
GARAGE = box(20, 0, 40, 22)
UPPER = box(0, 18, 40, 36)
LOT_SETBACKS = box(-4, -15, 44, 49)       # 4 ft side yards, deep front and rear yards
LOT_PARTY_WALLS = box(0, -15, 40, 49)     # walls on the side lot lines (Latin American row house)


@pytest.fixture(scope="module")
def env():
    scat, catalog = load_stacking_catalog(), load_catalog()
    srs, crs = load_stair_ruleset(), load_client_ruleset()
    limits = stair_limits(srs)
    acc = scat.access_core
    design = {**scat.stair_design, "u_well_gap_ft": acc["void"]["well_ft"], "u_min_span_ft": u_min_span_ft(crs)}
    shapes = {t["stair_id"]: stair_shape(t, scat.levels["floor_to_floor_ft"], limits, design)
              for t in scat.data["stair"]["types"]}
    ctx = S1Context(scat, limits, srs, None, crs, catalog, None, None, 44.0)
    cfg = _stair_cfg(ctx, "hall")
    required = crs.params("K06-STAIR-NATURAL-LIGHT")["required_by_strategy"]
    door = entry_door(GROUND, GARAGE, "right", (0.0, 10.0), acc)
    return {"scat": scat, "catalog": catalog, "srs": srs, "crs": crs, "acc": acc, "shapes": shapes, "cfg": cfg,
            "required": required, "door": door}


def _candidates(env, lot):
    walls = permitted_walls(GROUND, UPPER, GARAGE, lot, env["acc"])
    return access_candidates(UPPER, GROUND, GARAGE, env["door"], walls, env["shapes"], env["cfg"], env["acc"],
                             env["srs"], env["required"])


def test_k08_u_stairs_are_at_least_2_5_m_wide(env):
    assert u_min_span_ft(env["crs"]) == pytest.approx(2.5 / 0.3048)
    for sid in ("u_turn", "u_well"):
        shape = env["shapes"][sid]
        assert min(shape.length_ft, shape.span_ft) >= 2.5 / 0.3048 - 1e-6
    assert env["shapes"]["l_turn"].width_ft == pytest.approx(env["scat"].stair_design["width_ft"])


def test_t1_side_yard_gives_a_lit_side_stair(env):
    found, _ = _candidates(env, LOT_SETBACKS)
    side = [a for a in found if a.strategy == "A"]
    assert side and all(a.light.source == WINDOW for a in side)
    assert {a.stair_id for a in side} <= {"u_turn", "l_turn", "straight", "straight_landing"}


def test_fire_separation_is_measured_at_right_angles(env):
    from spaceplan.modules.stacking.lib.access_core import fire_separation_ft
    from shapely.geometry import LineString

    rear = LineString([(0, 36), (40, 36)])
    assert fire_separation_ft(rear, GROUND, LOT_PARTY_WALLS) == pytest.approx(13.0)
    side = LineString([(0, 18), (0, 36)])
    assert fire_separation_ft(side, GROUND, LOT_SETBACKS) == pytest.approx(4.0)
    assert fire_separation_ft(side, GROUND, LOT_PARTY_WALLS) == pytest.approx(0.0)


def test_t2_party_walls_have_no_side_window(env):
    found, stats = _candidates(env, LOT_PARTY_WALLS)
    side = [a for a in found if a.strategy == "A"]
    assert all(a.light.wall_kind != "side" for a in side)        # no window on a wall that stands on the lot line
    assert stats["A:K06"] > 0                                   # side-wall stairs away from the rear corner fail K06
    assert [a for a in found if a.strategy == "D" and a.light.source == WINDOW]   # the rear facade still lights


def test_t3_door_follows_the_entry_deck(env):
    acc = env["acc"]
    near = entry_door(GROUND, GARAGE, "right", (0.0, 10.0), acc)
    far = entry_door(GROUND, GARAGE, "right", (5.0, 15.0), acc)
    shift = near.segment.centroid.x - far.segment.centroid.x
    assert shift == pytest.approx(5.0)
    assert near.vestibule.within(GROUND.difference(GARAGE).buffer(1e-6))
    assert near.swing.within(near.vestibule.buffer(1e-6))      # the leaf swings inside the vestibule


def test_t4_a_stair_that_cuts_the_floor_is_rejected(env):
    wall_to_wall = box(0, 17, 20, 20)                           # from the side wall to the garage
    cut = free_cut_off(GROUND, wall_to_wall.union(GARAGE), env["door"].vestibule)
    assert cut > env["acc"]["circulation"]["max_cut_off_fraction"]
    assert free_cut_off(GROUND, box(0, 17, 3, 29).union(GARAGE), env["door"].vestibule) == pytest.approx(0.0)


def test_t5_u_void_is_kept_and_no_skylight_lights_it(env):
    shape = env["shapes"]["u_well"]
    well = well_of(shape.geometry, env["acc"]["void"]["well_ft"])
    assert well is not None and well.area >= env["acc"]["void"]["well_ft"] * 3.0
    assert stair_light(shape.geometry, [], env["srs"], 2.0, well, skylight=False).source == NONE
    from shapely.affinity import translate

    floors = CellFloors(GROUND, UPPER, GARAGE, translate(shape.geometry.footprint, 1, 19), box(1, 16, 4, 19),
                        box(1, 30, 4, 33), None, None, void=translate(well, 1, 19))
    unit = [ZoneUnit("private", "private", ("bedroom",), frozenset({"bedroom"}), 400.0, 9.0)]
    with_void = upper_frame(floors, unit, 0.5, [])
    without = upper_frame(replace(floors, void=None), unit, 0.5, [])
    assert without.grid.free_cells - with_void.grid.free_cells > 0


def test_t6_small_house_prefers_the_vestibule_over_the_family_room(env):
    rows = [{"space_id": "family_room", "space_type": "family_room", "zone": "social", "floor": 1, "area_sqft": 250},
            {"space_id": "primary_suite", "space_type": "primary_suite", "zone": "private", "floor": 1, "area_sqft": 290}]
    k01 = env["crs"].params(TOP_RULE)
    arr = upper_arrival(env["catalog"], env["scat"].s2, env["scat"].stair_access, rows, k01)
    assert arr["small_house"] and arr["order"] == [VESTIBULE, HALL, FAMILY_ROOM]
    hall = ZoneUnit("circulation", "circulation", (), frozenset(), 60.0, 3.5)
    family = ZoneUnit("social", "social", ("family_room",), frozenset({"family_room"}), 250.0, 11.0)
    assert arrival_of(hall, arr["order"]) == VESTIBULE and arrival_of(family, arr["order"]) == FAMILY_ROOM
    big = upper_arrival(env["catalog"], env["scat"].s2, env["scat"].stair_access,
                        rows + [{"space_id": "bedroom_1", "space_type": "bedroom", "zone": "private", "floor": 1,
                                 "area_sqft": 140}], k01)
    assert big["order"][0] == HALL and big["order"][-1] == FAMILY_ROOM


def test_t7_half_bath_is_a_preference_not_a_filter():
    trials = [{"strategy": "A", "route_ft": 30.0, "occupied_sqft": 61.0, "half_bath": False},
              {"strategy": "A", "route_ft": 31.0, "occupied_sqft": 62.0, "half_bath": True},
              {"strategy": "B", "route_ft": 26.0, "occupied_sqft": 54.0, "half_bath": True}]
    ranked = rank_stair_candidates(trials, 6.0, ["A", "D", "C", "B"])
    assert len(ranked) == 3                                      # nobody is discarded for lacking a half bath
    assert ranked[0].trial is trials[1]                          # strategy first, then the half bath
    far = rank_stair_candidates(trials, 2.0, ["A", "D", "C", "B"])
    assert far[0].trial is trials[2]                             # outside the tolerance the shorter route wins


def test_t8_no_feasible_candidate_is_reported_not_invented(env):
    assert rank_stair_candidates([{"strategy": "A", "route_ft": None, "occupied_sqft": 60.0}], 6.0, ["A"]) == []
    tiny_upper = box(0, 30, 6, 36)
    walls = permitted_walls(GROUND, tiny_upper, GARAGE, LOT_SETBACKS, env["acc"])
    found, _ = access_candidates(tiny_upper, GROUND, GARAGE, env["door"], walls, env["shapes"], env["cfg"],
                                 env["acc"], env["srs"], env["required"])
    assert found == []


def test_stair_hall_rejects_a_stair_inside_the_living_room(env):
    crs, catalog, scat = env["crs"], env["catalog"], env["scat"]
    ctx = s2_context(scat, catalog, crs, build_matrix(catalog, relations(crs), scat.s2["pair_default_weights"]))
    stair = box(10, 26, 13, 34)
    floors = CellFloors(GROUND, UPPER, GARAGE, stair, box(10, 23, 13, 26), box(10, 34, 13, 36), None, None)
    units = [ZoneUnit("circulation", "circulation", ("foyer",), frozenset({"foyer"}), 120.0, 4.0),
             ZoneUnit("social", "social", ("living_room",), frozenset({"living_room"}), 600.0, 11.0)]
    frame = ground_frame(floors, units, 0.5, "storage", [])
    search = FloorSearch(frame, ctx.ground_rules, ctx.matrix)
    i0, i1, j0, j1 = search.bbox
    # circulation along the front, living room around the stair
    inside = ((i0, i1, j0, j0 + 10), (i0, i1, j0 + 10, j1))
    assert search._stair_hall(inside) is not None
    # circulation column beside the stair
    beside = ((27, 35, j0, j1), (i0, 21, j0, j1))          # stair cells are columns 21-26
    assert search._stair_hall(beside) is None


def test_stair_hall_rejects_a_stair_enclosed_by_one_private_zone(env):
    crs, catalog, scat = env["crs"], env["catalog"], env["scat"]
    ctx = s2_context(scat, catalog, crs, build_matrix(catalog, relations(crs), scat.s2["pair_default_weights"]))
    stair = box(10, 26, 13, 34)
    floors = CellFloors(GROUND, UPPER, GARAGE, stair, box(10, 23, 13, 26), box(10, 34, 13, 36), None, None)
    units = [ZoneUnit("circulation", "circulation", ("foyer",), frozenset({"foyer"}), 120.0, 4.0),
             ZoneUnit("private", "private", ("bedroom",), frozenset({"bedroom"}), 600.0, 9.0)]
    frame = ground_frame(floors, units, 0.5, "storage", [])
    search = FloorSearch(frame, ctx.ground_rules, ctx.matrix)
    i0, i1, j0, j1 = search.bbox
    # circulation only at the stair's start (front), the bedroom zone wraps the other three sides
    enclosed = ((i0, i1, j0, 53), (i0, i1, 53, j1))              # stair rows start at 53 (y = 26 ft)
    assert search._stair_hall(enclosed) == "hall:inside_private"
