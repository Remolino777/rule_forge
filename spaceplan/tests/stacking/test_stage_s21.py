"""Stage S2.1 of the stacking module (step 6.7a): spaces and doors inside the S2 zones, normative (C01, C06, O01-O03,
S08) and client (K01, K02, K04, K05) rules at the door level, fallback along the ranked stair candidates."""

import copy

import numpy as np
import pytest
from conftest import load_fixture
from shapely.geometry import shape

from spaceplan.core.lib.catalog import load_catalog
from spaceplan.core.lib.contracts import contract_problems
from spaceplan.modules.stacking.lib.door_placement import door_choices
from spaceplan.modules.stacking.lib.space_rules import (
    load_crc_ruleset,
    load_openings_ruleset,
    space_rules,
)
from spaceplan.modules.stacking.lib.stacking_catalog import (
    check_stacking_catalog,
    load_stacking_catalog,
)
from spaceplan.modules.stacking.lib.stair_access import load_client_ruleset, relations
from spaceplan.modules.stacking.lib.stair_rules import load_stair_ruleset
from spaceplan.modules.stacking.lib.unit_frame import SpaceSpec, roles_of
from spaceplan.modules.stacking.lib.unit_layout import suite_groups
from spaceplan.modules.stacking.lib.zone_relations import build_matrix
from spaceplan.modules.stacking.lib_aux.space_grid import (
    Guillotine,
    largest_rect,
    realize,
    swing_cells,
    wall_runs,
)
from spaceplan.modules.stacking.main.contract import to_contract
from spaceplan.modules.stacking.main.run_stacking import run_stacking, s21_table_rows


@pytest.fixture(scope="module")
def catalog():
    return load_catalog()


@pytest.fixture(scope="module")
def scat():
    return load_stacking_catalog()


@pytest.fixture(scope="module")
def matrix(catalog, scat):
    return build_matrix(catalog, relations(load_client_ruleset()), scat.s2["pair_default_weights"])


@pytest.fixture(scope="module")
def rules(catalog, scat):
    return space_rules(scat, catalog, load_crc_ruleset(), load_openings_ruleset(), load_stair_ruleset(),
                       load_client_ruleset())


@pytest.fixture(scope="module")
def spaced():
    """A teens family on the interior lot (maximum): the chosen stair gets no layout, a later ranked one does."""
    from spaceplan.pipeline.main.run_modules import area_matrix_contract_for

    am = area_matrix_contract_for(lots=["interior_50x100"], households=[("teens_family", "latino")], zone_top=0)
    return run_stacking(am, [load_fixture("lot_capacity", "interior_50x100")], stage="S2.1")


def _spec(rules, matrix, sid, st, zone, passable=False, circulation=False, host=None, fixed=False):
    return SpaceSpec(sid, st, zone, None, 100.0, 0.0, 0.0, False, passable, circulation, roles_of(matrix, st), host,
                     fixed)


def _cells(result):
    return [c for c in result["cells"] if (c.get("s21") or {}).get("status") == "spaced"]


# ------------------------------------------------------------------ data


def test_catalog_has_s21_block_and_checks_it(scat):
    assert scat.version == "0.12.0" and scat.s21["fallback"]["order"] == "stair_choice.ranked"
    bad = copy.deepcopy(scat.data)
    bad["s21"]["doors"]["interior_clear_width_in"] = 0
    bad["s21"]["weights"] = {"relations": 1.0}
    problems = check_stacking_catalog(bad)
    assert any("interior_clear_width_in" in p for p in problems) and any("s21.weights" in p for p in problems)


def test_rules_come_from_the_rulesets_not_the_code(rules):
    crc, openings = load_crc_ruleset(), load_openings_ruleset()
    assert rules.habitable_min_side_ft == float(crc.rule("C01-HABITABLE-DIMENSION")["value"])
    assert rules.glazing_ratio == float(crc.rule("C03-GLAZING")["value"])
    o1 = openings.params("O01-EMERGENCY-ESCAPE")
    assert rules.escape_width_ft == pytest.approx(o1["min_clear_width_in"] / 12.0)
    assert set(rules.sleeping_types) == set(o1["sleeping_space_types"])
    assert all(openings.status(r) == "provisional" for r in ("O01-EMERGENCY-ESCAPE", "O02-GARAGE-OPENINGS",
                                                              "O03-HABITABLE-FACADE"))


