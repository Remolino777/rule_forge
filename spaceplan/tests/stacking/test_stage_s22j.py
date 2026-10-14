"""Step 6.7a S2.2j: the bedrooms (client 2026-10-13 23:21-23:30): the own bath through the walk-in, the in-room path
never crossing the bed, the closet and bath by the entry, the main bedroom the largest with a king bed, hinged leaves
always on a wall (narrow leaves for baths and walk-ins), no thin strips, the bath closet off the shower side, and the
guest room only with a shared bath."""

from types import SimpleNamespace

import numpy as np
import pytest

from spaceplan.core.lib.catalog import load_catalog
from spaceplan.modules.design.lib.design_registry import load_registry
from spaceplan.modules.stacking.lib.bath_fixtures import bath_fixtures, wet_keep_out
from spaceplan.modules.stacking.lib.door_placement import Door, FloorLayout, door_choices, walk_through_bath
from spaceplan.modules.stacking.lib.program_adjust import adjust_program, program_fallbacks
from spaceplan.modules.stacking.lib.room_circulation import bed_cells, room_paths
from spaceplan.modules.stacking.lib.space_rules import (
    design_view,
    load_crc_ruleset,
    load_openings_ruleset,
    space_rules,
)
from spaceplan.modules.stacking.lib.stacking_catalog import load_stacking_catalog
from spaceplan.modules.stacking.lib.stair_access import load_client_ruleset, relations
from spaceplan.modules.stacking.lib.stair_rules import load_stair_ruleset
from spaceplan.modules.stacking.lib.strips import clean_strips, floor_strips
from spaceplan.modules.stacking.lib.unit_frame import SpaceSpec, roles_of
from spaceplan.modules.stacking.lib.unit_layout import master_largest
from spaceplan.modules.stacking.lib.zone_relations import build_matrix
from spaceplan.modules.stacking.lib_aux.room_paths import bed_fits, bed_places, passable
from spaceplan.modules.stacking.lib_aux.space_grid import WallRun
from spaceplan.modules.stacking.lib_aux.strip_grid import strip_cells, strip_parts

RES = 0.5


@pytest.fixture(scope="module")
def values():
    return load_registry().baseline()


@pytest.fixture(scope="module")
def catalog():
    return load_catalog()


@pytest.fixture(scope="module")
def rules():
    scat, cat = load_stacking_catalog(), load_catalog()
    return space_rules(scat, cat, load_crc_ruleset(), load_openings_ruleset(), load_stair_ruleset(),
                       load_client_ruleset(), design_view())


@pytest.fixture(scope="module")
def matrix(catalog):
    return build_matrix(catalog, relations(load_client_ruleset()), load_stacking_catalog().s2["pair_default_weights"])


def _spec(sid, st, host=None, circ=False, master=False, fixed=False, matrix=None):
    roles = roles_of(matrix, st) if matrix is not None else frozenset()
    return SpaceSpec(sid, st, "private", "u", 100.0, 0.0, 0.0, not circ, circ, circ, roles, host, fixed,
                     master=master)


def _layout(labels, specs, doors=(), level=1):
    floor = SimpleNamespace(res=RES, level=level, landing=np.zeros(labels.shape, dtype=bool),
                            stair=np.zeros(labels.shape, dtype=bool))
    lay = FloorLayout(floor, (), list(specs), labels, 0, 0)
    lay.doors = list(doors)
    return lay


# ------------------------------------------------------------------ data


def test_registry_carries_the_bedroom_rules(values):
    reg = load_registry()
    kinds = reg.kinds()
    assert reg.self_check() == []
    assert kinds["space.bedroom.furniture_w_ft"] == "hard" and kinds["space.primary_suite.furniture_w_ft"] == "hard"
    assert values["space.master_bedroom.bed"] == "king" and values["space.master_bedroom.furniture_w_ft"] == 12.5
    assert values["space.master_bedroom.largest"] and kinds["space.master_bedroom.largest"] == "hard"
    assert values["space.policy.walk_through_scope"] == ["primary_suite", "master_bedroom"]
    assert values["space.policy.walk_through_fallback"] == "closet"
    assert values["circulation.in_room.path_width_ft"] == 3.0 and kinds["circulation.in_room.enabled"] == "hard"
    assert values["door.leaf.support_required"] and not values["door.conflicts.off_corner"]
    assert values["door.leaf.narrow_leaf_in"] == 32.0 and "walk_in_closet" in values["door.leaf.narrow_types"]
    assert values["space.strips.min_part_ft"] == 3.0 and values["space.strips.closet_min_part_ft"] == 2.0
    assert values["space.strips.closet_min_front_ft"] == 3.0
    assert values["space.bath_fixtures.closet_not_wet_side"] and values["space.guest_room.fallback"] == "study"


