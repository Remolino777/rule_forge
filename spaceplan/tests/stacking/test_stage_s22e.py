"""Step 6.7a S2.2e: area criteria (effective maximum, freed area, whole suite, extra room), the S2.1 caps and the
exact door interference checks."""

from types import SimpleNamespace

import numpy as np
import pytest
from shapely.geometry import Point, box, mapping

from spaceplan.core.lib.catalog import load_catalog
from spaceplan.modules.design.lib import area_criteria as ac
from spaceplan.modules.design.lib import design_profile as dp
from spaceplan.modules.design.lib.design_registry import load_registry
from spaceplan.modules.design.lib.llm_tools import dispatch
from spaceplan.modules.stacking.lib.program_adjust import adjust_program
from spaceplan.modules.stacking.lib.space_quality import space_metrics, suite_metrics
from spaceplan.modules.stacking.lib.space_rules import (
    design_view,
    load_crc_ruleset,
    load_openings_ruleset,
    space_rules,
)
from spaceplan.modules.stacking.lib.stacking_catalog import load_stacking_catalog
from spaceplan.modules.stacking.lib.stair_access import load_client_ruleset, relations
from spaceplan.modules.stacking.lib.stair_rules import load_stair_ruleset
from spaceplan.modules.stacking.lib.unit_frame import UnitFrame, spec_of
from spaceplan.modules.stacking.lib.unit_layout import UnitLayout
from spaceplan.modules.stacking.lib.zone_relations import build_matrix
from spaceplan.modules.stacking.lib_aux.door_geometry import closed_leaf, floor_conflicts, summarize

DATE = "2026-10-12"
RES = 0.5


@pytest.fixture(scope="module")
def reg():
    return load_registry()


@pytest.fixture(scope="module")
def values(reg):
    return reg.baseline()


@pytest.fixture(scope="module")
def catalog():
    return load_catalog()


@pytest.fixture(scope="module")
def scat():
    return load_stacking_catalog()


@pytest.fixture(scope="module")
def client():
    return load_client_ruleset()


def _values(reg, changes):
    return dp.effective_values(reg, dp.apply(reg, dp.new_profile(reg, "t"), changes, "test", DATE))


def _cell(ground: float, upper: float, suite: float = 290.0, beds: int = 1):
    rows = [{"space_id": "hall", "space_type": "hall", "zone": "circulation", "floor": 0, "area_sqft": 60.0},
            {"space_id": "living_room", "space_type": "living_room", "zone": "social", "floor": 0,
             "area_sqft": 280.0},
            {"space_id": "primary_suite", "space_type": "primary_suite", "zone": "private", "floor": 1,
             "area_sqft": suite},
            {"space_id": "primary_bath", "space_type": "primary_bath", "zone": "private", "floor": 1,
             "area_sqft": 80.0},
            {"space_id": "walk_in_closet", "space_type": "walk_in_closet", "zone": "private", "floor": 1,
             "area_sqft": 50.0}]
    rows += [{"space_id": f"bedroom_{k}", "space_type": "bedroom", "zone": "private", "floor": 1, "area_sqft": 140.0}
             for k in range(1, beds + 1)]
    rows += [{"space_id": f"bathroom_{k}", "space_type": "bathroom", "zone": "private", "floor": 1, "area_sqft": 55.0}
             for k in range(1, beds + 1)]
    return {"floors": 2, "gross_sqft": ground + upper, "ground_sqft": ground, "upper_sqft": upper,
            "space_split": rows, "split": {"gross_by_floor_sqft": [ground, upper],
                                           "net_by_floor_sqft": [ground / 1.15, upper / 1.15], "upper_spaces": []}}


def _row(adjusted, sid):
    return next(r for r in adjusted["space_split"] if r["space_id"] == sid)


# ------------------------------------------------------------------ data and criteria