def test_facade_need_grows_with_the_room_and_covers_the_escape_opening(rules):
    f = rules.s21["facade"]
    small = rules.facade_need_ft("bedroom", 100.0, True)
    big = rules.facade_need_ft("bedroom", 200.0, True)
    assert big > small >= rules.escape_width_ft + float(f["frame_allowance_ft"]) - 1e-9
    assert rules.facade_need_ft("hall", 100.0, False) == 0.0


# ------------------------------------------------------------------ grid helpers (lib_aux)


def test_realize_fills_a_box_with_side_by_side_parts():
    mask = np.zeros((12, 22), dtype=bool)
    mask[1:11, 1:21] = True
    g = Guillotine(True, (("a",), ("b", ("c", "d"))))
    r = realize(mask, (1, 21, 1, 11), g, {"a": 100.0, "b": 50.0, "c": 25.0, "d": 25.0}, {k: 2 for k in "abcd"})
    assert r is not None and set(r) == set("abcd")
    covered = sum((i1 - i0) * (j1 - j0) for i0, i1, j0, j1 in r.values())
    assert covered == 200
    assert r["c"][2] == r["d"][2] and r["c"][1] == r["d"][0]          # c and d share their slot, side by side


def test_largest_rect_and_wall_runs():
    m = np.zeros((6, 6), dtype=bool)
    m[1:5, 1:5] = True
    m[1, 1] = False
    n, rect = largest_rect(m)
    assert n == 12 and rect is not None
    labels = np.full((4, 6), -1)
    labels[:, :3] = 0
    labels[:, 3:] = 1
    runs = wall_runs(labels)
    assert list(runs) == [(0, 1)] and runs[(0, 1)][0].vertical and runs[(0, 1)][0].cells == 4


def test_swing_is_a_quarter_disc_on_the_served_side():
    labels = np.zeros((10, 10), dtype=int)
    labels[:, 5:] = 1
    run = wall_runs(labels)[(0, 1)][0]
    sw = swing_cells(labels.shape, run, True, 1.0, 3.0, True)
    assert sw.any() and (labels[sw] == 1).all() and sw.sum() <= 9


# ------------------------------------------------------------------ door rules


def test_half_bath_never_opens_onto_living_or_kitchen_k04(rules, matrix):
    hb = _spec(rules, matrix, "half_bath", "half_bath", "circulation")
    for room in ("living_room", "kitchen", "dining_room"):
        assert door_choices(rules, matrix, hb, _spec(rules, matrix, room, room, "social", passable=True)) is None
    assert door_choices(rules, matrix, hb, _spec(rules, matrix, "hall", "hall", "circulation", True, True)) is not None


def test_bedroom_opens_onto_circulation_only_and_baths_en_suite(rules, matrix):
    bed = _spec(rules, matrix, "bedroom_1", "bedroom", "private")
    living = _spec(rules, matrix, "living", "living_room", "social", passable=True)
    hall = _spec(rules, matrix, "hall", "hall", "circulation", True, True)
    bath = _spec(rules, matrix, "primary_bath", "primary_bath", "private")
    suite = _spec(rules, matrix, "primary_suite", "primary_suite", "private")
    assert door_choices(rules, matrix, bed, living) is None
    assert door_choices(rules, matrix, bed, hall) is not None
    assert door_choices(rules, matrix, bath, suite) == 0              # the bath opens onto its bedroom
    assert door_choices(rules, matrix, suite, bath) is None           # never the other way round


def test_garage_never_opens_onto_a_sleeping_room_o02(rules, matrix):
    garage = _spec(rules, matrix, "garage", "garage_2car", "garage")
    bed = _spec(rules, matrix, "bedroom_1", "bedroom", "private")
    kitchen = _spec(rules, matrix, "kitchen", "kitchen", "kitchen", passable=True)
    assert door_choices(rules, matrix, garage, bed) is None
    assert door_choices(rules, matrix, garage, kitchen) is not None