def test_the_llm_reaches_the_bedroom_rules():
    from spaceplan.modules.design.lib import design_profile as dp
    from spaceplan.modules.design.lib.llm_tools import dispatch

    reg = load_registry()
    res, _ = dispatch(reg, dp.new_profile(reg, "llm"), "get_criteria", {"group": "structure"}, "llm", "2026-10-14")
    ids = {r["id"] for r in res["rules"]}
    assert {"circulation.in_room.enabled", "door.leaf.support_required", "space.strips.min_part_ft",
            "space.bath_fixtures.closet_not_wet_side", "space.guest_room.fallback"} <= ids


def test_the_main_bedroom_has_a_king_bed(rules):
    assert rules.furniture_of("bedroom", True) == [(12.5, 10.0)]
    assert rules.furniture_of("bedroom", False) == [(11.0, 10.0)]
    assert rules.furniture_hard_of("bedroom", True) and rules.furniture_hard_of("bedroom", False)
    assert bed_cells(rules, "bedroom", False, RES) == (10, 14, 6, 6)        # 5 x 7 ft bed, 36 in around it
    assert bed_cells(rules, "bedroom", True, RES) == (13, 14, 6, 6)         # 6.5 x 7 ft (king)


# ------------------------------------------------------------------ R1: the own bath through the walk-in


def test_the_main_bedroom_bath_is_reached_through_its_walk_in(rules, matrix):
    main = _spec("bed_main", "bedroom", master=True, matrix=matrix)
    other = _spec("bed_kid", "bedroom", matrix=matrix)
    bath = _spec("bath", "bathroom", host="bed_main", matrix=matrix)
    walk = _spec("wic", "walk_in_closet", host="bed_main", matrix=matrix)
    assert walk_through_bath(rules, bath, main) and not walk_through_bath(
        rules, _spec("b2", "bathroom", host="bed_kid", matrix=matrix), other)
    assert door_choices(rules, matrix, bath, walk, main) == 0
    assert door_choices(rules, matrix, bath, main, main) == 1
    assert rules.walk_through("primary_suite", False) and not rules.walk_through("bedroom", False)


# ------------------------------------------------------------------ R3: the bed and the paths


def test_a_bed_placement_has_its_head_on_a_wall():
    room = np.ones((24, 24), dtype=bool)                  # 12 x 12 ft
    places = bed_places(room, 10, 14, 6, 6)
    assert places and all(p.clear[1] - p.clear[0] <= 24 and p.clear[3] - p.clear[2] <= 24 for p in places)
    for p in places:
        i0, i1, j0, j1 = p.bed
        assert {"low_x": i0 == 0, "high_x": i1 == 24, "low_y": j0 == 0, "high_y": j1 == 24}[p.head]


def test_the_path_never_crosses_the_bed():
    room = np.ones((22, 24), dtype=bool)                  # 12 x 11 ft
    entry = np.zeros_like(room)
    entry[0:6, 0:6] = True                                # entry by the low-x, low-y corner
    closet = np.zeros_like(room)
    closet[16:22, 18:24] = True                           # an inner door in the opposite corner
    assert bed_fits(room, np.zeros_like(room), [entry, closet], 10, 14, 6, 6, 3.0) is not None
    small = np.ones((20, 20), dtype=bool)                 # 10 x 10 ft: the bed with its clearances does not fit
    assert bed_fits(small, np.zeros_like(small), [entry[:20, :20], closet[:20, :20]], 10, 14, 6, 6, 3.0) is None
    blocked = np.zeros_like(room)
    blocked[:, 8:16] = True                               # a band across the room blocks every path
    assert not passable(room, blocked, [entry, closet], 3.0)


def test_room_paths_checks_each_bedroom(rules, matrix):
    labels = np.full((26, 30), -1, dtype=np.int32)
    labels[1:25, 1:7] = 0                                 # hall (3 ft)
    labels[1:25, 7:29] = 1                                # bedroom 11 x 12 ft
    hall = _spec("hall", "hall", circ=True, matrix=matrix)
    bed = _spec("bed", "bedroom", matrix=matrix)
    run = WallRun(0, 1, True, 7, 1, 25)
    door = Door(1, 0, "door", run, 2.0, 7.67, 2.0, True, True, 5.67, 2.67)
    lay = _layout(labels, [hall, bed], [door])
    report, bad = room_paths(lay, rules)
    assert bad is None and report[0]["bed_fits"] and report[0]["space_id"] == "bed"
    labels2 = labels.copy()
    labels2[1:25, 25:29] = -1                             # 9 x 12 ft: no bed with 36 in on both sides
    report2, bad2 = room_paths(_layout(labels2, [hall, bed], [door]), rules)
    assert bad2 == "in_room:bedroom" and not report2[0]["bed_fits"]


