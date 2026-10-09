"""Step 4 reference cases (spaceplan v1.1 figures 2 and 3)."""

import pytest
from conftest import load_brief
from shapely.geometry import shape

from spaceplan.pipeline.main.run_capacity import run_capacity


def site(pkg):
    return pkg["site_partition"]


def option(pkg, option_id):
    return next(o for o in site(pkg)["options"] if o["option_id"] == option_id)


def check(opt, check_id):
    return next(c for c in opt["checks"] if c["check_id"] == check_id)


def variant(opt, walkway, deck):
    return next(v for v in opt["variants_evaluated"] if v["walkway_variant"] == walkway and v["deck_position"] == deck)


def test_figure2_front_yard_paving(packages):
    """50 ft lot: driveway 300 + walkway 4x9 + deck 10x6 = 396 of 750 sq ft (53%)."""
    opt = option(packages["interior_50x100"], "n1")
    assert site(packages["interior_50x100"])["front_yard_area_sqft"] == pytest.approx(750)
    assert variant(opt, "independent", "centered")["paving_fraction"] == pytest.approx(396 / 750)
    assert opt["zones"]["driveway"]["area_sqft"] == pytest.approx(300)
    assert opt["zones"]["entry_deck"]["area_sqft"] == pytest.approx(60)
    assert opt["access"]["deck_depth_ft"] == pytest.approx(6)
    assert check(opt, "front_paving_fraction")["passes"] is True
    assert check(opt, "deck_projection")["value"] <= 6 + 1e-9


def test_figure3_garden_by_floors(packages):
    pkg = packages["interior_50x100"]
    n1, n2 = option(pkg, "n1"), option(pkg, "n2")
    assert n1["coverage_ratio"] == pytest.approx(0.4424, abs=1e-3)
    # full-width footprint reproduces figure 3-A (garden ~1,615); reserving equipment room trades ~50 sq ft
    assert n1["zones"]["garden"]["area_sqft"] == pytest.approx(1616.7 if n1["footprint_variant"] == "full_width"
                                                              else 5000 - 750 - 50 * 56.72, abs=1.0)
    assert n2["zones"]["garden"]["area_sqft"] > n1["zones"]["garden"]["area_sqft"]
    assert (n1["preferences_met"], n2["preferences_met"]) == (False, True)
    assert site(pkg)["selected_option_id"] == "n2"


def test_partition_covers_the_lot_without_overlaps(packages):
    for pkg in packages.values():
        lot_area = pkg["lot_metrics"]["area_sqft"]
        for opt in site(pkg)["options"]:
            if "zones" not in opt:
                continue
            geoms = [shape(z["polygon"]) for z in opt["zones"].values() if z["polygon"]]
            assert sum(g.area for g in geoms) == pytest.approx(lot_area, abs=1.0)
            for i, a in enumerate(geoms):
                for b in geoms[i + 1:]:
                    assert a.intersection(b).area < 0.5


def test_footprint_respects_setbacks(packages):
    for pkg in packages.values():
        env = shape(pkg["capacity"]["envelope"]["polygon"]).buffer(1e-4)
        for opt in site(pkg)["options"]:
            if "zones" in opt:
                assert env.covers(shape(opt["zones"]["footprint"]["polygon"]))
                assert check(opt, "footprint_within_envelope")["passes"] is True


def test_fan_lot_fails_paving_and_proposes_corrections(packages):
    pkg = packages["fan_curve_35_80x100"]
    n1, n2 = option(pkg, "n1"), option(pkg, "n2")
    # auto selects strategy B on the fan (A uses < 80 % of the envelope); 3,000 sq ft exceed two steps by 1 sq ft
    assert "zones" not in n1 and "B_stepped_footprint holds" in n1["reasons"][0]
    paving = check(n2, "front_paving_fraction")
    assert paving["passes"] is False and paving["value"] == pytest.approx(0.625, abs=0.005)
    assert any("1-car driveway" in h for h in n2["corrections"])
    assert any("does not count as paving" in h for h in n2["corrections"])
    assert site(pkg)["selected_option_id"] is None