def test_registry_carries_the_area_and_door_criteria(reg, values):
    assert reg.version == "0.4.0" and reg.self_check() == []
    assert ac.enabled(values) and ac.policy(values, "extra_room_policy") == "propose"
    assert ac.policy(values, "freed_area") == "unbuilt"
    assert "primary_suite" in ac.cap_types(values) and "garage_2car" not in ac.cap_types(values)
    assert values["space.primary_suite.area_rec_sqft"] == 224.0 and values["space.primary_suite.area_cap_sqft"] == 300
    assert values["door.conflicts.approach_depth_ft"] == 3.0
    assert ac.suite_total_cap(values) == pytest.approx(0.85 * values["space.garage_2car.area_target_sqft"])
    with pytest.raises(dp.ProfileError):                     # recommended above the cap is refused
        dp.apply(reg, dp.new_profile(reg, "x"), [{"id": "space.bedroom.area_rec_sqft", "value": 200}], "t", DATE)


def test_effective_cap_never_cuts_below_the_floor_and_names_the_binding_limit(reg, values):
    suite = ac.effective_cap(values, "primary_suite", 1800.0)
    assert suite["cap_sqft"] == 250.0 and suite["binding"] == "program_min"     # catalog minimum 250
    low = _values(reg, [{"id": "space.primary_suite.area_min_sqft", "value": 150}])
    suite = ac.effective_cap(low, "primary_suite", 1800.0)
    assert suite["binding"] == "hierarchy" and suite["cap_sqft"] == pytest.approx(1.8 * 132.0)
    living = ac.effective_cap(values, "living_room", 1800.0)
    assert living["binding"] == "share" and living["cap_sqft"] < values["space.living_room.area_cap_sqft"]
    assert ac.effective_cap(values, "hall", 1800.0) is None


def test_size_factor_is_larger_for_small_houses(values):
    assert ac.size_factor(values, 1000.0) == pytest.approx(1.25)
    assert ac.size_factor(values, 5000.0) == pytest.approx(1.0)
    assert 1.0 < ac.size_factor(values, 2700.0) < 1.25


def test_the_llm_reads_and_changes_the_criteria(reg):
    prof = dp.new_profile(reg, "llm")
    res, _ = dispatch(reg, prof, "get_criteria", {"group": "area", "space_type": "primary_suite",
                                                  "house_net_sqft": 1800}, "llm", DATE)
    assert res["ok"] and res["spaces"][0]["effective"]["binding"] == "program_min"
    assert res["spaces"][0]["layers"]["code"]["rule_id"] == "C01-HABITABLE-AREA"
    res, prof = dispatch(reg, prof, "set_criteria", {"group": "area", "space_type": "primary_suite",
                                                     "changes": {"program_min_sqft": 180, "cap_sqft": 280},
                                                     "reason": "smaller master"}, "llm", DATE)
    assert res["ok"] and {c["id"] for c in prof["changes"]} == {"space.primary_suite.area_min_sqft",
                                                               "space.primary_suite.area_cap_sqft"}
    res, prof2 = dispatch(reg, prof, "set_criteria", {"group": "area", "changes": {"extra_room_policy": "auto"},
                                                      "reason": "the family wants the room"}, "llm", DATE)
    assert res["ok"] and dp.effective_values(reg, prof2)["space.area.extra_room_policy"] == "auto"
    res, same = dispatch(reg, prof, "set_criteria", {"group": "area", "space_type": "bedroom",
                                                     "changes": {"width": 3}, "reason": "x"}, "llm", DATE)
    assert not res["ok"] and res["error"] == "invalid_criteria" and same is prof
    res, _ = dispatch(reg, prof, "set_criteria", {"group": "doors", "changes": {"approach_depth_ft": 9},
                                                  "reason": "x"}, "llm", DATE)
    assert not res["ok"] and res["error"] == "invalid_changes"                 # outside its range
    res, _ = dispatch(reg, prof, "get_criteria", {"group": "doors"}, "llm", DATE)
    assert any(r["id"] == "door.conflicts.no_swing_on_doorway" for r in res["rules"])


# ------------------------------------------------------------------ program adjustment


