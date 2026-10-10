"""Stage S1.1 of the stacking module (step 6.7a): stair configurations and directions, space under the stair,
arrival zones and receiving spaces at both ends, the stair core for S2 and the rule traces (normative vs client)."""

import json

import pytest
from conftest import load_fixture
from shapely.geometry import box, shape

from spaceplan.core.lib.catalog import load_catalog
from spaceplan.modules.stacking.lib.plan_levels import COMPACT, upper_floor
from spaceplan.modules.stacking.lib.stacking_catalog import load_stacking_catalog
from spaceplan.modules.stacking.lib.stair import candidates, choose, stair_shape, under_stair
from spaceplan.modules.stacking.lib.stair_access import (
    CLIENT,
    FAIL,
    NORMATIVE,
    PASS,
    bottom_receiving,
    check_receiving,
    load_client_ruleset,
    space_type_of,
    top_receiving,
    under_stair_use,
    upper_rooms,
    uses_by_bottom_option,
)
from spaceplan.modules.stacking.lib.stair_rules import (
    fixture_headroom_ft,
    flight_rise_max_ft,
    half_bath_width_min_ft,
    load_stair_ruleset,
    stair_limits,
)
from spaceplan.modules.stacking.lib_aux.plan_geometry import joint_lines
from spaceplan.modules.stacking.lib_aux.stair_geometry import (
    KEEP_BOX,
    SWAP_BOX,
    band_area,
    place,
    transforms_for,
    zone_beyond,
)
from spaceplan.modules.stacking.main.contract import from_contract, to_contract
from spaceplan.modules.stacking.main.run_stacking import run_stacking

SUBJECT = "interior_50x100_empty_nest_anglo"


@pytest.fixture(scope="module")
def scat():
    return load_stacking_catalog()


@pytest.fixture(scope="module")
def srs():
    return load_stair_ruleset()


@pytest.fixture(scope="module")
def client():
    return load_client_ruleset()


@pytest.fixture(scope="module")
def shapes(scat, srs):
    return {t["stair_id"]: stair_shape(t, 10.0, stair_limits(srs), scat.stair_design) for t in scat.stair_types}


@pytest.fixture(scope="module")
def s1():
    am, lc = load_fixture("area_matrix", SUBJECT), load_fixture("lot_capacity", "interior_50x100")
    return run_stacking(am, [lc], mode="all", stage="S1")


def _cfg(scat, srs, receiving="hall"):
    from spaceplan.modules.stacking.lib.cell_geometry import S1Context, _stair_cfg

    ctx = S1Context(scat, stair_limits(srs), srs, None, load_client_ruleset(), load_catalog(), None, None, 60.0)
    return _stair_cfg(ctx, receiving)


# ------------------------------------------------------------------ rules


def test_new_crc_rules_and_client_rules_are_separate(srs, client):
    assert flight_rise_max_ft(srs) == pytest.approx(151 / 12) and fixture_headroom_ft(srs) == pytest.approx(80 / 12)
    assert half_bath_width_min_ft(srs) == pytest.approx(2.5)
    assert srs.status("S07-STAIR-FLIGHT-RISE") == "provisional" and client.status("K01-STAIR-TOP-ARRIVAL") == "verified"
    assert all(r["kind"] == CLIENT for r in client.data["rules"])
    assert not any("kind" in r for r in srs.data["rules"])


# ------------------------------------------------------------------ geometry under the stair


def test_clear_height_bands_and_net_cost(shapes, srs):
    hb_ft = fixture_headroom_ft(srs)
    st = shapes["straight"]
    u = under_stair(st.geometry, 4.0, hb_ft)
    assert u["footprint_sqft"] == pytest.approx(37.5)
    assert u["low_sqft"] + u["storage_sqft"] + u["half_bath_band_sqft"] == pytest.approx(37.5)
    # clear height 0.75 s - 0.208: 4 ft at s = 5.61 ft, 6'8" at s = 9.17 ft (3 ft wide)
    assert u["low_sqft"] == pytest.approx(3 * (4.0 + 0.8333 - 0.625) / 0.75, abs=0.05)
    assert u["half_bath_band_sqft"] == pytest.approx(3 * (12.5 - (hb_ft + 0.8333 - 0.625) / 0.75), abs=0.05)
    nets = {sid: under_stair(sh.geometry, 4.0, hb_ft) for sid, sh in shapes.items()}
    net = {sid: n["footprint_sqft"] - n["recovered_sqft"] for sid, n in nets.items()}
    assert max(net.values()) - min(net.values()) < 1e-6  # the low wedge of the first flight is the same in all
    assert nets["u_turn"]["recovered_sqft"] > nets["straight"]["recovered_sqft"]


