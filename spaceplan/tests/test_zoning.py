"""Layer 1c zoning (revised): houses and apartments, dwelling profiles, zone parts by spaces."""

import pytest

from conftest import load_brief
from spaceplan.lib.catalog import load_catalog
from spaceplan.lib.realization import ZoneTopology
from spaceplan.lib.zoning import (
    _compositions,
    _set_partitions,
    cell_model,
    constraints_from_brief,
    enumerate_topologies,
    load_profile,
    split_options,
)
from spaceplan.main.run_capacity import run_capacity

CATALOG = load_catalog()


def zoning_option(pkg, option_id):
    return next(o for o in pkg["zoning"]["options"] if o["option_id"] == option_id)


def cells_by_zone(scheme):
    out = {}
    for cid, cell in scheme["cells"].items():
        out.setdefault(cell["zone"], []).append((cid, cell))
    return out


# --------------------------------------------------------------------------- enumeration


def test_enumeration_is_exhaustive():
    # 1 zone per column: sum_k C(3,k) k! (3-k)! = 24; 2 per column: 6 * sum Fib(k+1) Fib(4-k) = 60
    assert sum(1 for _ in enumerate_topologies(["a", "b", "c"])) == 24
    assert sum(1 for _ in enumerate_topologies(["a", "b", "c"], 2)) == 60
    assert list(_compositions(3, 2)) == [(1, 1, 1), (1, 2), (2, 1)]
    assert len(list(_set_partitions(["a", "b", "c"], 2))) == 4


def test_column_pruning_matches_brute_force():
    """The column filter must remove exactly the topologies a full realization would reject by size."""
    from spaceplan.lib.realization import StrategyA
    from spaceplan.lib.zoning import BandGeometry, _column_ok

    areas = {"a": 300.0, "b": 60.0, "c": 400.0, "d": 240.0}
    mins = {"a": 12.0, "b": 5.0, "c": 10.0, "d": 8.0}
    fp = (0.0, 0.0, 25.0, 40.0)
    total = sum(areas.values())

    def column_check(col, band):
        area = sum(areas[c] for c in band)
        return _column_ok(col, areas, mins, BandGeometry(25.0, 40.0 * area / total, area), set(), 0.0)

    def fits(t: ZoneTopology):
        r = StrategyA().realize(fp, t, areas)
        return all(x1 - x0 >= mins[c] - 1e-9 and y1 - y0 >= mins[c] - 1e-9 for c, (x0, y0, x1, y1) in r.cells.items())

    brute = {t.key for t in enumerate_topologies(list(areas), 2) if fits(t)}
    pruned = {t.key for t in enumerate_topologies(list(areas), 2, column_check=column_check)}
    assert brute == pruned and brute


# --------------------------------------------------------------------------- cells and profiles


def test_zone_parts_follow_spaces_and_satellites_follow_hosts():
    brief = load_brief("apt_2br_interior")
    split = cell_model(CATALOG, brief["program"], 1440, {"private": "wet_core"})
    assert set(split.areas) == {"social", "kitchen", "private_suiteroom", "private_bedroomwing", "private_wetcore",
                                "circulation"}
    assert "service" not in split.areas            # the laundry closet is a satellite (its host hall is derived)
    assert "hall" in split.derived                 # halls are produced by the circulation network
    assert sum(split.areas.values()) == pytest.approx(1440)
    assert split.min_width["private_wetcore"] == 5


def test_split_options_respect_dwelling_type():
    house = split_options(CATALOG, load_brief("interior_50x100")["program"], "house")
    apt = split_options(CATALOG, load_brief("apt_2br_interior")["program"], "apartment")
    assert {"private": "wet_core"} not in house and {"private": "by_bedroom", "social": "living_dining"} in house
    assert {"private": "wet_core"} in apt


def test_merge_options_put_small_service_in_kitchen_or_garage():
    from spaceplan.lib.zoning import merge_options

    assert merge_options(CATALOG, load_brief("interior_50x100")["program"]) == [{}, {"service": "kitchen"},
                                                                                 {"service": "garage"}]


def test_brief_overrides_change_anchor_kind():
    p = load_profile(CATALOG, "house", {"living_faces_main_street": "soft"})
    assert {a.anchor_id: a.kind for a in p.anchors}["living_faces_main_street"] == "soft"
    p = load_profile(CATALOG, "apartment", {"kitchen_via_foyer": "off"})
    assert p.entry_sequence is None
    with pytest.raises(ValueError):
        load_profile(CATALOG, "house", {"no_such_anchor": "off"})


def test_constraints_come_from_the_brief_and_follow_merges():
    brief = load_brief("interior_50x100")
    zones = {"social", "private", "kitchen", "circulation", "garage"}
    c = constraints_from_brief(brief, zones, {"service": "garage"})
    assert ("garage", "driveway", "r05") in c.facade_required
    assert ("garage", "garage") in c.groups[0]["members"]       # laundry inside the garage = mudroom link
    assert "r13" in c.skipped                                   # forbidden service-social checked per space
    assert ("social", "garden", 1.0, "r06") in c.facade_desired # superseded by the D/I/N matrix


def test_front_precheck_matches_realization(packages):
    """The cheap x-range test never rejects what the full realization accepts."""
    from spaceplan.lib.zoning import first_violation, front_precheck, make_contexts, house_facade_roles

    from spaceplan.lib.realization import StrategyA

    pkg = packages["interior_50x100"]
    opt = pkg["site_partition"]["options"][0]
    c = opt["footprint_candidates"][0]
    a = c["access_options"][0]
    cand = {**c, "intervals": {"entry_deck": a["deck_interval_ft"], "driveway": a["driveway_interval_ft"]}}
    ctx = make_contexts(CATALOG, load_brief("interior_50x100"), opt["footprint_area_sqft"], [cand],
                        house_facade_roles(opt), opt["zone_facade_affinity"])[0]
    for i, t in enumerate(enumerate_topologies(list(ctx.areas), 2)):
        if i > 4000:
            break
        if front_precheck(ctx, t) is not None:
            r = StrategyA().realize(ctx.footprint, t, ctx.areas)
            v = first_violation(ctx, r)
            assert v is not None and v.split(":")[0] in ("profile", "facade", "width", "depth")


