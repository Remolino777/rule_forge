"""Stage S2 of the stacking module (step 6.7a): zoning of both floors around the stair core, A/B/C start portfolio,
client-rule traces (K01-K05, K05 over the base matrix) and the stair choice of stage S1.2 (no backtrack: option B)."""

import copy

import pytest
from conftest import load_fixture
from shapely.geometry import box, shape
from shapely.ops import unary_union

from spaceplan.core.lib.catalog import load_catalog
from spaceplan.core.lib.contracts import contract_problems
from spaceplan.modules.stacking.lib.core_zoning import FloorSearch
from spaceplan.modules.stacking.lib.floor_frame import (
    FAMILY_ROOM,
    HALL,
    VESTIBULE,
    CellFloors,
    ZoneUnit,
    arrival_kind,
    floor_units,
    upper_frame,
)
from spaceplan.modules.stacking.lib.stacking_catalog import check_stacking_catalog, load_stacking_catalog
from spaceplan.modules.stacking.lib.stair_access import DEFERRED_S21, NOT_EVALUATED, PASS, load_client_ruleset, relations
from spaceplan.modules.stacking.lib.zone_cell import _receives, s2_context
from spaceplan.modules.stacking.lib.zone_relations import (
    DEFERRED,
    FAILED,
    MET,
    FloorGraph,
    build_matrix,
    pair_on_floor,
)
from spaceplan.modules.stacking.lib_aux.zone_grid import (
    cut_index,
    label_contact,
    rasterize,
    shared_contact,
)
from spaceplan.modules.stacking.main.contract import to_contract
from spaceplan.modules.stacking.main.run_stacking import run_stacking, s2_table_rows

SUBJECT = "interior_50x100_empty_nest_anglo"


@pytest.fixture(scope="module")
def catalog():
    return load_catalog()


@pytest.fixture(scope="module")
def scat():
    return load_stacking_catalog()


@pytest.fixture(scope="module")
def ctx(catalog, scat):
    crs = load_client_ruleset()
    return s2_context(scat, catalog, crs, build_matrix(catalog, relations(crs), scat.s2["pair_default_weights"]))


@pytest.fixture(scope="module")
def zoned():
    """A household the pilot zones on the interior lot (young couple, maximum: hall arrival, half bath)."""
    from spaceplan.pipeline.main.run_modules import area_matrix_contract_for

    am = area_matrix_contract_for(lots=["interior_50x100"], households=[("young_couple", None)], zone_top=0)
    return run_stacking(am, [load_fixture("lot_capacity", "interior_50x100")], stage="S2")


def _zoned_cells(result):
    return [c for c in result["cells"] if (c.get("s2") or {}).get("status") == "zoned"]


# ------------------------------------------------------------------ catalog and data


def test_catalog_has_s2_block_and_checks_it(scat):
    assert scat.version == "0.11.0" and scat.s2["arrival_order"][0] == FAMILY_ROOM
    bad = copy.deepcopy(scat.data)
    bad["s2"]["grid_ft"] = 0
    bad["s2"]["arrival_order"] = ["hall"]
    problems = check_stacking_catalog(bad)
    assert any("grid_ft" in p for p in problems) and any("arrival_order" in p for p in problems)


def test_area_matrix_cells_carry_the_space_split():
    am = load_fixture("area_matrix", SUBJECT)
    two = [c for c in am["cells"] if c["floors"] == 2]
    assert two and all(c["space_split"] for c in two)
    for c in two:
        assert {r["floor"] for r in c["space_split"]} <= {0, 1}
        assert sorted(r["space_id"] for r in c["space_split"] if r["floor"] > 0) == sorted(c["split"]["upper_spaces"])
    assert all(c["space_split"] is None for c in am["cells"] if c["floors"] == 1)


# ------------------------------------------------------------------ grid (lib_aux)


def test_grid_counts_cuts_and_contacts():
    floor = box(0, 0, 10, 6)
    g = rasterize(floor, [("stair", box(4, 0, 6, 3))], 0.5)
    assert g.free_cells * g.cell_area == pytest.approx(60 - 6)
    i0, i1, j0, j1 = 1, 21, 1, 13                     # one cell of padding around the floor
    assert g.count((i0, i1, j0, j1)) == g.free_cells
    cum = g.profile("x", j0, j1).cumsum()
    k = cut_index(cum, i0, 48)                      # 12 sq ft = 48 cells = a column 2 ft wide (12 rows)
    assert k == 5 and g.count((i0, k, j0, j1)) == 48
    left, right = (i0, 9, j0, j1), (9, i1, j0, j1)  # cut at x = 4: the stair takes the lower 3 ft of the wall
    assert shared_contact(g, left, right) == pytest.approx(3.0)
    front = label_contact(g, left, g.labels == 0, ("low_y",))
    assert front == pytest.approx(4.0)
    assert label_contact(g, right, g.mask_of("stair")) > 0


# ------------------------------------------------------------------ relation matrix (K05 over the base)