def test_symmetries_keep_heights_and_ends(shapes):
    st = shapes["straight"]
    size = (st.length_ft, st.span_ft)
    assert len(transforms_for(size, (0, 0, 12.5, 3))) == 4 and len(transforms_for(size, (0, 0, 3, 12.5))) == 4
    for m in KEEP_BOX + SWAP_BOX:
        target = (10, 20, 22.5, 23) if m in KEEP_BOX else (10, 20, 13, 32.5)
        g = place(st.geometry, size, m, target)
        assert g.footprint.bounds == pytest.approx(target)
        assert band_area(g, 4.0) == pytest.approx(band_area(st.geometry, 4.0))
        assert g.bottom.line.distance(g.top.line) == pytest.approx(12.5)
        bz = zone_beyond(g.bottom, 3.0, 3.0)
        assert bz.intersection(g.footprint).area == pytest.approx(0.0) and bz.distance(g.footprint) == 0.0


def test_u_turn_ends_on_the_same_side(shapes):
    g = shapes["u_turn"].geometry
    assert g.bottom.outward == g.top.outward and g.bottom.line.distance(g.top.line) == pytest.approx(0.0)


def test_arrival_zone_aligned_when_wider_than_the_stair(shapes):
    g = shapes["straight"].geometry
    centred, start, end = (zone_beyond(g.top, 3.0, 3.5, a) for a in ("centre", "start", "end"))
    assert centred.bounds[1] == pytest.approx(-0.25) and start.bounds[1] == pytest.approx(0.0)
    assert end.bounds[3] == pytest.approx(3.0)


# ------------------------------------------------------------------ choice at the joint


def test_candidates_compare_all_configurations(scat, srs, shapes):
    ground, upper, garage = box(0, 0, 40, 36), box(0, 18, 40, 36), box(28, 0, 40, 24)
    cfg = _cfg(scat, srs)
    cands = candidates(list(shapes.values()), joint_lines(upper, ground), upper, ground, garage, cfg)
    assert {c.shape.stair_id for c in cands} == set(shapes)
    best = choose(cands)
    assert best.half_bath is not None
    for c in cands:
        fp = c.geom.footprint
        assert fp.difference(upper).area < 1e-6 and fp.intersection(garage).area < 1e-6
        assert c.bottom_zone.difference(ground).area < 1e-6 and c.bottom_zone.intersection(garage).area < 1e-6
        assert c.top_zone.difference(upper).area < 1e-6 and c.top_zone.intersection(fp).area < 1e-6
    assert best.key == min(c.key for c in cands)


def test_positions_skip_the_garage_before_the_cap(scat, srs, shapes):
    # the middle of the joint lies over the garage: positions must still be found beside it
    ground, upper, garage = box(0, 0, 37, 43), box(0, 17, 37, 43), box(17, 0, 37, 24)
    cfg = {**_cfg(scat, srs), "max_positions": 2}
    assert choose(candidates(list(shapes.values()), joint_lines(upper, ground), upper, ground, garage, cfg))


def test_compact_upper_floor_for_small_upper_floors(scat):
    ground = box(0, 0, 62, 25)
    rear = upper_floor("rear", ground, 200.0, None, "right", scat.geometry)
    assert rear.polygon.bounds[3] - rear.polygon.bounds[1] < 4.0  # a 62 x 3 ft strip
    compact = upper_floor(COMPACT, ground, 200.0, None, "right", scat.geometry, 12.0)
    _, y0, _, y1 = compact.polygon.bounds
    assert compact.polygon.area == pytest.approx(200.0) and y1 - y0 >= 12.0 and y1 == pytest.approx(25.0)


