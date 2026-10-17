"""Step V6.8 k1b (client 2026-10-14 12:47 and 2026-10-17 01:38): the stair core first — clear start and arrival
zones of the stair's width and 4 ft deep inside one circulation space, the stair and its zones a block that S2 pins
on one unit, the rear joint as an anchor with a preselection slot per joint edge, the half bath under the stair only
toward the foyer or a hall (else a pantry) and never beside the stair."""

import numpy as np
import pytest
from shapely.geometry import LineString, box

from spaceplan.modules.design.lib.design_registry import load_registry
from spaceplan.modules.stacking.lib.access_core import entry_door, permitted_walls
from spaceplan.modules.stacking.lib.access_stair import access_candidates, preselect
from spaceplan.modules.stacking.lib.cell_geometry import S1Context, _stair_cfg
from spaceplan.modules.stacking.lib.plan_levels import OVER_GARAGE, upper_floor
from spaceplan.modules.stacking.lib.space_rules import design_view
from spaceplan.modules.stacking.lib.stacking_catalog import load_stacking_catalog
from spaceplan.modules.stacking.lib.stair import stair_shape
from spaceplan.modules.stacking.lib.stair_access import load_client_ruleset, u_min_span_ft, under_stair_use
from spaceplan.modules.stacking.lib.stair_core import (
    REAR_EDGE,
    SIDE_EDGE,
    CoreSettings,
    clear_zone_violation,
    core_settings,
    edge_class,
    half_bath_beside_stair,
    touched_score,
    zone_cfg,
)
from spaceplan.modules.stacking.lib.stair_rules import load_stair_ruleset, stair_limits
from spaceplan.modules.stacking.lib.structural_frame import CORE, _fixed_lines
from spaceplan.modules.stacking.lib_aux.core_cells import block_bounds, labels_touching, rects_touching

GROUND = box(0, 0, 40, 48)
GARAGE = box(20, 0, 40, 22)
OVER = box(10, 0, 40, 22)                 # over the garage: side joint x = 10, rear joint y = 22
LOT = box(-4, -15, 44, 61)


@pytest.fixture(scope="module")
def core():
    values, kinds = design_view()
    return core_settings(values, kinds)


@pytest.fixture(scope="module")
def env(core):
    from spaceplan.core.lib.catalog import load_catalog

    scat, catalog = load_stacking_catalog(), load_catalog()
    srs, crs = load_stair_ruleset(), load_client_ruleset()
    limits = stair_limits(srs)
    acc = scat.access_core
    design = {**scat.stair_design, "u_well_gap_ft": acc["void"]["well_ft"], "u_min_span_ft": u_min_span_ft(crs)}
    shapes = {t["stair_id"]: stair_shape(t, scat.levels["floor_to_floor_ft"], limits, design)
              for t in scat.data["stair"]["types"]}
    ctx = S1Context(scat, limits, srs, None, crs, catalog, None, None, 44.0, 0.0, core)
    base = _stair_cfg(ctx, "hall")
    cfg = zone_cfg(base, core)
    acc = {**acc, "band": crs.params("K12-STAIR-BAND")}
    door = entry_door(GROUND, GARAGE, "right", (0.0, 10.0), acc)
    walls = permitted_walls(GROUND, OVER, GARAGE, LOT, acc)
    required = crs.params("K06-STAIR-NATURAL-LIGHT")["required_by_strategy"]
    found, _ = access_candidates(OVER, GROUND, GARAGE, door, walls, shapes, cfg, acc, srs, required)
    return {"scat": scat, "crs": crs, "acc": acc, "found": found, "cfg": cfg, "base": base, "shapes": shapes}


# ------------------------------------------------------------------ registry and rules


def test_the_registry_holds_the_core_decisions(core):
    reg = load_registry()
    p = reg.get("stair.arrival_clear.depth_ft")
    assert p.value == 4.0 and p.kind == "hard" and p.unit == "ft"
    for pid in ("stair.arrival_clear.width_from_stair", "stair.arrival_clear.single_space",
                "stair.arrival_clear.circulation_only", "stair.core.block_first", "stair.joint.rear_anchor"):
        assert reg.get(pid).value is True and reg.get(pid).kind == "hard"
    assert reg.get("stair.joint.slots_per_edge").value == 1
    assert core.depth_ft == 4.0 and core.single_space and core.circulation_only and core.block_first
    assert core.rear_anchor and core.slots_per_edge == 1 and core.touched_target == 1


def test_a_soft_single_space_is_not_enforced():
    values, kinds = design_view()
    soft = core_settings(values, {**kinds, "stair.arrival_clear.single_space": "soft"})
    assert not soft.single_space and soft.circulation_only
    assert core_settings({}) == CoreSettings()                 # an empty registry: the pre-k1b behaviour


