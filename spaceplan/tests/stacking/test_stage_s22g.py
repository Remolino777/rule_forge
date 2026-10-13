"""Step 6.7a S2.2g: structural frame first (bays on shared axes), zoning on the frame, surplus to roof or porch."""

from dataclasses import replace

import pytest
from shapely.geometry import box

from spaceplan.modules.design.lib.design_registry import load_registry
from spaceplan.modules.stacking.lib.core_zoning import FloorSearch
from spaceplan.modules.stacking.lib.floor_frame import CellFloors, ZoneUnit, upper_frame
from spaceplan.modules.stacking.lib.frame_bands import (
    HIGH,
    LOW,
    PORCH,
    ROOF,
    UNBUILT,
    FrameGuide,
    _ordered_groups,
    bay_ranges,
    framed_topologies,
    surplus_kind,
)
from spaceplan.modules.stacking.lib.stacking_catalog import load_stacking_catalog
from spaceplan.modules.stacking.lib.structural_frame import (
    CORE,
    FREE,
    GARAGE,
    SINGLE,
    SPINE,
    TWO_BAY,
    build_frames,
    frame_settings,
)
from spaceplan.modules.stacking.lib.zone_cell import frame_guide, structure_settings
from spaceplan.modules.stacking.lib_aux.frame_geometry import axis_window, edge_lines, extent, snap

HALL = "hall"


@pytest.fixture(scope="module")
def values():
    return load_registry().baseline()


@pytest.fixture(scope="module")
def st(values):
    return frame_settings(values, values["circulation.hall.design_width_ft"], 0.5)


def _floors(upper, ground=None, garage=None, stair=None):
    stair = stair or box(10, 0, 13, 12.5)
    return CellFloors(ground=ground or box(0, 0, 40, 40), upper=upper, garage=garage, stair=stair,
                      bottom_zone=box(10, -3, 13, 0), top_zone=box(9.75, 12.5, 13.25, 15.5), half_bath=None,
                      vestibule=None)


# ------------------------------------------------------------------ data


def test_registry_carries_the_frame_and_the_roofs(values):
    reg = load_registry()
    assert reg.self_check() == []
    assert values["structure.frame.enabled"] and values["structure.frame.bay_min_ft"] == 10.0
    assert values["structure.frame.spine_from_ft"] == 30.0 and values["structure.frame.ground_surplus"] == "either"
    assert values["structure.roofs.multi_plane"] and values["structure.roofs.lower_kind"] == "shed"
    assert reg.kinds()["structure.frame.enabled"] == "hard"
    s = structure_settings(values, load_stacking_catalog().s2, reg.kinds())
    assert s["frame"]["joist"] == 20.0 and s["frame"]["hall"] == 3.5 and s["frame_hard"]
    assert s["surplus_min_cells"] == 60                     # 15 sq ft in 0.5 ft cells
    assert structure_settings(values, load_stacking_catalog().s2, {"structure.frame.enabled": "soft"})[
        "frame_hard"] is False
    assert frame_settings({**values, "structure.frame.enabled": False}, 3.5, 0.5) is None


def test_the_llm_reaches_the_frame_criteria():
    from spaceplan.modules.design.lib import design_profile as dp
    from spaceplan.modules.design.lib.llm_tools import dispatch

    reg = load_registry()
    prof = dp.new_profile(reg, "llm")
    res, _ = dispatch(reg, prof, "get_criteria", {"group": "structure"}, "llm", "2026-10-12")
    ids = {r["id"] for r in res["rules"]}
    assert {"structure.frame.spine_from_ft", "structure.frame.ground_surplus", "structure.roofs.lower_pitch"} <= ids
    res, prof = dispatch(reg, prof, "set_criteria", {"group": "structure", "changes": {
        "frame.ground_surplus": "porch"}, "reason": "client wants porches"}, "llm", "2026-10-12")
    assert res["ok"] and dp.effective_values(reg, prof)["structure.frame.ground_surplus"] == "porch"


# ------------------------------------------------------------------ geometry and frame


def test_frame_geometry():
    poly = box(0, 0, 30, 20)
    assert extent(poly, "x") == (0, 30) and extent(poly, "y") == (0, 20)
    assert sorted(edge_lines(poly, "x")) == [0.0, 30.0]
    assert snap(10.3, 0.5, 0.0) == 10.5
    assert axis_window(0, 26, 10, 20) == (10, 16)           # both bays between 10 and 20 ft
    assert axis_window(0, 35, 10, 20, 3.5) == (11.5, 20)    # with a central hall
    assert axis_window(0, 18, 10, 20) is None