def test_cul_de_sac_deck_projection_uses_half_setback(packages):
    pkg = packages["fan_cul_de_sac_35_80x100"]
    assert site(pkg)["limits"]["deck_max_projection_ft"] == pytest.approx(5)
    for opt in site(pkg)["options"]:
        assert check(opt, "deck_projection")["passes"] is True


def test_corner_lot_side_facade_faces_the_street(packages):
    opt = option(packages["corner_55x100"], "n1")
    faces = {f["facade_id"]: f["faces"] for f in opt["facades"]}
    assert faces == {"front": "front_yard", "right": "street_side_yard", "rear": "garden", "left": "side_yard"}


def test_facade_azimuths_follow_north(packages):
    opt = option(packages["interior_50x100"], "n2")
    az = {f["facade_id"]: f["azimuth_deg"] for f in opt["facades"]}
    assert az == pytest.approx({"front": 180, "right": 90, "rear": 0, "left": 270})
    affinity = opt["zone_facade_affinity"]
    assert affinity["social"]["front"] > affinity["social"]["rear"]  # south sun beats the north garden side
    assert affinity["private"]["rear"] > affinity["private"]["front"]  # privacy from the street


def test_rotating_north_changes_exposure_not_geometry():
    brief = load_brief("interior_50x100")
    base = run_capacity(brief)
    brief["orientation"]["north_azimuth_deg"] = 180.0
    flipped = run_capacity(brief)
    a, b = option(base, "n2"), option(flipped, "n2")
    assert a["zones"]["garden"]["area_sqft"] == b["zones"]["garden"]["area_sqft"]
    sun = lambda o, f: next(x["sun"] for x in o["facades"] if x["facade_id"] == f)
    assert sun(a, "front") == pytest.approx(1) and sun(b, "rear") == pytest.approx(1)


def test_no_garage_means_no_driveway():
    brief = load_brief("interior_50x100")
    brief["program"]["garage_cars"] = 0
    brief["program"]["spaces"] = [s for s in brief["program"]["spaces"] if s["zone"] != "garage"]
    brief["relations"] = [r for r in brief["relations"] if "driveway" not in (r["a"], r["b"]) and "garage" not in (r["a"], r["b"])]
    brief["relation_groups"] = []
    brief["streets"][0]["curb_cut"] = None
    pkg = run_capacity(brief)
    opt = option(pkg, "n2")
    assert opt["zones"]["driveway"]["area_sqft"] == 0
    assert opt["access"]["walkway_variant"] == "independent"
    assert all(v["error"] for v in opt["variants_evaluated"] if v["walkway_variant"] == "from_driveway")


def test_deck_position_preference_is_respected():
    brief = load_brief("interior_50x100")
    brief["preferences"]["deck_position"] = "centered"
    opt = option(run_capacity(brief), "n2")
    assert {v["deck_position"] for v in opt["variants_evaluated"]} == {"centered"}


def test_footprint_reserves_equipment_room_away_from_driveway(packages):
    opt = option(packages["interior_50x100"], "n2")
    assert opt["footprint_variant"] == "equipment_room_left"  # driveway sits on the right
    room = check(opt, "side_yard_equipment_room")
    assert room["kind"] == "info" and room["passes"] is True and room["value"] == pytest.approx(3)
    assert opt["footprint_width_ft"] == pytest.approx(39)


def test_full_width_kept_when_reserving_breaks_the_fit():
    pkg = run_capacity(load_brief("fan_cul_de_sac_35_80x100"), strategy="A_inscribed_rectangle", corrections=False)
    opt = option(pkg, "n1")  # strategy A: 2,212 sq ft footprint already at full depth
    assert opt["footprint_variant"] == "full_width"
    assert check(opt, "side_yard_equipment_room")["passes"] is False