def test_k13_half_bath_only_toward_the_foyer_or_a_hall():
    crs = load_client_ruleset()
    assert crs.version == "0.8.0"
    k13 = crs.params("K13-UNDER-STAIR-USE")
    assert k13["otherwise"] == "pantry" and k13["half_bath_beside_stair"] is False
    assert under_stair_use(crs, "foyer", True)["use"] == "half_bath"
    assert under_stair_use(crs, "hall", True)["use"] == "half_bath"
    assert under_stair_use(crs, None, True)["use"] == "half_bath"            # side decided in S2 (K04 vestibule)
    assert under_stair_use(crs, "living_room", True)["use"] == "storage"     # the vestibule-to-living variant is gone
    assert under_stair_use(crs, "kitchen", True)["use"] == "storage"         # K03
    assert under_stair_use(crs, "foyer", False)["use"] == "storage"          # does not fit: pantry
    assert under_stair_use(crs, "living_room", True)["rule"] == "K13-UNDER-STAIR-USE"


# ------------------------------------------------------------------ S1: clear zones and joint edges


def test_both_zones_are_four_feet_deep_and_as_wide_as_the_stair(env):
    assert env["cfg"]["landing_ft"] == 4.0 and env["cfg"]["top_depth_ft"] >= 4.0
    assert env["base"]["landing_ft"] < 4.0                    # the code minimum before k1b
    assert env["found"]
    for a in env["found"]:
        c = a.cand
        w = c.shape.width_ft
        for z in (c.bottom_zone, c.top_zone):
            x0, y0, x1, y1 = z.bounds
            assert min(x1 - x0, y1 - y0) >= min(4.0, w) - 1e-6
            assert max(x1 - x0, y1 - y0) >= w - 1e-6
            assert z.intersection(c.geom.footprint).area <= 1e-6


def test_a_u_along_the_joint_starts_and_arrives_on_the_same_side(env):
    us = [a for a in env["found"] if a.strategy == "B" and a.stair_id == "u_turn" and a.along]
    assert us
    for a in us:
        fp, bz, tz = a.cand.geom.footprint, a.cand.bottom_zone, a.cand.top_zone
        shared_b = fp.boundary.intersection(bz.buffer(1e-6))
        shared_t = fp.boundary.intersection(tz.buffer(1e-6))
        assert shared_b.length > 0 and shared_t.length > 0
        assert _side(fp, bz) == _side(fp, tz) is not None     # both beyond the same edge of the footprint


def _side(fp, z, eps=1e-6):
    fx0, fy0, fx1, fy1 = fp.bounds
    zx0, zy0, zx1, zy1 = z.bounds
    for name, ok in (("low_y", zy1 <= fy0 + eps), ("high_y", zy0 >= fy1 - eps), ("low_x", zx1 <= fx0 + eps),
                     ("high_x", zx0 >= fx1 - eps)):
        if ok:
            return name
    return None


def test_edge_class_of_the_joint_lines():
    assert edge_class(LineString([(10, 22), (40, 22)])) == REAR_EDGE
    assert edge_class(LineString([(10, 0), (10, 22)])) == SIDE_EDGE


def test_the_preselection_keeps_a_slot_on_the_rear_joint(env, core):
    order = list(env["acc"]["comparison"]["stair_order"])
    found = env["found"]
    rear = [a for a in found if a.wall.kind == "joint" and edge_class(a.wall.line) == REAR_EDGE]
    assert rear, "the rear joint over the garage offers candidates"
    picked = preselect(found, 4, order, core.slots_per_edge, (SIDE_EDGE, REAR_EDGE))
    b = [a for a in picked if a.strategy == "B"]
    assert any(edge_class(a.wall.line) == REAR_EDGE for a in b)
    first_rear = next(a for a in b if edge_class(a.wall.line) == REAR_EDGE)
    if any(a.stair_id == "u_turn" and a.along for a in rear):
        assert first_rear.stair_id == "u_turn" and first_rear.along
    assert len(b) <= 4


# ------------------------------------------------------------------ upper floor over the garage


def test_the_room_over_the_garage_grows_sideways_over_the_front():
    geo = load_stacking_catalog().geometry
    small = upper_floor(OVER_GARAGE, GROUND, 550.0, GARAGE, "right", geo)
    large = upper_floor(OVER_GARAGE, GROUND, 880.0, GARAGE, "right", geo)
    for c in (small, large):
        x0, y0, x1, y1 = c.polygon.bounds
        assert (y0, y1) == (0.0, 22.0)                       # garage depth: never toward the rear
        assert any(abs(j.coords[0][1] - 22.0) < 1e-6 and abs(j.coords[-1][1] - 22.0) < 1e-6 for j in c.joints)
    assert large.polygon.bounds[0] < small.polygon.bounds[0]   # wider over the front of the house


# ------------------------------------------------------------------ S2: the block and the units it touches