def test_caps_cut_the_suite_and_leave_the_freed_area_unbuilt(catalog, scat, client, values):
    cell = _cell(1500.0, 1200.0)
    adjusted, rep = adjust_program(cell, 3000.0, catalog, scat, client, values)
    suite = _row(adjusted, "primary_suite")
    assert suite["area_sqft"] == 250.0 and suite["area_cap_sqft"] == 250.0
    area = rep["area_criteria"]
    capped = {c["space_id"]: c for c in area["capped"]}
    assert area["enabled"] and capped["primary_suite"]["binding"] == "program_min"
    assert capped["living_room"]["binding"] == "recommended"                 # share of a small house, floored
    assert capped["bedroom_1"]["binding"] == "recommended" and _row(adjusted, "bedroom_1")["area_sqft"] == 132.0
    assert area["freed_net_by_floor_sqft"][1] == pytest.approx(40.0 + 8.0)
    assert area["unbuilt_gross_by_floor_sqft"][1] == pytest.approx(48.0 * 1.15, abs=0.2)
    assert area["unbuilt_gross_by_floor_sqft"][0] == pytest.approx(30.0 * 1.15, abs=0.2)
    assert adjusted["split"]["gross_by_floor_sqft"][1] < 1200.0 + rep["added_by_floor_sqft"][1]
    assert all(r.get("area_cap_sqft") for r in adjusted["space_split"] if r["space_type"] in ac.cap_types(values))


def test_freed_area_kept_and_caps_off(reg, catalog, scat, client, values):
    keep = _values(reg, [{"id": "space.area.freed_area", "value": "keep"}])
    adjusted, rep = adjust_program(_cell(1500.0, 1200.0), 3000.0, catalog, scat, client, keep)
    assert rep["area_criteria"]["unbuilt_gross_by_floor_sqft"] == [0.0, 0.0]
    off = _values(reg, [{"id": "space.area.caps_enabled", "value": False}])
    adjusted, rep = adjust_program(_cell(1500.0, 1200.0), 3000.0, catalog, scat, client, off)
    assert _row(adjusted, "primary_suite")["area_sqft"] == 290.0 and not rep["area_criteria"]["enabled"]
    adjusted, rep = adjust_program(_cell(1500.0, 1200.0), 3000.0, catalog, scat, client)   # no design values
    assert _row(adjusted, "primary_suite")["area_sqft"] == 290.0 and "area_cap_sqft" not in _row(adjusted,
                                                                                                "primary_suite")


def test_ground_floor_never_shrinks_below_the_upper_one(catalog, scat, client, values):
    cell = _cell(1000.0, 1000.0)
    cell["space_split"][1]["area_sqft"] = 600.0                 # a living room far above its share
    _, rep = adjust_program(cell, 2500.0, catalog, scat, client, values)
    area = rep["area_criteria"]
    assert area["freed_net_by_floor_sqft"][0] > 300                          # the living room gives up 350
    assert area["unbuilt_gross_by_floor_sqft"][0] == pytest.approx(area["unbuilt_gross_by_floor_sqft"][1])


def test_whole_suite_within_its_garage_cap(reg, catalog, scat, client):
    low = _values(reg, [{"id": "space.primary_suite.area_min_sqft", "value": 150}])
    cell = _cell(1500.0, 1200.0)
    for r in cell["space_split"]:
        r["area_sqft"] = {"primary_bath": 110.0, "walk_in_closet": 70.0}.get(r["space_id"], r["area_sqft"])
    adjusted, rep = adjust_program(cell, 3000.0, catalog, scat, client, low)
    total = sum(_row(adjusted, k)["area_sqft"] for k in ("primary_suite", "primary_bath", "walk_in_closet"))
    st = rep["area_criteria"]["suite_total"][0]
    assert st["within_cap"] and total == pytest.approx(ac.suite_total_cap(low), abs=0.2)
    assert _row(adjusted, "primary_suite")["area_sqft"] >= low["space.primary_suite.area_rec_sqft"]
    assert _row(adjusted, "walk_in_closet")["area_sqft"] == 50.0 and _row(adjusted, "primary_bath")["area_sqft"] == 83.0
    assert st["taken_sqft"] == pytest.approx(47.0)


