"""Stage S2.1b (step 6.7a): sliding closet doors, leaves resting on a wall, baths per bedroom (K10), the secondary
door to the patio, the main entry and the front yard (Z10, Z11, O04, O05), the rear cantilever and full connectivity
(client decisions 2026-10-11)."""

from collections import defaultdict

import numpy as np
import pytest
from conftest import load_fixture
from shapely.geometry import LineString, Point, box, shape

from spaceplan.core.lib.catalog import load_catalog
from spaceplan.modules.stacking.lib.door_placement import DoorPlacer, FloorLayout, door_choices
from spaceplan.modules.stacking.lib.floor_frame import floor_units
from spaceplan.modules.stacking.lib.plan_levels import CANTILEVER_REAR, upper_floor
from spaceplan.modules.stacking.lib.program_adjust import adjust_program
from spaceplan.modules.stacking.lib.space_rules import (
    load_crc_ruleset,
    load_openings_ruleset,
    space_rules,
)
from spaceplan.modules.stacking.lib.stacking_catalog import PLACEMENTS, load_stacking_catalog
from spaceplan.modules.stacking.lib.stair_access import load_client_ruleset, relations
from spaceplan.modules.stacking.lib.stair_rules import load_stair_ruleset
from spaceplan.modules.stacking.lib.unit_frame import SpaceSpec, roles_of
from spaceplan.modules.stacking.lib.zone_relations import build_matrix
from spaceplan.modules.stacking.lib_aux.space_grid import wall_runs
from spaceplan.modules.stacking.main.run_stacking import run_stacking


@pytest.fixture(scope="module")
def catalog():
    return load_catalog()


@pytest.fixture(scope="module")
def scat():
    return load_stacking_catalog()


@pytest.fixture(scope="module")
def client():
    return load_client_ruleset()


@pytest.fixture(scope="module")
def matrix(catalog, scat, client):
    return build_matrix(catalog, relations(client), scat.s2["pair_default_weights"])


@pytest.fixture(scope="module")
def rules(catalog, scat, client):
    return space_rules(scat, catalog, load_crc_ruleset(), load_openings_ruleset(), load_stair_ruleset(), client)


@pytest.fixture(scope="module")
def result():
    from spaceplan.pipeline.main.run_modules import area_matrix_contract_for

    am = area_matrix_contract_for(lots=["interior_50x100"], households=[("teens_family", None)], zone_top=0)
    return run_stacking(am, [load_fixture("lot_capacity", "interior_50x100")], stage="S2.1")


def _spaced(result):
    cells = [c for c in result["cells"] if (c.get("s21") or {}).get("status") == "spaced"]
    assert cells
    return cells


def _spec(matrix, sid, st, zone, passable=False, circulation=False, host=None, between=()):
    return SpaceSpec(sid, st, zone, None, 100.0, 0.0, 0.0, False, passable, circulation, roles_of(matrix, st), host,
                     False, False, tuple(between))


def _cell(beds: int, baths: int, gross: float):
    rows = [{"space_id": "hall", "space_type": "hall", "zone": "circulation", "floor": 0, "area_sqft": 60.0},
            {"space_id": "primary_suite", "space_type": "primary_suite", "zone": "private", "floor": 1,
             "area_sqft": 290.0},
            {"space_id": "primary_bath", "space_type": "primary_bath", "zone": "private", "floor": 1,
             "area_sqft": 80.0},
            {"space_id": "walk_in_closet", "space_type": "walk_in_closet", "zone": "private", "floor": 1,
             "area_sqft": 50.0}]
    rows += [{"space_id": f"bedroom_{k}", "space_type": "bedroom", "zone": "private", "floor": 1, "area_sqft": 140.0}
             for k in range(1, beds + 1)]
    rows += [{"space_id": f"bathroom_{k}", "space_type": "bathroom", "zone": "private", "floor": 1, "area_sqft": 55.0}
             for k in range(1, baths + 1)]
    return {"floors": 2, "gross_sqft": gross, "ground_sqft": gross / 2, "upper_sqft": gross / 2,
            "space_split": rows, "split": {"gross_by_floor_sqft": [gross / 2, gross / 2],
                                           "net_by_floor_sqft": [gross / 2, gross / 2], "upper_spaces": []}}


# ------------------------------------------------------------------ data and program (K10)