def test_block_bounds_and_touched_units():
    land = np.zeros((10, 10), dtype=bool)
    stair = np.zeros((10, 10), dtype=bool)
    stair[2:6, 3:5] = True
    land[6:8, 3:5] = True
    assert block_bounds(land, stair) == (3, 5, 2, 8)
    one = [(0, 10, 0, 10)]
    two = [(0, 4, 0, 10), (4, 10, 0, 10)]
    assert rects_touching((10, 10), one, stair) == 1
    assert rects_touching((10, 10), two, stair) == 2
    cs = CoreSettings(touched_target=1)
    assert touched_score(1, cs) == 1.0 and touched_score(2, cs) < 1.0 and touched_score(3, cs) < touched_score(2, cs)


def test_the_frame_takes_the_block_edges():
    from spaceplan.modules.stacking.lib.floor_frame import CellFloors

    floors = CellFloors(ground=GROUND, upper=box(0, 18, 40, 48), garage=None, stair=box(10, 20, 18.2, 29.9),
                        bottom_zone=box(10, 29.9, 13, 33.9), top_zone=box(15.2, 29.9, 18.2, 33.9), half_bath=None,
                        vestibule=None, entry_vestibule=None, void=None, door_area=None)
    plain = {c for c, _ in _fixed_lines(floors, "y", 18, 48)}
    block = {c for c, t in _fixed_lines(floors, "y", 18, 48, core_block=True) if t == CORE}
    assert 33.9 not in plain and any(abs(c - 33.9) < 1e-6 for c in block)


# ------------------------------------------------------------------ S2.1 checks


class _Spec:
    def __init__(self, space_type, fixed=False):
        self.space_type, self.fixed = space_type, fixed


def test_the_clear_zone_lies_in_one_circulation_space(core):
    specs = [_Spec("foyer"), _Spec("living_room"), _Spec("entry_vestibule", True), _Spec("hall")]
    labels = np.zeros((6, 6), dtype=int)
    land = np.zeros((6, 6), dtype=bool)
    land[2:4, 2:4] = True
    assert clear_zone_violation(labels, specs, land, core, ("foyer", "hall"), ("entry_vestibule",)) is None
    labels[3, 3] = 2                                  # the entry vestibule shares the zone: still one space
    assert clear_zone_violation(labels, specs, land, core, ("foyer", "hall"), ("entry_vestibule",)) is None
    labels[3, 2] = 3                                  # foyer + hall: split
    assert clear_zone_violation(labels, specs, land, core, ("foyer", "hall"),
                                ("entry_vestibule",)).startswith("clear:split")
    labels[:] = 1                                     # the living room receives it: not circulation
    assert clear_zone_violation(labels, specs, land, core, ("foyer", "hall"),
                                ("entry_vestibule",)) == "clear:not_circulation:living_room"
    assert clear_zone_violation(labels, specs, land, CoreSettings(), ("foyer", "hall"), ()) is None


def test_the_half_bath_never_stands_beside_the_stair():
    specs = [_Spec("hall"), _Spec("half_bath"), _Spec("stair", True), _Spec("half_bath", True)]
    labels = np.zeros((6, 6), dtype=int)
    stair = np.zeros((6, 6), dtype=bool)
    stair[1:3, 1:3] = True
    labels[stair] = 2
    labels[4:6, 4:6] = 1
    assert half_bath_beside_stair(labels, specs, stair, {"half_bath"}) is None
    labels[1:3, 3] = 3                                # the fixed half bath under the stair is fine
    assert half_bath_beside_stair(labels, specs, stair, {"half_bath"}) is None
    labels[0, 1] = 1                                  # a placed half bath against the stair
    assert half_bath_beside_stair(labels, specs, stair, {"half_bath"}) == "K13:half_bath_beside_stair"
    assert 1 in labels_touching(labels, stair)


class _Door:
    def __init__(self, a, b):
        self.a, self.b = a, b


def test_the_half_bath_under_the_stair_opens_only_to_the_foyer_or_a_hall():
    from spaceplan.modules.stacking.lib.stair_core import half_bath_opens_violation

    specs = [_Spec("foyer"), _Spec("half_bath", True), _Spec("vestibule", True), _Spec("kitchen"), _Spec("stair", True)]
    ok = [_Door(1, 2), _Door(2, 0), _Door(0, 4)]
    assert half_bath_opens_violation(ok, specs, {"half_bath"}, ("foyer", "hall"), ("stair",)) is None
    bad = ok + [_Door(3, 2)]
    assert half_bath_opens_violation(bad, specs, {"half_bath"}, ("foyer", "hall"),
                                     ("stair",)) == "K13:half_bath_opens_to:kitchen"
    relocated = [_Spec("foyer"), _Spec("half_bath"), _Spec("kitchen")]
    assert half_bath_opens_violation([_Door(1, 2)], relocated, {"half_bath"}, ("foyer",), ()) is None