# ------------------------------------------------------------------ R4: the main bedroom is the largest


def test_the_main_bedroom_is_the_largest(rules):
    main, kid = _spec("m", "bedroom", master=True), _spec("k", "bedroom")
    node = lambda s, n: SimpleNamespace(spec=s, cells=n)        # noqa: E731
    assert master_largest([node(main, 500), node(kid, 480)], rules)
    assert not master_largest([node(main, 400), node(kid, 520)], rules)
    assert master_largest([node(kid, 520)], rules)


# ------------------------------------------------------------------ 6: strips


def test_strips_of_a_mask():
    m = np.zeros((10, 12), dtype=bool)
    m[2:8, 0:8] = True
    m[2:3, 8:12] = True                                    # a 0.5 ft sliver
    assert strip_cells(m, 6).sum() == 4 and len(strip_parts(m, 6)) == 1


def test_a_sliver_joins_its_neighbour_and_a_tiny_closet_its_room(rules):
    labels = np.full((22, 20), -1, dtype=np.int32)
    labels[1:9, 1:19] = 3                                  # a room along the top (the sliver is inside the house)
    labels[9:21, 1:9] = 0                                  # hall 4 x 6 ft
    labels[9:10, 9:13] = 0                                 # 0.5 ft sliver of the hall
    labels[10:21, 9:19] = 1                                # bedroom
    labels[9:10, 13:19] = 1
    labels[9:13, 1:3] = 2                                  # a 1 x 2 ft closet of the bedroom: too small to open
    specs = [_spec("hall", "hall", circ=True), _spec("bed", "bedroom"), _spec("cl", "closet", host="bed"),
             _spec("bed2", "bedroom")]
    lay = _layout(labels, specs)
    assert floor_strips(lay, rules)
    new, report = clean_strips(lay, rules)
    assert new is not None and not report["left"]
    assert {"from": "hall", "into": "bed", "sqft": 1.0} in report["joined"]
    assert [s.space_id for s in new.specs] == ["hall", "bed", "bed2"] and report["closets_removed"][0]["into"] == "hall"
    labels2 = labels.copy()
    labels2[1:9, 1:19] = -1                                # the sliver now on the facade: it leaves the house
    new2, report2 = clean_strips(_layout(labels2, specs[:3]), rules)
    assert any(j["into"] == "upper_roof" for j in report2["joined"]) and new2.open_air


# ------------------------------------------------------------------ 7: bath fixtures


def test_the_shower_stands_at_the_end_away_from_the_closet(rules):
    labels = np.full((12, 22), -1, dtype=np.int32)
    labels[1:11, 1:5] = 1                                  # bath closet, 2 ft deep, at the low-x end
    labels[1:11, 5:21] = 0                                 # bath 8 x 5 ft
    specs = [_spec("bath", "bathroom"), _spec("bath_closet", "closet", host="bath")]
    lay = _layout(labels, specs)
    keep = wet_keep_out(labels, specs, rules, RES)
    assert keep[0][1:11, 15:21].all() and not keep[0][:, 5:15].any()
    fx, bad = bath_fixtures(lay, rules)
    assert bad is None and fx[0]["wet_end"] == "high" and fx[0]["closet_ok"]
    labels2 = labels.copy()
    labels2[1:11, 17:21] = 2                               # another closet of the bath at the other end
    specs2 = specs + [_spec("bath_closet2", "closet", host="bath")]
    _, bad2 = bath_fixtures(_layout(labels2, specs2), rules)
    assert bad2 == "bath:closet_on_wet_side"


# ------------------------------------------------------------------ 8: the guest room


def _cell(rows):
    rows = [{"zone": "private", "household_role": "general", "host_space_id": None, **r} for r in rows]
    rows += [{"space_id": "living", "space_type": "living_room", "zone": "social", "household_role": "general",
              "host_space_id": None, "floor": 0, "area_sqft": 300.0}]
    return {"floors": 2, "space_split": rows, "gross_sqft": 2000.0, "split": {}}