def test_catalog_adds_door_types_exits_program_and_cantilever(scat):
    assert scat.version == "0.12.0" and "cantilever_rear" in PLACEMENTS
    types = scat.s21["doors"]["types"]
    assert types["main_entry"]["leaf_in"] == 36 and types["main_entry"]["sidelight_in"] > 0
    assert types["patio_slider"]["width_in"] >= 60 and "closet" in scat.s21["doors"]["sliding_space_types"]
    assert scat.s21["exits"]["patio"]["order"][:2] == ["dining_room", "living_dining"]
    assert scat.data["upper_floor"]["cantilever"]["depth_ft"] == 6.0


def test_k10_gives_each_bedroom_a_bath_when_the_far_allows(catalog, scat, client):
    adjusted, rep = adjust_program(_cell(2, 0, 1500.0), 3000.0, catalog, scat, client)
    baths = [r for r in adjusted["space_split"] if r["space_type"] == "bathroom"]
    assert len(baths) == 2 and {r["host_space_id"] for r in baths} == {"bedroom_1", "bedroom_2"}
    assert any(r.get("allowance") for r in adjusted["space_split"])
    assert adjusted["gross_sqft"] == pytest.approx(1500.0 + rep["gross_added_sqft"])
    assert rep["gross_added_sqft"] <= rep["far_slack_sqft"]


def test_k10_shares_a_bath_between_two_bedrooms_without_far(catalog, scat, client):
    adjusted, rep = adjust_program(_cell(2, 1, 3000.0), 3000.0, catalog, scat, client)
    bath = next(r for r in adjusted["space_split"] if r["space_type"] == "bathroom")
    assert bath["shared_by"] == ["bedroom_1", "bedroom_2"] and not bath.get("host_space_id")
    assert rep["gross_added_sqft"] == 0.0 and adjusted["gross_sqft"] == 3000.0
    master = {r["space_id"]: r.get("host_space_id") for r in adjusted["space_split"]}
    assert master["primary_bath"] == "primary_suite" and master["walk_in_closet"] == "primary_suite"


def test_corridor_allowance_goes_to_the_private_zone_target(catalog, scat, client):
    adjusted, _ = adjust_program(_cell(2, 1, 3000.0), 3000.0, catalog, scat, client)
    sets = floor_units(catalog, scat.s2, adjusted["space_split"], 1, 2, scat.stair_space_type, False, "hall")
    private = next(u for u in sets[0][1] if u.zone == "private")
    plain = sum(r["area_sqft"] for r in adjusted["space_split"] if r["floor"] == 1 and r["zone"] == "private"
                and not r.get("allowance"))
    assert private.target_sqft > plain


# ------------------------------------------------------------------ door rules


def test_en_suite_bath_opens_onto_its_bedroom_only_and_shared_onto_the_hall(rules, matrix):
    hall = _spec(matrix, "hall", "hall", "circulation", True, True)
    bed = _spec(matrix, "bedroom_1", "bedroom", "private")
    own = _spec(matrix, "bathroom_1", "bathroom", "private", host="bedroom_1")
    shared = _spec(matrix, "bathroom_2", "bathroom", "private", between=("bedroom_1", "bedroom_2"))
    assert door_choices(rules, matrix, own, bed) == 0 and door_choices(rules, matrix, own, hall) is None
    assert door_choices(rules, matrix, shared, hall) is not None and door_choices(rules, matrix, shared, bed) is None


def test_a_hinged_leaf_needs_a_wall_beside_it(rules):
    labels = np.full((14, 14), -1, dtype=np.int32)
    labels[1:7, 1:13] = 0                         # hall
    labels[7:13, 1:7] = 1                         # room served by the door
    labels[7:13, 7:13] = 2                        # neighbour room
    layout = FloorLayout(None, (), [], labels, 0, 0)
    placer = DoorPlacer.__new__(DoorPlacer)
    placer.layout = layout
    run = wall_runs(labels)[(0, 1)][0]             # horizontal wall between hall (low) and room 1 (high)
    assert placer._supported(run, True, True, 1, 5.0)        # hinge at the room's west corner: exterior wall
    assert placer._supported(run, True, False, 1, 5.0)       # east corner: the wall shared with room 2
    labels2 = labels.copy()
    labels2[7:13, 7:13] = 1                        # room 1 continues: the run's east end is not a corner
    labels2[1:7, 7:13] = 3                         # another space on the other side of that wall
    layout.labels = labels2
    run2 = wall_runs(labels2)[(0, 1)][0]
    assert not placer._supported(run2, True, False, 1, 5.0)


# ------------------------------------------------------------------ the pilot cell