def test_k05_overrides_the_base_matrix(ctx):
    over = {o["pair"]: o for o in ctx.matrix.overrides}
    assert over["D:living-social_bath"]["overridden_by"] == "K05-STAIR-RELATIONS"
    assert over["D:living-social_bath"]["now_kind"] == "hard"
    ids = {p.pair_id for p in ctx.matrix.pairs}
    assert "N:social_bath-living" in ids and "D:living-social_bath" not in ids


def test_stair_top_in_a_room_zone_fails_but_a_hall_with_a_closet_is_deferred(ctx):
    pair = next(p for p in ctx.matrix.pairs if p.pair_id == "N:stair_top-bedroom")
    in_room = FloorGraph({0: frozenset()}, frozenset(), {"stair_top": frozenset({0}), "bedroom": frozenset({0})})
    in_hall = FloorGraph({0: frozenset()}, frozenset({0}), {"stair_top": frozenset({0}), "bedroom": frozenset({0})})
    apart = FloorGraph({0: frozenset({1}), 1: frozenset({0})}, frozenset({0}),
                       {"stair_top": frozenset({0}), "bedroom": frozenset({1})})
    assert pair_on_floor(in_room, pair) == FAILED
    assert pair_on_floor(in_hall, pair) == DEFERRED
    assert pair_on_floor(apart, pair) == MET


# ------------------------------------------------------------------ program per floor


def test_arrival_follows_the_catalog_order(scat):
    order = scat.s2["arrival_order"]
    assert arrival_kind(order, {"family_room", "bedroom"}, 3, 1) == FAMILY_ROOM
    assert arrival_kind(order, {"bedroom"}, 1, 1) == VESTIBULE
    assert arrival_kind(order, {"bedroom"}, 3, 1) == HALL


def _rows(*spaces):
    return [{"space_id": sid, "space_type": st, "zone": zone, "floor": floor, "area_sqft": area,
             "host_space_id": None, "household_role": "general"} for sid, st, zone, floor, area in spaces]


def test_upper_units_raise_circulation_and_split_two_rooms(catalog, scat):
    rows = _rows(("foyer", "foyer", "circulation", 0, 50), ("hall", "hall", "circulation", 0, 60),
                 ("living_room", "living_room", "social", 0, 280), ("kitchen", "kitchen", "kitchen", 0, 170),
                 ("study", "study", "social", 1, 130), ("flex", "flex_room", "social", 1, 120),
                 ("bath", "bathroom", "private", 1, 55))
    sets = floor_units(catalog, scat.s2, rows, 1, 2, "stair", False, HALL)
    whole = {u.unit_id: u for u in sets[0][1]}
    share = catalog.data["circulation"]["target_fraction"]
    others = sum(u.target_sqft for k, u in whole.items() if k != "circulation")
    assert whole["circulation"].target_sqft == pytest.approx(share * others / (1 - share))
    assert whole["social"].min_width_ft == 8.0                    # widest side of study / flex, not the living's 12
    labels = [lab for lab, _, _ in sets]
    assert "split:social" in labels and "split:private" not in labels   # a lone hall bath is no part


# ------------------------------------------------------------------ K01 / K02 on synthetic floors


def _floors(upper):
    stair = box(10, 0, 13, 12.5)
    return CellFloors(ground=box(0, 0, 40, 30), upper=upper, garage=None, stair=stair, bottom_zone=box(10, -3, 13, 0),
                      top_zone=box(9.75, 12.5, 13.25, 15.5), half_bath=None, vestibule=None)


def test_ruleforge_case_stair_never_arrives_in_a_bedroom(ctx):
    """CRC passes (stair fits) but the client rule K01 fails when the upper floor has no hall to arrive into."""
    from dataclasses import replace

    units = [ZoneUnit("private", "private", ("bedroom",), frozenset({"bedroom"}), 600.0, 9.0)]
    frame = upper_frame(_floors(box(0, 0, 40, 20)), units, 0.5, [])
    search = FloorSearch(frame, replace(ctx.upper_rules, arrival=HALL), ctx.matrix)
    assert search.run() == [] and search.first_violations["K01"] > 0


def test_hall_arrival_zones_with_rooms_on_both_sides(ctx):
    from dataclasses import replace

    units = [ZoneUnit("circulation", "circulation", (), frozenset(), 120.0, 3.5),
             ZoneUnit("private:1", "private", ("suite",), frozenset({"primary_suite"}), 300.0, 11.0),
             ZoneUnit("private:2", "private", ("bed",), frozenset({"bedroom"}), 300.0, 9.0)]
    frame = upper_frame(_floors(box(0, 0, 40, 20)), units, 0.5, [])
    valid = FloorSearch(frame, replace(ctx.upper_rules, arrival=HALL), ctx.matrix, pin=0).run()
    assert valid
    best = valid[0]
    assert frame.units[best.landing_unit].zone == "circulation"
    assert {(0, 1), (0, 2)} <= set(best.links) and (1, 2) not in best.links    # rooms meet through the hall