def test_patterns_by_the_short_side(st):
    single = build_frames(_floors(box(0, 0, 40, 18)), st)
    assert len(single) == 1 and single[0].pattern == SINGLE and single[0].axis == "y" and not single[0].axes
    two = build_frames(_floors(box(0, 0, 40, 26)), st)
    assert two and all(f.pattern == TWO_BAY and len(f.axes) == 1 for f in two)
    for f in two:
        assert all(st["bay_min"] - 1e-6 <= b - a <= st["joist"] + 1e-6 for a, b in f.bays())
    spine = build_frames(_floors(box(0, 0, 50, 34)), st)
    assert spine and spine[0].pattern == SPINE
    a0, a1 = spine[0].axes
    assert a1.pos - a0.pos == pytest.approx(st["hall"])
    assert spine[0].spine_bay == 1
    assert build_frames(_floors(box(0, 0, 60, 46), ground=box(0, 0, 60, 46)), st) == []   # deeper than 2 joists


def test_the_stair_core_and_the_garage_are_axis_candidates(st):
    # stair long walls on y = 12 and y = 15 (lines along x: the axes of a floor narrower in y)
    floors = _floors(box(0, 0, 40, 26), stair=box(10, 12, 20, 15),
                     garage=box(20, 0, 40, 14))
    frames = build_frames(floors, st)
    tags = {a.tag for f in frames for a in f.axes}
    assert CORE in tags or GARAGE in tags
    fixed = [f for f in frames if f.axes[0].tag != FREE]
    assert fixed and fixed[0].axes[0].window[0] == fixed[0].axes[0].window[1]    # a fixed element does not move
    assert frames[0].score >= frames[-1].score


def test_the_joint_is_a_ground_line(st):
    # upper floor on the front half of a deeper ground floor: its rear edge stands over the ground interior
    f = build_frames(_floors(box(0, 0, 40, 18), ground=box(0, 0, 40, 36)), st)[0]
    assert f.joints == (18.0,) and 18.0 in f.ground_lines()
    d = f.to_dict()
    assert d["pattern"] == SINGLE and d["bays_ft"] == [18.0]


# ------------------------------------------------------------------ framed topologies


def test_ordered_groups_and_bays():
    groups = list(_ordered_groups((0, 1, 2), 2))
    assert len(groups) == 6 * 2 and ((0,), (1, 2)) in groups
    assert list(_ordered_groups((0,), 2)) == []
    assert bay_ranges(0, 10, (4,)) == [(0, 4), (4, 10)] and bay_ranges(0, 10, (12,)) is None


def test_spine_keeps_the_hall_alone_in_the_middle_bay():
    fg = FrameGuide("y", (20, 27), fixed=True, spine=(20, 27))
    tops = list(framed_topologies(4, 0, fg))
    assert tops and all(t[1][1] == (0,) and len(t[1]) == 3 and t[2] == (20, 27) for t in tops)
    assert list(framed_topologies(4, None, fg)) == []         # no circulation unit: no central hall


def test_upper_strip_runs_along_the_interior_axis():
    fg = FrameGuide("y", (24,), fixed=True, strip=True)
    tops = list(framed_topologies(3, 0, fg))
    strips = [t for t in tops if t[3] is not None]
    assert strips
    for _, bands, _, split in strips:                      # the hall strip is next to the axis
        assert (bands[1] == (0,)) if split == 0 else (bands[1] == (0,) and split == 1)


def test_ground_band_cut_on_a_frame_line_or_by_area():
    fg = FrameGuide("y", (30, 40), False, max_cuts=1, free_cut=True, surplus="either")
    tops = list(framed_topologies(3, 0, fg))
    cuts = {t[2] for t in tops}
    assert cuts == {(), (30,), (40,)}
    spine = FrameGuide("y", (20, 27), spine=(20, 27), max_cuts=2)
    sets = {t[2] for t in framed_topologies(4, 0, spine)}
    assert sets == {(20, 27), (20,), (27,), ()}               # a frame line may run inside a zone (wall or beam)
    assert any(t[2] == () and t[3] == 0 for t in tops)       # the S2 band cut by area, on the frame's axis


