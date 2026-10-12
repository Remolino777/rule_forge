"""Step 6.7a S2.2f: structure of the upper floor (shared grid, walls on walls, beams, posts, bearing spans), compact
stair arrival and grouped bedroom doors."""

import numpy as np
import pytest
from shapely.geometry import box

from spaceplan.modules.design.lib.design_registry import load_registry
from spaceplan.modules.stacking.lib.stacking_catalog import load_stacking_catalog
from spaceplan.modules.stacking.lib.zone_cell import structure_settings
from spaceplan.modules.stacking.lib_aux.structure_grid import (
    bearing_spans,
    edge_walls,
    grid_offset,
    snap_line,
    support_report,
    window,
)
from spaceplan.modules.stacking.lib_aux.zone_grid import rasterize


def _floor(ny, nx, inner=(1, -1, 1, -1)):
    lab = np.zeros((ny, nx), dtype=int)
    j0, j1, i0, i1 = inner
    lab[j0:j1, i0:i1] = 1
    return lab


# ------------------------------------------------------------------ data


def test_registry_carries_structure_arrival_and_grouping():
    reg = load_registry()
    assert reg.self_check() == []
    v = reg.baseline()
    assert v["structure.enabled"] and v["structure.joist_span_max_ft"] == 20.0
    assert v["structure.axes_rule"] == "bearing" and v["structure.support_min_fraction"] == 0.0
    assert v["circulation.arrival.node_short_side_max_ft"] == 8.0 and v["circulation.arrival.single_hall"]
    assert v["door.grouping.nearest_corner"] and v["upper.cantilever_depth_ft"] == 3.0
    assert v["structure.code.braced_line_offset_max_ft"] == 4.0
    st = structure_settings(v, load_stacking_catalog().s2)
    assert st["node_cells"] == 16 and st["snap_cells"] == 5 and st["pair_candidates"] == 3
    assert structure_settings({**v, "structure.enabled": False}, load_stacking_catalog().s2) is None


# ------------------------------------------------------------------ geometry


def test_anchored_grids_share_their_lines():
    ground = box(0.0, 0.0, 40.0, 30.0)
    upper = box(0.0, 12.25, 40.0, 30.0)                  # cut at a quarter foot: off the 0.5 ft lines
    g = rasterize(ground, [], 0.5)
    u_free = rasterize(upper, [], 0.5)
    with pytest.raises(ValueError):
        grid_offset(u_free.x0, u_free.y0, g.x0, g.y0, 0.5)
    u = rasterize(upper, [], 0.5, anchor=ground.bounds[:2])
    assert grid_offset(u.x0, u.y0, g.x0, g.y0, 0.5) == (0, 24)


def test_edges_and_window():
    lab = _floor(4, 5)
    v, h = edge_walls(lab, 0)
    assert v.shape == (4, 6) and h.shape == (5, 5)
    assert v[1, 1] and v[1, 4] and not v[1, 2] and h[1, 2] and h[3, 2]
    w = window(v, (4, 6), 1, 0)
    assert w[1, 0] == v[1, 1] and not w[1, 5]


def test_walls_on_walls_beams_and_posts():
    g = _floor(12, 22)
    g[1:11, 11:21] = 2                                    # ground wall on x = 11
    u = g.copy()
    u[6:11, 1:11] = 3                                     # upper wall on y = 6 over the open ground room
    rep, bad = support_report(u, 0, g, 0, 0, 0, 1.0, 0.5, 20.0)
    runs = {(r["vertical"], r["line"]): r for r in rep.runs if r["interior"]}
    assert runs[(True, 11)]["supported_ft"] == 10.0 and runs[(False, 6)]["supported_ft"] == 0.0
    assert runs[(False, 6)]["beams_ft"] == [10.0]         # perimeter to the crossing wall: a 10 ft beam
    assert bad == ["structure:support:y6"]
    rep0, bad0 = support_report(u, 0, g, 0, 0, 0, 1.0, 0.0, 20.0)
    assert bad0 == [] and rep0.interior_fraction == pytest.approx(0.5)
    _rep8, bad8 = support_report(u, 0, g, 0, 0, 0, 1.0, 0.0, 8.0)
    assert bad8 == ["structure:beam:y6"]


def test_outer_wall_over_the_ground_interior_gets_posts():
    g = _floor(40, 12)                                    # ground 10 x 38
    u = np.zeros_like(g)
    u[1:39, 1:6] = 1                                      # upper: the west half; its east wall stands mid-room
    rep, bad = support_report(u, 0, g, 0, 0, 0, 1.0, 0.0, 20.0)
    assert bad == [] and rep.posts >= 1 and max(rep.beams_ft) <= 20.0


def test_bearing_spans_need_a_line_within_the_joist_span():
    g = _floor(32, 22)
    g[16:31, 1:21] = 2                                    # ground wall on y = 16 (20 x 30 floor)
    rep, _ = support_report(g, 0, g, 0, 0, 0, 1.0, 0.5, 20.0)
    b = bearing_spans(g, 0, rep, 1.0, 20.0, 0.5, 20.0)
    assert b["ok"] and b["span_y_ft"] == 15.0
    wide = _floor(32, 32)                                 # 30 x 30 without interior walls
    rep, _ = support_report(wide, 0, wide, 0, 0, 0, 1.0, 0.5, 20.0)
    assert not bearing_spans(wide, 0, rep, 1.0, 20.0, 0.5, 20.0)["ok"]


def test_snap_moves_a_cut_to_the_nearest_wall_line():
    g = _floor(12, 22)
    g[1:11, 11:21] = 2
    v, _ = edge_walls(g, 0)
    assert snap_line(v, True, 13, 1, 11, 3, 0.5, 1, 21) == 11
    assert snap_line(v, True, 16, 1, 11, 3, 0.5, 1, 21) == 16          # out of reach: unchanged


def test_the_llm_reads_and_changes_the_structure_criteria():
    from spaceplan.modules.design.lib import design_profile as dp
    from spaceplan.modules.design.lib.llm_tools import dispatch

    reg = load_registry()
    prof = dp.new_profile(reg, "llm")
    res, _ = dispatch(reg, prof, "get_criteria", {"group": "structure"}, "llm", "2026-10-12")
    ids = {r["id"] for r in res["rules"]}
    assert res["ok"] and {"structure.joist_span_max_ft", "circulation.arrival.node_short_side_max_ft",
                          "door.grouping.nearest_corner", "upper.cantilever_depth_ft"} <= ids
    res, prof = dispatch(reg, prof, "set_criteria", {"group": "structure", "changes": {
        "support_min_fraction": 0.5, "axes_rule": "all_zone_walls"}, "reason": "stricter stacking"}, "llm", "2026-10-12")
    assert res["ok"] and dp.effective_values(reg, prof)["structure.support_min_fraction"] == 0.5
    res, _ = dispatch(reg, prof, "set_criteria", {"group": "structure", "changes": {"joist_span_max_ft": 40},
                                                  "reason": "x"}, "llm", "2026-10-12")
    assert not res["ok"]                                   # outside the range