def test_the_guest_room_shares_a_bath_or_becomes_a_study(values, catalog):
    scat, crs = load_stacking_catalog(), load_client_ruleset()
    rows = [{"space_id": "bedroom_kid", "space_type": "bedroom", "floor": 1, "area_sqft": 130.0},
            {"space_id": "flex_room_guest", "space_type": "flex_room", "household_role": "guest", "floor": 1,
             "area_sqft": 120.0}]
    out, rep = adjust_program(_cell(rows), 2400.0, catalog, scat, crs, values)
    bath = next(r for r in out["space_split"] if r.get("shared_by"))
    assert bath["shared_by"] == ["bedroom_kid", "flex_room_guest"] and rep["guest"][0]["shared_bath"]
    alone = [{"space_id": "flex_room_guest", "space_type": "flex_room", "household_role": "guest", "floor": 1,
              "area_sqft": 120.0}]
    out2, rep2 = adjust_program(_cell(alone), 2400.0, catalog, scat, crs, values)
    guest = next(r for r in out2["space_split"] if r["space_id"] == "flex_room_guest")
    assert guest["space_type"] == "study" and rep2["guest"][0]["converted_to"] == "study"
    tags = [t for t, _ in program_fallbacks(out["space_split"], values, catalog)]
    assert "guest_to_study" in tags
    back = dict(program_fallbacks(out["space_split"], values, catalog))["guest_to_study"]
    b = next(r for r in back if r["space_id"] == bath["space_id"])
    assert b["host_space_id"] == "bedroom_kid" and not b.get("shared_by")
    assert next(r for r in back if r["space_id"] == "flex_room_guest")["space_type"] == "study"


def test_the_walk_in_fallback_makes_it_a_closet(values, catalog):
    rows = [{"space_id": "suite", "space_type": "primary_suite", "zone": "private", "floor": 1, "area_sqft": 220.0,
             "host_space_id": None},
            {"space_id": "wic", "space_type": "walk_in_closet", "zone": "private", "floor": 1, "area_sqft": 60.0,
             "host_space_id": "suite"}]
    alt = dict(program_fallbacks(rows, values, catalog))["walk_in_to_closet"]
    wic = next(r for r in alt if r["space_id"] == "wic")
    suite = next(r for r in alt if r["space_id"] == "suite")
    cap = float(catalog.space_type("closet")["area"]["max"])
    assert wic["space_type"] == "closet" and wic["area_sqft"] == cap
    assert suite["area_sqft"] == pytest.approx(220.0 + 60.0 - cap)


# ------------------------------------------------------------------ a drawn house (all the rules hard)


@pytest.fixture(scope="module")
def drawn():
    from conftest import load_fixture

    from spaceplan.modules.stacking.main.run_stacking import run_stacking
    from spaceplan.pipeline.main.run_modules import area_matrix_contract_for

    am = area_matrix_contract_for(lots=["interior_50x100"], households=[("multigenerational", "latino")], zone_top=0)
    res = run_stacking(am, [load_fixture("lot_capacity", "interior_50x100")], stage="S2.1")
    cells = [c for c in res["cells"] if (c.get("s21") or {}).get("status") == "spaced"]
    assert cells
    return cells


def test_a_drawn_house_keeps_the_bedroom_rules(drawn):
    from shapely.geometry import shape

    from spaceplan.modules.stacking.lib.space_quality import leaf_supported

    for c in drawn:
        s21 = c["s21"]
        for f in ("ground", "upper"):
            b = s21[f]
            polys = {s["space_id"]: shape(s["polygon"]) for s in b["spaces"]}
            assert all(r["bed_fits"] for r in b.get("in_room") or [])
            assert not [x for x in (b.get("strips") or {}).get("left", []) if not x.get("circulation")]
            assert all(fx["closet_ok"] and fx["door_ok"] for fx in b.get("fixtures") or [])
            for d in b["doors"]:
                assert leaf_supported(d, polys) is not False, d          # no hinged leaf in the air
            spaces = {s["space_id"]: s for s in b["spaces"]}
            for s in b["spaces"]:                                         # the own bath through the walk-in
                host = spaces.get(s.get("host") or "")
                walk = [k for k, v in spaces.items() if v["space_type"] == "walk_in_closet" and v.get("host") == s.get("host")]
                if s["space_type"] in ("bathroom", "primary_bath") and host and walk and \
                        (host["space_type"] == "primary_suite"):
                    via = {d["b"] if d["a"] == s["space_id"] else d["a"] for d in b["doors"]
                           if s["space_id"] in (d["a"], d["b"]) and d["kind"] == "door"}
                    assert via & set(walk) and host["space_id"] not in via