def test_extra_room_is_proposed_added_or_never(reg, catalog, scat, client, values):
    _, rep = adjust_program(_cell(1600.0, 1000.0), 3500.0, catalog, scat, client, values)
    extra = rep["area_criteria"]["extra_room"]
    assert extra["policy"] == "propose" and extra["fits"] and not extra["applied"] and extra["floor"] == 1
    auto = _values(reg, [{"id": "space.area.extra_room_policy", "value": "auto"}])
    adjusted, rep = adjust_program(_cell(1600.0, 1000.0), 3500.0, catalog, scat, client, auto)
    new = {r["space_type"]: r for r in adjusted["space_split"] if r.get("extra_room")}
    assert set(new) == {"bedroom", "bathroom"} and rep["area_criteria"]["extra_room"]["applied"]
    assert new["bathroom"]["host_space_id"] == new["bedroom"]["space_id"] and new["bedroom"]["area_sqft"] == 132.0
    _, rep = adjust_program(_cell(1600.0, 1000.0), 2700.0, catalog, scat, client, auto)
    assert not rep["area_criteria"]["extra_room"]["fits"]                    # no FAR slack for it
    _, rep = adjust_program(_cell(1000.0, 1000.0), 3500.0, catalog, scat, client, auto)
    assert rep["area_criteria"]["extra_room"]["reason"] == "upper_exceeds_ground"
    never = _values(reg, [{"id": "space.area.extra_room_policy", "value": "never"}])
    _, rep = adjust_program(_cell(1600.0, 1000.0), 3500.0, catalog, scat, client, never)
    assert not rep["area_criteria"]["extra_room"]["fits"]


# ------------------------------------------------------------------ stage S2.1 caps


def test_layout_targets_respect_the_caps(catalog, scat, values):
    rules = space_rules(scat, catalog, load_crc_ruleset(), load_openings_ruleset(), load_stair_ruleset(),
                        load_client_ruleset(), design_view())
    matrix = build_matrix(catalog, relations(load_client_ruleset()), scat.s2["pair_default_weights"])
    rows = [{"space_id": "suite", "space_type": "primary_suite", "zone": "private", "area_sqft": 250.0,
             "area_cap_sqft": 250.0},
            {"space_id": "bed", "space_type": "bedroom", "zone": "private", "area_sqft": 140.0,
             "area_cap_sqft": 180.0}]
    specs = [spec_of(catalog, rules, matrix, r, "u") for r in rows]
    assert specs[0].cap_sqft == 250.0
    nx, ny = 2 + int(30 / RES), 2 + int(16 / RES)
    base = np.full((ny, nx), -2, dtype=np.int32)
    base[0, :] = base[-1, :] = base[:, 0] = base[:, -1] = -1
    mask = base == -2
    unit = UnitFrame(0, "u", "private", mask, (1, nx - 1, 1, ny - 1), specs)
    zero = np.zeros_like(mask)
    floor = SimpleNamespace(res=RES, outside=base == -1, landing=zero, links={}, units=[unit], base=base, fixed=[],
                            stair=zero, level=1, accessible=False)
    ul = UnitLayout(floor, unit, rules, catalog, matrix)
    by_id = {s.space_id: s for s in specs}
    free = 420.0 / (RES * RES)                                  # 420 sq ft for 390 of program
    targets = ul._cap_area({"suite": free * 250 / 390, "bed": free * 140 / 390}, by_id)
    cap = ac.drawn_cap(values, 250.0) / (RES * RES)
    assert targets["suite"] == pytest.approx(cap) and sum(targets.values()) == pytest.approx(free)
    assert targets["bed"] * RES * RES == pytest.approx(420.0 - ac.drawn_cap(values, 250.0))
    over = ul._cap_area({"suite": 2 * cap, "bed": 2 * cap}, by_id)             # all capped: spread in proportion
    assert sum(over.values()) == pytest.approx(4 * cap)


# ------------------------------------------------------------------ doors


def _swing(hx, hy, r, qx, qy):
    return mapping(Point(hx, hy).buffer(r, 16).intersection(box(*qx[:1], *qy[:1], *qx[1:], *qy[1:])))