def test_surplus_kinds_follow_the_policy():
    role = {"low_y": "main_street", "high_y": "garden", "low_x": "street_view", "high_x": "street_view"}.get
    assert surplus_kind(ROOF, "x", LOW, role) == ROOF
    assert surplus_kind("either", "x", HIGH, role) == PORCH   # garden end
    assert surplus_kind("either", "y", HIGH, role) == UNBUILT  # side end
    assert surplus_kind(PORCH, "y", LOW, role) == PORCH and surplus_kind(UNBUILT, "x", LOW, role) == UNBUILT


# ------------------------------------------------------------------ zoning on the frame


def _upper_units():
    return [ZoneUnit("circulation", "circulation", (), frozenset(), 110.0, 3.5),
            ZoneUnit("private:1", "private", ("suite",), frozenset({"primary_suite"}), 300.0, 11.0),
            ZoneUnit("private:2", "private", ("bed",), frozenset({"bedroom"}), 200.0, 9.0),
            ZoneUnit("private:3", "private", ("bed2",), frozenset({"bedroom"}), 200.0, 9.0)]


def test_upper_floor_zones_on_its_bays_with_roof_surplus(st):
    from spaceplan.core.lib.catalog import load_catalog
    from spaceplan.modules.stacking.lib.stair_access import load_client_ruleset, relations
    from spaceplan.modules.stacking.lib.zone_cell import s2_context
    from spaceplan.modules.stacking.lib.zone_relations import build_matrix

    catalog, scat = load_catalog(), load_stacking_catalog()
    crs = load_client_ruleset()
    ctx = s2_context(scat, catalog, crs, build_matrix(catalog, relations(crs), scat.s2["pair_default_weights"]))
    floors = _floors(box(0, 0, 40, 26))
    frame = build_frames(floors, st)[0]
    uf = upper_frame(floors, _upper_units(), 0.5, [], anchored=True)
    fg = frame_guide(frame, uf, {"surplus_min_cells": 60, "ground_surplus": "either", "line_bonus": 0.1})
    assert not fg.fixed and fg.strip and len(fg.lines) == 1 and fg.surplus == ROOF
    valid = FloorSearch(uf, replace(ctx.upper_rules, arrival=HALL), ctx.matrix, pin=0, fguide=fg).run()
    assert valid
    cut = fg.lines[0]
    for rz in valid[:20]:
        assert len(rz.topology) == 4 and rz.sframe is frame
        if cut in rz.topology[2]:
            for r in rz.rects:                                 # no unit crosses an axis that is a band cut
                assert r[3] <= cut or r[2] >= cut
        assert all(kind == ROOF for _, kind in rz.open_air)
        for k, u in enumerate(uf.units):                       # within the band tolerance of the program area
            if u.zone != "circulation":
                assert rz.counts[k] <= max(rz.targets[k], uf.targets[k]) * 1.3


# ------------------------------------------------------------------ positions (MILP)


def test_milp_model_solves_a_small_alignment():
    from spaceplan.modules.stacking.lib_aux.milp_tools import Model

    m = Model()
    x = m.var(10, 20, integer=True)
    y = m.var(14, 14, integer=True)                          # a fixed wall below
    m.abs_dev({x: 1.0}, -11.0, 1.0)                          # x wants to be 11 ...
    z = m.binary(-5.0)                                       # ... but standing on y is worth 5
    m.row({x: 1.0, y: -1.0, z: 20.0}, hi=20.0)
    m.row({x: -1.0, y: 1.0, z: 20.0}, hi=20.0)
    sol = m.solve()
    assert sol is not None and round(sol[x]) == 14 and sol[z] > 0.5
    m2 = Model()
    a = m2.var(0, 1, integer=True)
    m2.row({a: 1.0}, lo=2.0)
    assert m2.solve() is None                                # infeasible


def test_positions_settings_follow_the_registry(values):
    from spaceplan.modules.stacking.lib.frame_positions import positions_settings

    s = positions_settings(values, load_stacking_catalog().s2)
    assert s == {"window_cells": 4, "reach_cells": 5, "surplus_weight": 0.2, "align_bonus_sqft": 10.0}
    assert positions_settings({**values, "structure.frame.optimize": False}, load_stacking_catalog().s2) is None


# ------------------------------------------------------------------ roofs in several planes


def _s1_block(ground, upper, garage=None):
    from shapely.geometry import mapping

    return {"levels": [{"polygon": mapping(ground), "wall_top_ft": 10.0},
                       {"polygon": mapping(upper), "wall_top_ft": 20.0}],
            "ground": {"garage_polygon": mapping(garage) if garage is not None else None},
            "roof": {"kept_roof_id": "pitched_4_12", "kept_ridge": "along_x",
                     "checks": [{"roof_id": "pitched_4_12", "ridge": "along_x", "top_ft": 24.0}]}}