# --------------------------------------------------------------------------- houses


@pytest.mark.parametrize("name", ["interior_50x100", "corner_55x100"])
def test_house_schemes_meet_every_hard_rule(packages, name):
    pkg = packages[name]
    opt = zoning_option(pkg, "n1")
    assert opt["status"] == "zoned" and opt["profile"] == "house"
    for scheme in opt["schemes"]:
        spaces = scheme["spaces"]
        living = [s for s in spaces.values() if s["space_type"] in ("living_room", "living_dining")]
        assert living and all(s["rect_local"][1] == pytest.approx(scheme["footprint_local"][1]) for s in living)
        garage = next(s for s in spaces.values() if s["zone"] == "garage")
        assert garage["rect_local"][3] - garage["rect_local"][1] >= 19 - 1e-6
        assert all(a["satisfied"] for a in scheme["anchors"] if a["kind"] == "hard")
        assert all(m["satisfied"] for m in scheme["matrix"] if m["kind"] == "hard" and m["applicable"])
        assert all(s["depth_from_entry"] is not None for s in spaces.values())


def test_sala_to_the_street_does_not_fit_a_narrow_fan_lot():
    pkg = run_capacity(load_brief("fan_cul_de_sac_35_80x100"), strategy="A_inscribed_rectangle", corrections=False)
    opt = zoning_option(pkg, "n1")
    assert opt["status"] == "no_valid_scheme" and opt["schemes"] == []
    assert opt["diagnostics"]


def test_fan_cul_de_sac_baseline_b_needs_a_correction(packages):
    pkg = packages["fan_cul_de_sac_35_80x100"]  # auto -> strategy B; the deck sits in the front yard at recess 0
    assert zoning_option(pkg, "n1")["status"] == "not_feasible"
    assert pkg["corrections"]["status"] == "corrected"


def test_soft_override_is_recorded():
    brief = load_brief("fan_cul_de_sac_35_80x100")
    brief["zoning_overrides"] = {"anchors": {"living_faces_main_street": "soft"}}
    opt = zoning_option(run_capacity(brief, strategy="A_inscribed_rectangle", corrections=False), "n1")
    assert "living_faces_main_street:soft" in opt["constraints"]["profile_anchors"]


def test_multi_floor_is_deferred(packages):
    assert zoning_option(packages["interior_50x100"], "n2")["status"] == "deferred_to_stacking"


# --------------------------------------------------------------------------- apartments


@pytest.mark.parametrize("name", ["apt_2br_interior", "apt_2br_corner"])
def test_apartment_kitchen_is_reached_through_the_foyer(apartments, name):
    pkg = apartments[name]
    opt = zoning_option(pkg, "unit")
    assert opt["status"] == "zoned" and opt["profile"] == "apartment"
    entrance = pkg["unit"]["entrance_interval_ft"]
    for scheme in opt["schemes"]:
        spaces = scheme["spaces"]
        kitchen = next(s for s in spaces.values() if s["space_type"] == "kitchen")
        foyer = next(s for s in spaces.values() if s["space_type"] == "foyer")
        on_door = abs(kitchen["rect_local"][1]) < 1e-6 and \
            min(kitchen["rect_local"][2], entrance[1]) - max(kitchen["rect_local"][0], entrance[0]) > 1e-6
        assert not on_door
        assert min(foyer["rect_local"][2], entrance[1]) - max(foyer["rect_local"][0], entrance[0]) >= 3 - 1e-6
        assert foyer["depth_from_entry"] == 1 and kitchen["depth_from_entry"] == 2
        assert scheme["entry_sequence"]["satisfied"] is True


@pytest.mark.parametrize("name", ["apt_2br_interior", "apt_2br_corner"])
def test_apartment_living_and_bedrooms_get_exterior_light(apartments, name):
    pkg = apartments[name]
    roles = pkg["unit"]["facade_roles"]
    exterior = {f for f, r in roles.items() if "exterior" in r}
    for scheme in zoning_option(pkg, "unit")["schemes"]:
        for cid, cell in scheme["cells"].items():
            if {"living_dining", "living_room", "primary_suite", "bedroom"} & set(cell["spaces"]):
                assert any(cell["facades"].get(f, 0) >= 4 - 1e-6 for f in exterior), cid


def test_interior_apartment_uses_a_wet_core(apartments):
    best = zoning_option(apartments["apt_2br_interior"], "unit")["schemes"][0]
    assert "private_wetcore" in best["cells"] and "front" in best["cells"]["private_wetcore"]["facades"]


def test_apartment_package_has_unit_and_no_capacity(apartments):
    pkg = apartments["apt_2br_interior"]
    assert pkg["meta"]["dwelling_type"] == "apartment"
    assert pkg["capacity"] is None and pkg["site_partition"] is None
    assert pkg["scope"]["in_scope"] is False


@pytest.mark.parametrize("position", [0.3, 0.7])
def test_kitchen_never_on_the_entrance_wherever_the_door_is(position):
    brief = load_brief("apt_2br_interior")
    brief["unit"]["entrance"]["position"] = position
    opt = zoning_option(run_capacity(brief), "unit")
    for scheme in opt["schemes"]:
        assert scheme["entry_sequence"]["satisfied"]
