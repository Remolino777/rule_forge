"""Step V6.8 k2 (client 2026-10-17, mandatory): garage -> kitchen without crossing the living or dining room — the
garage against the service or kitchen unit and service against kitchen in S2; the garage door onto a mudroom,
kitchen, laundry or service hall (the foyer only when the route crosses nothing social); a door route garage ->
kitchen off the social rooms (hard) whose length is scored and reported."""

import numpy as np
import pytest

from spaceplan.modules.design.lib.design_registry import load_registry
from spaceplan.modules.stacking.lib.garage_route import (
    RouteSettings,
    door_route,
    door_target_ok,
    garage_route,
    plan_route,
    route_score,
    route_settings,
    route_violation,
    zone_violation,
)
from spaceplan.modules.stacking.lib.space_rules import design_view
from spaceplan.modules.stacking.lib_aux.route_graph import dijkstra, distance


@pytest.fixture(scope="module")
def rs():
    values, kinds = design_view()
    return route_settings(values, kinds)


class _Spec:
    def __init__(self, space_type, zone, passable=True, circulation=False):
        self.space_type, self.zone, self.passable, self.circulation = space_type, zone, passable, circulation


GARAGE = _Spec("garage_2car", "garage", passable=False)
FOYER = _Spec("foyer", "circulation", circulation=True)
LIVING = _Spec("living_room", "social")
KITCHEN = _Spec("kitchen", "kitchen")
MUDROOM = _Spec("mudroom", "service")
STAIR = _Spec("stair", "circulation", circulation=True)


# ------------------------------------------------------------------ registry


def test_the_registry_holds_the_route_decisions(rs):
    reg = load_registry()
    p = reg.get("circulation.garage_route.required")
    assert p.value is True and p.kind == "hard" and p.who == "client"
    assert set(reg.get("circulation.garage_route.avoid_space_types").value) == {
        "living_room", "dining_room", "living_dining", "family_room"}
    assert reg.get("circulation.garage_route.zone_opens_to").kind == "hard"
    assert rs.required and rs.service_kitchen and rs.targets == {"kitchen"}
    assert rs.zone_opens_to == {"service", "kitchen"}
    assert {"mudroom", "kitchen", "laundry", "hall"} <= rs.door_to
    assert rs.length_weight > 0 and rs.length_scale_ft > 0


def test_a_soft_route_is_not_enforced_and_an_empty_registry_is_pre_k2():
    values, kinds = design_view()
    soft = route_settings(values, {**kinds, "circulation.garage_route.required": "soft"})
    assert not soft.required and soft.service_kitchen
    assert route_settings({}) == RouteSettings()
    assert door_target_ok(RouteSettings(), "living_room")       # pre-k2: any door the catalog allows


# ------------------------------------------------------------------ S2


def test_the_garage_stands_against_service_or_kitchen(rs):
    zones = ["circulation", "kitchen", "social", "service"]
    links = {(0, 1), (0, 2), (1, 3)}
    assert zone_violation(zones, {1}, links, rs) is None
    assert zone_violation(zones, {3}, links, rs) is None
    assert zone_violation(zones, {0}, links, rs) == "doors:garage_zone"        # only the foyer: never
    assert zone_violation(zones, {0, 3}, links, rs) is None
    assert zone_violation(zones, {1}, {(0, 1), (0, 3)}, rs) == "doors:service_kitchen"
    assert zone_violation(["circulation", "kitchen"], {1}, {(0, 1)}, rs) is None   # service merged into kitchen
    assert zone_violation(zones, {0}, links, None) is None                       # pre-k2 zoning
    assert zone_violation(zones, {0}, links, RouteSettings(zone_opens_to=frozenset({"kitchen"}))) is None


# ------------------------------------------------------------------ S2.1: the garage door


def test_the_garage_door_never_opens_onto_the_social_rooms(rs):
    for t in ("mudroom", "kitchen", "laundry", "hall", "foyer"):
        assert door_target_ok(rs, t)
    for t in ("living_room", "dining_room", "living_dining", "family_room", "bedroom"):
        assert not door_target_ok(rs, t)


def test_dijkstra_and_distance():
    graph = {"a": [("b", 1.0), ("c", 5.0)], "b": [("c", 1.0)], "c": []}
    cost, path = dijkstra({"a": 0.0}, lambda x: graph[x], lambda x: x == "c")
    assert cost == 2.0 and path == ["a", "b", "c"]
    assert dijkstra({"a": 0.0}, lambda x: graph[x], lambda x: x == "z") is None
    assert distance((0, 0), (3, 4)) == 5.0 and distance(None, (1, 1)) == 0.0


def _strip_labels():
    """A row of spaces left to right: garage 0 | mudroom 1 | kitchen 2 | living 3 | foyer 4 (2 cells each)."""
    lab = np.zeros((2, 10), dtype=int)
    for k in range(5):
        lab[:, 2 * k:2 * k + 2] = k
    return lab