# ------------------------------------------------------------------ receiving spaces and client rules


def test_small_house_arrives_into_a_vestibule(client):
    catalog, acc = load_catalog(), load_stacking_catalog().stair_access
    assert space_type_of("bedroom_teen_1", [t["space_type"] for t in catalog.data["space_types"]]) == "bedroom"
    two = upper_rooms(["bedroom_primary", "primary_bath", "closet", "walk_in_closet_primary", "flex_room_guest"],
                      catalog, acc)
    four = upper_rooms(["bedroom_primary", "bedroom_child_1", "bedroom_child_2", "study_work", "bathroom"],
                       catalog, acc)
    assert (two, four) == (2, 4)
    assert top_receiving(client, two, 2)["receiving"] == "upper_vestibule"
    top = top_receiving(client, four, 2)
    assert top["receiving"] == "hall" and top["max"] == "family_room" and "bedroom" in top["forbidden"]


def test_ruleforge_case_code_passes_client_rule_fails(client, s1):
    """The CRC traces of a drawn cell pass, yet a top end landing in a bedroom breaks client rule K01."""
    cell = next(c for c in s1["cells"] if c.get("s1"))
    normative = [t for t in cell["s1"]["rule_traces"] if t["kind"] == NORMATIVE]
    assert normative and all(t["result"] == PASS for t in normative)
    bad = check_receiving(client, "top", "bedroom")
    assert bad["kind"] == CLIENT and bad["result"] == FAIL and bad["rule_id"] == "K01-STAIR-TOP-ARRIVAL"
    assert check_receiving(client, "top", "family_room")["result"] == PASS
    assert check_receiving(client, "bottom", "kitchen")["result"] == PASS  # third option, always available
    assert check_receiving(client, "bottom", "garage_2car")["result"] == FAIL


def test_under_stair_toward_the_kitchen_is_storage(client):
    assert under_stair_use(client, "kitchen", True)["use"] == "storage"
    assert under_stair_use(client, "hall", True)["use"] == "half_bath"
    assert under_stair_use(client, None, False)["use"] == "storage"
    living = under_stair_use(client, "living_room", True)
    assert living["use"] == "half_bath" and "vestibule" in living["trace"]["detail"]
    bottom = bottom_receiving(client, ["A", "B", "C"], "A")
    assert uses_by_bottom_option(client, bottom, "bottom", True) == {"A": "half_bath", "B": "half_bath",
                                                                      "C": "storage"}
    assert set(uses_by_bottom_option(client, bottom, "apart", True).values()) == {"half_bath"}


# ------------------------------------------------------------------ stair core through the contract


def test_stair_core_in_the_contract(s1):
    cells = [c for c in s1["cells"] if c.get("s1")]
    assert cells and all(c["s1"]["status"] == "drawn" for c in cells)
    for c in cells:
        core = c["s1"]["stair_core"]
        assert core["fixed"] and core["stair_id"] == c["s1"]["stair"]["stair_id"]
        fp = shape(core["footprint"])
        assert shape(core["bottom_end"]["zone"]).intersection(fp).area < 1e-3
        assert shape(core["top_end"]["zone"]).intersection(fp).area < 1e-3
        assert core["top_end"]["receiving"]["receiving"] in ("hall", "upper_vestibule")
        assert core["bottom_end"]["receiving"]["options"][-1]["option"] == "C"
        us = core["under_stair"]
        assert us["net_ground_sqft"] == pytest.approx(us["footprint_sqft"] - us["recovered_sqft"]
                                                      if "footprint_sqft" in us else us["net_ground_sqft"])
        if us["half_bath_fit"]:
            assert shape(us["half_bath"]).area >= 18.0 - 1e-3 and us["vestibule"] is not None
        assert {"normative", "client"} <= {t["kind"] for t in c["s1"]["rule_traces"]}
        assert set(core["alternatives"]) >= {core["stair_id"]}
    back = from_contract(to_contract(s1))
    assert back["cells"][0].keys() == s1["cells"][0].keys()
    assert json.dumps(back["meta"]["client_ruleset"]) == '"client-stair-rules"'