def test_k02_receiving_ignores_a_closet_in_the_hall(ctx):
    hall = ZoneUnit("circulation", "circulation", ("hall", "laundry"), frozenset({"laundry_closet"}), 90.0, 3.5)
    room = ZoneUnit("private", "private", ("bed",), frozenset({"bedroom"}), 200.0, 9.0)
    forbidden = ["bedroom", "laundry_closet"]
    assert _receives(hall, ["foyer", "hall"], {"hall"}, forbidden)
    assert not _receives(room, ["foyer", "hall", "bedroom"], {"hall"}, forbidden)


# ------------------------------------------------------------------ end to end


def test_zoned_cell_closes_the_client_rules(zoned):
    cells = _zoned_cells(zoned)
    assert cells
    for c in cells:
        s2 = c["s2"]
        assert c["next_stage"] == "S2.1" and s2["chosen_option"] in s2["feasible_options"]
        results = {(t["rule_id"][:3], t["result"]) for t in s2["rule_traces"]}
        assert ("K01", PASS) in results and ("K02", PASS) in results and ("K05", PASS) in results
        assert s2["upper"]["landing_unit"].split(":")[0] in ("circulation", "social")
        opt = s2["options"][s2["chosen_option"]]
        if opt.get("half_bath"):
            assert ("K04", PASS) in results


def test_zones_cover_each_floor_without_overlap(zoned):
    for c in _zoned_cells(zoned):
        s1, s2 = c["s1"], c["s2"]
        core = s1["stair_core"]
        opt = s2["options"][s2["chosen_option"]]
        access = s1.get("access_core") or {}                       # S1.2: entry vestibule and void are fixed
        for level, units, fixed in ((1, s2["upper"]["units"], [access.get("void")]),
                                    (0, opt["ground"]["units"], [s1["ground"].get("garage_polygon"),
                                                                 access.get("vestibule")]
                                     + ([core["under_stair"]["half_bath"], core["under_stair"]["vestibule"]]
                                        if opt.get("half_bath") == "under_stair" else []))):
            floor = shape(s1["levels"][level]["polygon"])
            polys = [shape(u["polygon"]) for u in units]
            cover = unary_union(polys + [shape(s1["stair"]["polygon"])] + [shape(f) for f in fixed if f])
            assert floor.difference(cover).area < 0.01 * floor.area
            assert sum(a.intersection(b).area for i, a in enumerate(polys) for b in polys[i + 1:]) < 0.5


def test_start_options_are_kept_as_a_portfolio(zoned):
    for c in _zoned_cells(zoned):
        opts = c["s2"]["options"]
        assert set(opts) == {"A", "B", "C"}
        for o in opts.values():
            assert o["feasible"] == ("ground" in o)
            assert o["feasible"] or o["reason"]


def test_s2_contract_validates_and_tables(zoned):
    contract = to_contract(zoned)
    assert contract_problems(contract, "stack_plan") == []
    rows = s2_table_rows(zoned)
    assert len(rows) == sum(1 for c in zoned["cells"] if c.get("s2"))
    assert zoned["meta"]["s2"]["to_s2_1"] == len(_zoned_cells(zoned))


def test_small_upper_floor_is_reported_not_evaluated():
    result = run_stacking(load_fixture("area_matrix", SUBJECT), [load_fixture("lot_capacity", "interior_50x100")],
                          mode="all", stage="S2")
    for c in result["cells"]:
        s2 = c.get("s2")
        if s2 and s2["status"] != "zoned":
            assert s2["next_stage"] is None and s2["upper_search"]["first_violations"]
            assert {t["result"] for t in s2["rule_traces"]} <= {NOT_EVALUATED, "fail"}
            assert "backtrack" not in s2                          # option B: S2 chooses among the S1 candidates
            assert s2["stair_choice"]["chosen"] is None and s2["stair_choice"]["reason"]


def test_s2_chooses_the_stair_among_the_s1_candidates(zoned, scat):
    for c in _zoned_cells(zoned):
        choice, core = c["s2"]["stair_choice"], c["s1"]["access_core"]
        assert choice["tolerance_ft"] == scat.access_core["comparison"]["route_tolerance_ft"]
        assert 1 <= choice["zoned"] <= choice["candidates"] <= len(core["candidates"])
        chosen = choice["chosen"]
        assert chosen and chosen["s2_status"] == "zoned" and chosen["near_best"]
        assert core["provisional"] is False                       # the drawing kept is the one S2 chose
        assert core["candidates"] and "discards" in core          # and keeps what S1 handed over
        assert len(choice["ranked"]) == choice["zoned"] and choice["ranked"][0] == chosen
        assert (core["strategy"], core["stair_id"], core["placement"]) == \
            (chosen["strategy"], chosen["stair_id"], chosen["placement"])
        assert choice["portfolio"][chosen["strategy"]] == chosen     # the best of each strategy is kept
        assert any(p["pareto"] for p in choice["pareto"])


def test_deferred_door_pairs_are_traced_for_s2_1(zoned):
    for c in _zoned_cells(zoned):
        s2 = c["s2"]
        opt = s2["options"][s2["chosen_option"]]
        deferred = set(opt["ground"]["matrix_deferred"]) | set(s2["upper"]["matrix_deferred"])
        traced = [t for t in s2["rule_traces"] if t["result"] == DEFERRED_S21]
        assert bool(deferred) == bool(traced)
