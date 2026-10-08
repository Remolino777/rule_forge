"""Circulation network and D/I/N relation matrix (step 5, revision 2)."""

import pytest

from spaceplan.lib.catalog import load_catalog
from spaceplan.lib.circulation import DoorRules, Node, build_graph, evaluate_matrix, reachability, shared_edge, through_strips
from spaceplan.lib.relation_matrix import ENTRY, PATIO, load_matrix
from spaceplan.lib.space_layout import fit_lengths

CATALOG = load_catalog()
HOUSE = load_matrix(CATALOG, "house")


def node(nid, stype, zone, rect, passable, circulation=False, roles=None):
    return Node(nid, stype, zone, zone, rect, passable, circulation, 3.0, 0.0,
                frozenset(roles if roles is not None else HOUSE.roles_of(stype)), stype.endswith("bath"))


def rules(matrix=HOUSE, entry=(0.0, 4.0), patio=("rear",)):
    return DoorRules(3.0, matrix, frozenset({frozenset(("garage", "private"))}), frozenset({"kitchen", "service"}),
                     "circulation", entry, 3.0, (0.0, 0.0, 30.0, 30.0), patio,
                     frozenset(CATALOG.data["circulation"]["private_roles"]))


# --------------------------------------------------------------------------- matrix


def test_matrix_matches_the_client_table():
    pairs = {(p.a, p.b): (p.type, p.kind) for p in HOUSE.pairs}
    assert pairs[("access", "living")] == ("D", "hard")
    assert pairs[("access", "dining")] == ("I", "soft")
    assert pairs[("living", "kitchen")] == ("I", "soft")
    assert pairs[("bedroom", "bedroom")] == ("I", "soft")
    assert pairs[("kitchen", "laundry")] == ("D", "hard")
    assert [g.group_id for g in HOUSE.groups] == ["patio_from_dining_or_kitchen"]
    apt = {(p.a, p.b): p.type for p in load_matrix(CATALOG, "apartment").pairs}
    assert apt[("access", "kitchen")] == "I" and not any("patio" in k for k in apt)


def test_matrix_overrides():
    m = load_matrix(CATALOG, "house", [{"a": "living", "b": "kitchen", "type": "D", "kind": "hard"},
                                       {"a": "bedroom", "b": "bedroom", "type": "N"}])
    pairs = {(p.a, p.b): (p.type, p.kind) for p in m.pairs}
    assert pairs[("living", "kitchen")] == ("D", "hard") and ("bedroom", "bedroom") not in pairs
    with pytest.raises(ValueError):
        load_matrix(CATALOG, "house", [{"a": "garage_x", "b": "living", "type": "D"}])


def test_directed_ensuite():
    assert HOUSE.d_directed("primary_suite", "primary_bath") and not HOUSE.d_directed("primary_bath", "primary_suite")


# --------------------------------------------------------------------------- geometry helpers


def test_shared_edge_and_fit_lengths():
    assert shared_edge((0, 0, 10, 10), (10, 2, 20, 6))[0] == pytest.approx(4)
    assert shared_edge((0, 0, 10, 10), (11, 0, 20, 10))[0] == 0
    assert fit_lengths([13.4, 4.4, 13.4], [9, 5, 9]) == pytest.approx([13.1, 5.0, 13.1])
    assert fit_lengths([3, 3], [4, 4]) is None


# --------------------------------------------------------------------------- doors and reachability


def _plan():
    """foyer at the door, living beside it, hall behind, two bedrooms and a bath on the hall."""
    return {
        "foyer": node("foyer", "foyer", "circulation", (0, 0, 6, 10), True, True, set()),
        "living": node("living", "living_room", "social", (6, 0, 30, 10), True),
        "hall": node("hall", "hall", "circulation", (0, 10, 30, 14), True, True, set()),
        "bed1": node("bed1", "bedroom", "private", (0, 14, 12, 30), False),
        "bath": node("bath", "bathroom", "private", (12, 14, 18, 30), False),
        "bed2": node("bed2", "bedroom", "private", (18, 14, 30, 30), False),
    }


def test_private_rooms_open_only_onto_circulation():
    nodes = _plan()
    nodes["bed2"] = node("bed2", "bedroom", "private", (18, 14, 30, 30), False)
    nodes["hall"] = node("hall", "hall", "circulation", (0, 10, 18, 14), True, True, set())
    nodes["living"] = node("living", "living_room", "social", (6, 0, 30, 14), True)
    g = build_graph(nodes, rules())
    assert not g.linked("bed2", "living")      # a bedroom never opens onto the living room
    depth, _ = reachability(g)
    assert "bed2" not in depth                 # and so it is unreachable without a hall


def test_bedrooms_are_never_corridors():
    nodes = _plan()
    g = build_graph(nodes, rules())
    assert not g.linked("bed1", "bath") or ("bed1", "bath") in g.ensuite
    depth, parent = reachability(g)
    assert all(parent[n] in ("hall", "bed1", "bed2") for n in ("bed1", "bath", "bed2"))
    assert depth["foyer"] == 1 and depth["hall"] == 2


def test_matrix_evaluation_semantics():
    g = build_graph(_plan(), rules())
    results = {r["pair"]: r for r in evaluate_matrix(HOUSE, g)}
    assert results["D:access-living"]["satisfied"]            # door -> foyer -> living (foyer is circulation)
    assert results["D:bedroom-private_bath"]["satisfied"]     # both open onto the same hall
    assert results["I:bedroom-bedroom"]["satisfied"]          # separated by the hall
    assert not results["D:living-dining"]["applicable"]       # no dining in this plan
    assert results["group:patio_from_dining_or_kitchen"]["satisfied"]  # not applicable -> vacuously true


def test_open_rooms_need_a_shared_wall_for_d():
    nodes = {
        "foyer": node("foyer", "foyer", "circulation", (0, 0, 10, 10), True, True, set()),
        "living": node("living", "living_room", "social", (10, 0, 20, 10), True),
        "dining": node("dining", "dining_room", "social", (0, 10, 10, 20), True),
    }
    results = {r["pair"]: r for r in evaluate_matrix(HOUSE, build_graph(nodes, rules()))}
    assert not results["D:living-dining"]["satisfied"]        # both touch the foyer, but not each other


def test_through_strip_is_door_to_door():
    nodes = {
        "foyer": node("foyer", "foyer", "circulation", (0, 0, 4, 10), True, True, set()),
        "living": node("living", "living_room", "social", (4, 0, 24, 10), True),
        "bed": node("bed", "bedroom", "private", (24, 0, 34, 10), False),
    }
    nodes["hall"] = node("hall", "hall", "circulation", (24, 10, 34, 14), True, True, set())
    nodes["bed"] = node("bed", "bedroom", "private", (24, 14, 34, 24), False)
    nodes["living"] = node("living", "living_room", "social", (4, 0, 24, 14), True)
    g = build_graph(nodes, rules(entry=(0, 4)))
    depth, parent = reachability(g)
    strips = through_strips(g, parent, 3.5)
    # L path from the foyer-living door (4, 5) to the living-hall door (24, 12): 20 + 7 = 27 ft
    assert strips == {"living": pytest.approx(3.5 * 27)}


def test_patio_doors_on_the_rear_facade():
    nodes = {
        "foyer": node("foyer", "foyer", "circulation", (0, 0, 6, 30), True, True, set()),
        "dining": node("dining", "dining_room", "social", (6, 0, 30, 30), True),
    }
    g = build_graph(nodes, rules())
    assert g.linked("dining", PATIO) and ENTRY in g.adj