def test_closets_slide_and_no_hinged_leaf_stands_in_the_air(result):
    for c in _spaced(result):
        for f in ("ground", "upper"):
            block = c["s21"][f]
            types = {s["space_id"]: s["space_type"] for s in block["spaces"]}
            polys = {s["space_id"]: shape(s["polygon"]) for s in block["spaces"]}
            for d in block["doors"]:
                if types.get(d["a"]) == "closet":
                    assert d["kind"] == "closet_slider"
                if not d.get("swing") or d["a"] not in polys:
                    continue
                hinge, r = Point(d["hinge"]), d["leaf_ft"]
                sw, seg = shape(d["swing"]), LineString(d["segment"])
                tip = max((Point(p) for p in sw.exterior.coords if abs(Point(p).distance(hinge) - r) < 0.05),
                          key=seg.distance)
                leaf = LineString([hinge, tip])
                wall = polys[d["a"]].boundary.buffer(0.75)
                assert all(wall.contains(leaf.interpolate(t, normalized=True)) for t in (0.3, 0.6, 0.95)), d


def test_every_space_is_reached_from_the_entry_or_the_stair(result):
    for c in _spaced(result):
        for f in ("ground", "upper"):
            block = c["s21"][f]
            adj = defaultdict(set)
            for d in block["doors"]:
                adj[d["a"]].add(d["b"])
                adj[d["b"]].add(d["a"])
            seen, stack = {block["root"]}, [block["root"]]
            while stack:
                for y in adj[stack.pop()]:
                    if y not in seen:
                        seen.add(y)
                        stack.append(y)
            assert {s["space_id"] for s in block["spaces"]} <= seen


def test_shared_bath_sits_between_its_bedrooms_and_opens_onto_the_hall(result):
    for c in _spaced(result):
        for shared in c["s21"]["k10"]["shared"]:
            block = c["s21"]["upper"]
            polys = {s["space_id"]: shape(s["polygon"]) for s in block["spaces"]}
            bath = polys[shared["bath"]]
            for b in shared["bedrooms"]:
                assert bath.intersection(polys[b]).length >= 1.9 or bath.buffer(0.05).intersection(polys[b]).area > 0
            doors = [d for d in block["doors"] if shared["bath"] in (d["a"], d["b"])]
            others = {d["b"] if d["a"] == shared["bath"] else d["a"] for d in doors}
            others -= {f"{shared['bath']}_bath_closet"}            # S2.2b: its own bath closet
            assert others and all(o.startswith("hall") for o in others)


def test_ground_floor_opens_onto_the_patio_with_a_landing(result, scat):
    order = scat.s21["exits"]["patio"]["order"]
    for c in _spaced(result):
        ex = c["s21"]["ground"]["patio_exit"]
        assert ex and ex["space_type"] in order and ex["facade"] in scat.s21["exits"]["patio"]["facades"]
        landing = shape(ex["landing"])
        assert min(landing.bounds[2] - landing.bounds[0], landing.bounds[3] - landing.bounds[1]) >= 3.0 - 1e-6
        if ex["kind"] == "patio_slider":
            assert ex["glass_sqft"] > 0


def test_front_yard_and_main_entry_meet_the_rules(result):
    for c in _spaced(result):
        site = c["s21"]["site"]
        assert site["status"] == "laid_out" and all(ch["passes"] for ch in site["checks"])
        me = site["main_entry"]
        assert me["leaf_in"] == 36 and me["sidelight_in"] > 0 and me["egress_ok"]
        a = site["areas_sqft"]
        assert a["garden"] > 0 and a["driveway"] > 0 and a["entry_deck"] > 0
        assert shape(site["garden"]).intersection(shape(site["driveway"])).area < 0.5


def test_cantilever_rear_stands_out_over_the_patio(scat):
    ground = box(0, 0, 40, 30)
    footprint = box(0, 0, 40, 45)
    cand = upper_floor(CANTILEVER_REAR, ground, 900.0, None, "right", scat.geometry, footprint=footprint,
                       cantilever_ft=6.0)
    assert cand.polygon is not None and cand.polygon.bounds[3] == pytest.approx(36.0)
    assert cand.polygon.area == pytest.approx(900.0, abs=scat.geometry["area_tolerance_sqft"])
    none = upper_floor(CANTILEVER_REAR, ground, 900.0, None, "right", scat.geometry, footprint=ground,
                       cantilever_ft=6.0)
    assert none.polygon is None                    # no room behind the ground floor inside the setbacks