def test_roof_pieces_upper_lower_garage_and_porch(values):
    from spaceplan.modules.stacking.lib.roof_planes import SHED, roof_pieces, roof_settings

    st = roof_settings(values)
    assert st == {"lower_kind": "shed", "porch_kind": "shed", "pitch": 0.25, "min_piece": 20.0}
    ground, upper, garage = box(0, 0, 40, 40), box(0, 0, 40, 22), box(20, 0, 40, 20)
    s1 = _s1_block(ground, upper, garage)
    porch = box(0, 36, 20, 40)                                # the rear end of a ground band
    out = roof_pieces(s1, load_stacking_catalog(), st, [box(30, 18, 40, 22)], [porch], [], 3)
    by = {}
    for p in out["pieces"]:
        by.setdefault(p["piece"], []).append(p)
    assert out["multi_plane"] and set(by) == {"upper", "lower", "garage", "porch"}
    assert by["garage"][0]["area_sqft"] == pytest.approx(20)   # the garage under the open end of an upper bay
    up = by["upper"][0]
    assert up["kind"] == "pitched" and up["top_ft"] == 24.0 and up["area_sqft"] == pytest.approx(880 - 40)
    low = by["lower"]
    assert sum(p["area_sqft"] for p in low) == pytest.approx(40 * 40 - 840 - 80 - 20)
    big = max(low, key=lambda p: p["area_sqft"])
    assert big["kind"] == SHED and big["fall"][1] > 0.9         # falls away from the upper wall (toward the rear)
    assert big["top_ft"] == pytest.approx(10.0 + 0.25 * big["depth_ft"])
    assert by["porch"][0]["kind"] == SHED and by["porch"][0]["area_sqft"] == pytest.approx(80)
    off = roof_pieces(s1, load_stacking_catalog(), None, [], [], [], 3)
    assert not off["multi_plane"] and [p["piece"] for p in off["pieces"]] == ["upper"]


def test_roof_geometry_helpers():
    from shapely.geometry import LineString

    from spaceplan.modules.stacking.lib_aux.roof_geometry import (
        fall,
        leaning_edge,
        long_axis,
        parts,
    )

    piece = box(0, 22, 40, 36)
    edge = leaning_edge(piece, box(0, 0, 40, 22))
    assert edge is not None and LineString(edge).length == pytest.approx(40)
    direction, depth = fall(piece, edge)
    assert direction[1] == pytest.approx(1.0) and depth == pytest.approx(14)
    d, length, width = long_axis(piece)
    assert abs(d[0]) == pytest.approx(1.0) and length == pytest.approx(40) and width == pytest.approx(14)
    assert [round(p.area) for p in parts(box(0, 0, 2, 2).union(box(5, 0, 15, 2)), 5)] == [20]


def test_a_circulation_strip_holding_the_stair_keeps_a_hall_beside_it(st):
    from spaceplan.core.lib.catalog import load_catalog
    from spaceplan.modules.stacking.lib.stair_access import load_client_ruleset, relations
    from spaceplan.modules.stacking.lib.zone_cell import s2_context
    from spaceplan.modules.stacking.lib.zone_relations import build_matrix

    catalog, scat = load_catalog(), load_stacking_catalog()
    crs = load_client_ruleset()
    ctx = s2_context(scat, catalog, crs, build_matrix(catalog, relations(crs), scat.s2["pair_default_weights"]))
    floors = _floors(box(0, 0, 26, 40), stair=box(0, 10, 3, 22.5))      # stair along the low long side (x 0..3)
    uf = upper_frame(floors, _upper_units(), 0.5, [], anchored=True)
    s = FloorSearch(uf, ctx.upper_rules, ctx.matrix)
    i0 = round((0.0 - uf.grid.x0) / 0.5)
    stair_hi = i0 + 6                                          # 3 ft of stair
    hall = 7                                                   # 3.5 ft of hall
    assert s._clear_stair("x", stair_hi + 2, i0, i0 + 52, True, False, 0) == stair_hi + hall   # sliver widened
    assert s._clear_stair("x", stair_hi + hall + 3, i0, i0 + 52, True, False, 0) == stair_hi + hall + 3   # kept