def _door(a, b, seg, hinge, swing, leaf=2.5, kind="door"):
    return {"a": a, "b": b, "kind": kind, "segment": seg, "hinge": hinge, "leaf_ft": leaf, "swing": swing,
            "swing_into": a}


def _space(sid, st, poly, host=None):
    return {"space_id": sid, "space_type": st, "polygon": mapping(poly), "host": host}


PARAMS = {"no_swing_overlap": True, "no_swing_on_doorway": True, "no_swing_outside_room": True,
          "approach_depth_ft": 3.0, "overlap_tolerance_sqft": 0.05, "leaf_thickness_in": 1.75,
          "same_suite_exception": True, "doorway_max_width_ft": 8.0}


def test_closed_leaf_runs_from_the_hinge_along_the_doorway():
    from shapely.geometry import LineString
    leaf = closed_leaf(LineString([(0, 0), (3, 0)]), (0.0, 0.0), 2.5, 1.75 / 12)
    assert leaf.bounds[0] == pytest.approx(0.0) and leaf.bounds[2] == pytest.approx(2.5)


def test_crossing_swings_are_r1_and_e1_inside_one_suite():
    room = box(0, 0, 10, 10)
    spaces = [_space("suite", "primary_suite", room), _space("wic", "walk_in_closet", box(0, 10, 5, 15), "suite")]
    d1 = _door("suite", "hall", [[0, 2], [0, 4.5]], [0, 2], _swing(0, 2, 2.5, (0, 2.5), (2, 4.5)))
    d2 = _door("suite", "x", [[2, 0], [4.5, 0]], [2, 0], _swing(2, 0, 2.5, (2, 4.5), (0, 2.5)))
    found = floor_conflicts([d1, d2], spaces, PARAMS, ("primary_suite", "bedroom"))
    counts = summarize(found)
    assert counts["E1"] == 1 and counts["R1"] == 0                     # same suite, no leaf strike
    found = floor_conflicts([d1, d2], [{**spaces[0], "space_type": "kitchen"}], PARAMS, ("primary_suite",))
    assert summarize(found)["R1"] == 1


def test_leaf_strike_outside_room_and_approach_zone():
    room = box(0, 0, 10, 10)
    spaces = [_space("bed", "bedroom", room), _space("hall", "hall", box(-4, 0, 0, 10))]
    near = _door("bed", "hall", [[0, 0.3], [0, 2.8]], [0, 2.8], _swing(0, 2.8, 2.5, (0, 2.5), (0.3, 2.8)))
    corner = _door("bed", "y", [[-1, 0], [1.5, 0]], [1.5, 0], _swing(1.5, 0, 2.5, (-1, 1.5), (0, 2.5)))
    found = floor_conflicts([near, corner], spaces, {**PARAMS, "same_suite_exception": False}, ())
    rules = {f["rule"] for f in found}
    assert {"R1", "R1b", "R3"} <= rules
    out = _door("bed", "hall", [[0, 8], [0, 10.5]], [0, 8], _swing(0, 8, 2.5, (0, 2.5), (8, 10.5)))
    assert summarize(floor_conflicts([out], spaces, PARAMS, ()))["R2"] == 1
    wide = {"a": "bed", "b": "hall", "kind": "opening", "segment": [[0, 2], [0, 12]]}
    assert summarize(floor_conflicts([near, wide], spaces, PARAMS, ()))["R3"] == 0


# ------------------------------------------------------------------ quality


def test_quality_measures_the_suite_and_the_caps(values):
    sp = {"space_id": "s", "space_type": "primary_suite", "polygon": mapping(box(0, 0, 20, 16)), "cap_sqft": 250.0}
    m = space_metrics(sp, 1, values)
    assert m["over_cap"] and m["cap_sqft"] == 250.0
    rows = [m, {**space_metrics({"space_id": "w", "space_type": "walk_in_closet",
                                 "polygon": mapping(box(0, 0, 6, 8)), "host": "s"}, 1, values)}]
    s = suite_metrics(rows, 420.0)
    assert s["total_sqft"] == pytest.approx(368.0) and s["bedroom_to_garage"] == pytest.approx(320 / 420, abs=1e-3)
