"""Step 6.7a S2.2k (V6.8, client 2026-10-14): stairs on the joint first (the stair at the centre of the ground floor
and at the edge of the upper floor), no L stair, a U turned along the joint so it starts and arrives on the hall."""

import pytest
from shapely.geometry import box

from spaceplan.modules.stacking.lib.access_core import entry_door, permitted_walls
from spaceplan.modules.stacking.lib.access_rank import rank_stair_candidates
from spaceplan.modules.stacking.lib.access_stair import access_candidates, preselect
from spaceplan.modules.stacking.lib.cell_geometry import S1Context, _stair_cfg
from spaceplan.modules.stacking.lib.stacking_catalog import load_stacking_catalog
from spaceplan.modules.stacking.lib.stair import stair_shape
from spaceplan.modules.stacking.lib.stair_access import load_client_ruleset, u_min_span_ft
from spaceplan.modules.stacking.lib.stair_rules import load_stair_ruleset, stair_limits

GROUND = box(0, 0, 40, 48)
GARAGE = box(20, 0, 40, 22)
UPPER = box(0, 18, 40, 48)                # the joint runs along y = 18
LOT = box(-4, -15, 44, 61)


@pytest.fixture(scope="module")
def env():
    from spaceplan.core.lib.catalog import load_catalog

    scat, catalog = load_stacking_catalog(), load_catalog()
    srs, crs = load_stair_ruleset(), load_client_ruleset()
    limits = stair_limits(srs)
    acc = scat.access_core
    design = {**scat.stair_design, "u_well_gap_ft": acc["void"]["well_ft"], "u_min_span_ft": u_min_span_ft(crs)}
    shapes = {t["stair_id"]: stair_shape(t, scat.levels["floor_to_floor_ft"], limits, design)
              for t in scat.data["stair"]["types"]}
    ctx = S1Context(scat, limits, srs, None, crs, catalog, None, None, 44.0)
    cfg = _stair_cfg(ctx, "hall")
    acc = {**acc, "band": crs.params("K12-STAIR-BAND")}
    door = entry_door(GROUND, GARAGE, "right", (0.0, 10.0), acc)
    walls = permitted_walls(GROUND, UPPER, GARAGE, LOT, acc)
    required = crs.params("K06-STAIR-NATURAL-LIGHT")["required_by_strategy"]
    found, _ = access_candidates(UPPER, GROUND, GARAGE, door, walls, shapes, cfg, acc, srs, required)
    return {"scat": scat, "crs": crs, "acc": acc, "found": found}


def test_the_client_order_puts_the_joint_first_and_drops_the_l(env):
    k07 = env["crs"].params("K07-STAIR-STRATEGY")
    assert k07["preference"][0] == "B" and k07["fallback"] == "A"
    st = env["acc"]["strategies"]
    assert all("l_turn" not in v["stair_ids"] for k, v in st.items() if k != "fallback_stair_ids")
    assert st["B"]["stair_ids"][0] == "u_turn"
    assert env["acc"]["comparison"]["stair_order"][0] == "u_turn"
    assert all(a.stair_id != "l_turn" for a in env["found"])


def test_a_u_on_the_joint_can_turn_along_it(env):
    joint_u = [a for a in env["found"] if a.strategy == "B" and a.stair_id == "u_turn"]
    assert joint_u and any(a.along for a in joint_u) and any(not a.along for a in joint_u)
    picked = preselect(env["found"], 4, list(env["acc"]["comparison"]["stair_order"]))
    b = [a for a in picked if a.strategy == "B"]
    assert b[0].stair_id == "u_turn" and b[0].along                 # the U turned along the joint first
    assert any(a.stair_id == "u_turn" and not a.along for a in b)  # and the other turn too
    assert any(a.stair_id.startswith("straight") for a in b)


def test_ranking_follows_strategy_then_stair_then_turn():
    trials = [{"strategy": "B", "stair_id": "straight", "along": True, "route_ft": 30.0, "occupied_sqft": 40.0},
              {"strategy": "B", "stair_id": "u_turn", "along": False, "route_ft": 31.0, "occupied_sqft": 80.0},
              {"strategy": "B", "stair_id": "u_turn", "along": True, "route_ft": 32.0, "occupied_sqft": 80.0},
              {"strategy": "A", "stair_id": "u_turn", "along": True, "route_ft": 29.0, "occupied_sqft": 80.0}]
    ranked = rank_stair_candidates(trials, 6.0, ["B", "A", "D", "C"], None, ["u_turn", "straight"])
    assert [r.trial for r in ranked] == [trials[2], trials[1], trials[0], trials[3]]