def test_suite_groups_keep_closets_and_en_suite_baths_with_their_room(rules, matrix):
    specs = {s.space_id: s for s in (
        _spec(rules, matrix, "primary_suite", "primary_suite", "private"),
        _spec(rules, matrix, "primary_bath", "primary_bath", "private"),
        _spec(rules, matrix, "walk_in", "walk_in_closet", "private", host="primary_suite"),
        _spec(rules, matrix, "bedroom_1", "bedroom", "private"),
        _spec(rules, matrix, "closet_1", "closet", "private", host="bedroom_1"),
        _spec(rules, matrix, "bathroom", "bathroom", "private"))}
    ways = suite_groups(specs, rules, matrix)
    first = {g[0]: set(g[1:]) for g in ways[0]}
    assert first["primary_suite"] == {"primary_bath", "walk_in"} and first["bedroom_1"] == {"closet_1"}
    assert "bathroom" in first                                        # the shared bath opens onto the hall
    assert any("bathroom" in g and g[0] == "bedroom_1" for way in ways[1:] for g in way)


# ------------------------------------------------------------------ the pilot cell


def test_spaced_cell_closes_6_7a_with_traces(spaced):
    cells = _cells(spaced)
    assert cells and spaced["meta"]["stage"] == "S2.1"
    c = cells[0]
    assert c["next_stage"] is None and c["s21"]["stair_rank"] >= 0 and c["s21"]["attempts"]
    results = {t["rule_id"]: t["result"] for t in c["s21"]["rule_traces"]}
    for rid in ("C01-HABITABLE-DIMENSION", "O01-EMERGENCY-ESCAPE", "O03-HABITABLE-FACADE", "S08-STAIR-TOP-DOOR",
                "K01-STAIR-TOP-ARRIVAL", "K02-STAIR-BOTTOM-START", "K05-STAIR-RELATIONS"):
        assert results[rid] == "pass"


def test_fallback_follows_the_ranked_candidates(spaced):
    c = _cells(spaced)[0]
    s21, choice = c["s21"], c["s2"]["stair_choice"]
    tried = s21["attempts"]
    assert [a["rank"] for a in tried] == list(range(len(tried))) and tried[-1]["status"] == "spaced"
    assert all(a["status"] == "no_valid_layout" for a in tried[:-1])
    if s21["stair_rank"]:
        assert choice["reason"].startswith("S2.1 fallback")


def test_spaces_tile_each_floor_and_rooms_meet_their_minimums(spaced, rules):
    c = _cells(spaced)[0]
    for f, level in (("ground", 0), ("upper", 1)):
        block = c["s21"][f]
        floor = shape(c["s1"]["levels"][level]["polygon"])
        polys = [shape(sp["polygon"]) for sp in block["spaces"]]
        stair = shape(c["s1"]["stair"]["polygon"])
        for i, a in enumerate(polys):
            for b in polys[i + 1:]:
                assert a.intersection(b).area < 0.5                 # no overlap
        covered = sum(p.area for p in polys) + stair.intersection(floor).area
        assert covered == pytest.approx(floor.area, rel=0.03)
        for sp in block["spaces"]:
            if sp["space_type"] in rules.sleeping_types:
                assert sp["exterior_ft"] >= rules.escape_width_ft


def test_every_space_gets_a_door_and_none_swings_over_the_stair(spaced):
    c = _cells(spaced)[0]
    stair = shape(c["s1"]["stair"]["polygon"])
    for f in ("ground", "upper"):
        block = c["s21"][f]
        linked = {d["a"] for d in block["doors"]} | {d["b"] for d in block["doors"]}
        for sp in block["spaces"]:
            assert sp["space_id"] in linked, sp["space_id"]
        for d in block["doors"]:
            if d.get("swing"):
                assert shape(d["swing"]).intersection(stair).area < 0.05
            if d["kind"] == "garage_door":
                assert d["self_closing"]


def test_s21_contract_validates_and_tables(spaced):
    contract = to_contract(spaced)
    assert contract_problems(contract, "stack_plan") == []
    rows = s21_table_rows(spaced)
    assert rows and all(r["s21_status"] in ("spaced", "no_valid_layout", "not_evaluated") for r in rows)
    assert not any("_alternatives" in (c.get("s2") or {}) for c in spaced["cells"])   # memory only