def test_the_planned_route_prefers_the_mudroom_and_avoids_the_living_room(rs):
    specs = [GARAGE, MUDROOM, KITCHEN, LIVING, FOYER]
    lab = _strip_labels()
    nb = {1: [2], 2: [1, 3], 3: [2, 4], 4: [3]}
    got = plan_route(specs, lab, 0, {1: (2.0, 1.0)}, lambda x: nb.get(x, []), rs, 1.0)
    assert got is not None and got[1] == [1, 2]
    got = plan_route(specs, lab, 0, {4: (8.0, 1.0)}, lambda x: nb.get(x, []), rs, 1.0)
    assert got is None                                   # from the foyer only through the living room
    nb2 = {**nb, 4: [3, 2], 2: [1, 3, 4]}                # an opening foyer -> kitchen is possible
    cost_foyer, path = plan_route(specs, lab, 0, {4: (8.0, 1.0)}, lambda x: nb2.get(x, []), rs, 1.0)
    assert path == [4, 2]
    cost_mud, path = plan_route(specs, lab, 0, {1: (2.0, 1.0), 4: (8.0, 1.0)}, lambda x: nb2.get(x, []), rs, 1.0)
    assert path == [1, 2] and cost_mud < cost_foyer


# ------------------------------------------------------------------ S2.1: the route over the placed doors


def test_the_door_route_report(rs):
    specs = [GARAGE, MUDROOM, KITCHEN, LIVING, FOYER, STAIR]
    clean = [(1, 0, (2.0, 1.0)), (1, 2, (4.0, 1.0)), (2, 3, (6.0, 1.0)), (3, 4, (8.0, 1.0)), (4, 5, (9.0, 1.0))]
    rep = garage_route(specs, clean, rs, 1.0)
    assert rep["reached"] and rep["clean"] and rep["opens_to"] == "mudroom" and rep["length_ft"] == 2.0
    assert rep["through"] == ["mudroom"]
    assert route_violation(rep, rs) is None and route_score(rep, rs) == 1.0

    dirty = [(4, 0, (8.0, 0.0)), (3, 4, (8.0, 1.0)), (2, 3, (6.0, 1.0))]   # garage -> foyer -> living -> kitchen
    rep = garage_route(specs, dirty, rs, 1.0)
    assert rep["reached"] and not rep["clean"] and rep["through"] == ["foyer", "living_room"]
    assert route_violation(rep, rs) == "route:garage_kitchen" and route_score(rep, rs) == 0.0
    assert door_route(specs, dirty, rs, 1.0) is None

    via_foyer = [(4, 0, (8.0, 0.0)), (4, 2, (5.0, 1.0)), (3, 4, (8.0, 1.0))]  # the foyer, then the kitchen: allowed
    rep = garage_route(specs, via_foyer, rs, 1.0)
    assert rep["clean"] and rep["opens_to"] == "foyer" and route_violation(rep, rs) is None

    stuck = [(1, 0, (2.0, 1.0))]
    assert garage_route(specs, stuck, rs, 1.0) == {"reached": False, "clean": False}
    assert garage_route([MUDROOM, KITCHEN], [], rs, 1.0) is None            # no garage: nothing to check


def test_the_route_length_is_scored(rs):
    near = {"reached": True, "clean": True, "length_ft": rs.length_ref_ft, "opens_to": "mudroom"}
    far = {**near, "length_ft": rs.length_ref_ft + rs.length_scale_ft}
    assert route_score(near, rs) == 1.0 and route_score(far, rs) == pytest.approx(0.5)
    assert route_score(None, rs) is None
    assert route_violation(None, rs) is None
    assert route_violation({**near, "opens_to": "living_room"}, rs).startswith("route:garage_door")
    assert route_violation({**near, "clean": False}, RouteSettings()) is None   # pre-k2: reported only


# ------------------------------------------------------------------ S2: passable pairs met only by a link


def test_dining_and_kitchen_are_direct_pairs_linked_in_s2():
    from spaceplan.core.lib.catalog import load_catalog
    from spaceplan.modules.stacking.lib.garage_route import direct_pairs, direct_violation
    from spaceplan.modules.stacking.lib.stacking_catalog import load_stacking_catalog
    from spaceplan.modules.stacking.lib.stair_access import load_client_ruleset, relations
    from spaceplan.modules.stacking.lib.zone_relations import build_matrix

    scat, cat = load_stacking_catalog(), load_catalog()
    m = build_matrix(cat, relations(load_client_ruleset()), scat.s2["pair_default_weights"])
    pairs = direct_pairs(m, cat)
    ids = {p.pair_id for p in pairs}
    assert "D:dining-kitchen" in ids and "D:kitchen-laundry" not in ids     # the laundry is not passable
    assert all(not p.anchored for p in pairs)
    dk = next(p for p in pairs if p.pair_id == "D:dining-kitchen")
    located = {dk.a: frozenset({1}), dk.b: frozenset({2})}
    assert direct_violation([dk], located, {(0, 1), (0, 2)}) == "matrix:direct:D:dining-kitchen"   # via the foyer
    assert direct_violation([dk], located, {(0, 1), (1, 2)}) is None
    assert direct_violation([dk], {dk.a: frozenset({1}), dk.b: frozenset({1})}, set()) is None    # one zone
    assert direct_violation([dk], {dk.a: frozenset({1})}, set()) is None                          # one role only
