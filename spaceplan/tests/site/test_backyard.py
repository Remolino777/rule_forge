"""Backyard program: priority filter, green reserve, clearances (layer 1d)."""

import pytest
from conftest import load_brief
from shapely.geometry import LineString, box, shape

from spaceplan.core.lib.catalog import load_catalog
from spaceplan.core.lib.rules import load_ruleset
from spaceplan.core.lib_aux.geometry import Frame
from spaceplan.modules.site.lib.backyard import (
    YardContext,
    plan_backyard,
    priority_filter,
    rect_dims,
    requests_from_brief,
)
from spaceplan.pipeline.main.run_capacity import run_capacity

CATALOG = load_catalog()
RS = load_ruleset()
GROUPS = CATALOG.data["backyard_policy"]["groups"]
SQFT_PER_M2 = 10.7639


def program(*elements, green=None):
    return {"min_green_fraction": green,
            "elements": [{"element": e, "priority": i + 1} for i, e in enumerate(elements)]}


def status(result):
    return {r["element"]: r["status"] for r in result["elements"]}


def test_twenty_square_meter_patio_keeps_spa_and_small_deck():
    """User example: 20 m2 with 30 % green -> a pool does not fit, a spa and a small deck do."""
    yard = 20 * SQFT_PER_M2
    reqs = requests_from_brief(CATALOG, program("pool", "spa", "rear_deck", "shed"))
    result = priority_filter(reqs, yard, 0.30, GROUPS)
    assert status(result) == {"pool": "excluded", "spa": "placed", "rear_deck": "placed", "shed": "excluded"}
    pool = next(r for r in result["elements"] if r["element"] == "pool")
    assert pool["reason"].startswith("area: needs 200")
    deck = next(r for r in result["elements"] if r["element"] == "rear_deck")
    assert 80 <= deck["area_sqft"] < 150                       # shrunk toward its minimum
    assert result["used_sqft"] <= yard * 0.70 + 1e-6           # green reserve untouched


def test_priority_order_decides_who_enters():
    yard = 20 * SQFT_PER_M2
    result = priority_filter(requests_from_brief(CATALOG, program("shed", "rear_deck", "spa")), yard, 0.30, GROUPS)
    assert status(result) == {"shed": "placed", "rear_deck": "placed", "spa": "excluded"}


def test_water_group_and_dependencies():
    result = priority_filter(requests_from_brief(CATALOG, program("bbq", "pool", "spa")), 5000, 0.30, GROUPS)
    rows = {r["element"]: r for r in result["elements"]}
    assert rows["bbq"]["status"] == "excluded" and "requires rear_deck" in rows["bbq"]["reason"]
    assert rows["pool"]["status"] == "placed"
    assert rows["spa"]["status"] == "excluded" and "group 'water'" in rows["spa"]["reason"]


def test_green_elements_do_not_consume_the_budget():
    result = priority_filter(requests_from_brief(CATALOG, program("garden_beds", "rear_deck")), 200, 0.30, GROUPS)
    assert status(result) == {"garden_beds": "placed", "rear_deck": "placed"}
    assert result["used_sqft"] == pytest.approx(min(150, 200 * 0.7))


def test_default_priority_comes_from_the_catalog():
    reqs = requests_from_brief(CATALOG, {"min_green_fraction": None,
                                         "elements": [{"element": "shed"}, {"element": "rear_deck"}]})
    assert [r.element for r in reqs] == ["rear_deck", "shed"]


def test_rect_dims_respect_minimum_dimension():
    assert rect_dims(300, 2.0, 10) == pytest.approx((12.247, 24.495), abs=1e-3)
    short, long = rect_dims(40, 4.0, 3)
    assert short == pytest.approx(3.162, abs=1e-3) and short * long == pytest.approx(40)


def test_clearances_can_exclude_what_the_area_allows():
    """A 30 x 9 ft strip has area for a spa but not room for its 3 ft lot-line clearance; the 8 ft deck fits."""
    yard = box(0, 50, 30, 59)
    lines = [LineString([(0, 59), (30, 59)]), LineString([(0, 50), (0, 59)]), LineString([(30, 50), (30, 59)])]
    ctx = YardContext(yard=yard, footprint=(5.0, 20.0, 25.0, 50.0), lot_lines=lines, deck_anchor_x=15.0, step=0.5)
    result = plan_backyard(CATALOG, RS, program("spa", "rear_deck"), ctx, Frame((0.0, 0.0), 0.0))
    rows = {r["element"]: r for r in result["elements"]}
    assert rows["spa"]["status"] == "excluded" and rows["spa"]["reason"].startswith("geometry")
    assert rows["rear_deck"]["status"] == "placed"


def test_reference_backyard_respects_every_clearance(packages):
    site = packages["interior_50x100"]["site_partition"]
    lot = box(0, 0, 50, 100)
    lines = [LineString([(0, 0), (0, 100)]), LineString([(50, 0), (50, 100)]), LineString([(0, 100), (50, 100)])]
    for option in site["options"]:
        by = option["backyard"]
        rows = {r["element"]: r for r in by["elements"]}
        assert {k for k, r in rows.items() if r["status"] == "placed"} == {"rear_deck", "pool", "bbq", "shed", "garden_beds"}
        assert rows["spa"]["reason"].startswith("group 'water'")
        geoms = {k: shape(r["polygon"]) for k, r in rows.items() if r["polygon"]}
        yard = shape(by["yard_polygon"])
        for g in geoms.values():
            assert yard.buffer(1e-6).covers(g) and lot.covers(g)
        fp_back = yard.bounds[1]
        assert geoms["rear_deck"].bounds[1] == pytest.approx(fp_back)            # attached to the house
        assert geoms["bbq"].distance(geoms["rear_deck"]) < 1e-6                   # touches the deck
        for k in ("pool", "shed"):
            gap = rows[k]["clearances"]["lot_line"]["ft"]
            assert min(ln.distance(geoms[k]) for ln in lines) >= gap - 1e-6
            assert geoms[k].bounds[1] - fp_back >= rows[k]["clearances"]["dwelling"]["ft"] - 1e-6
        names = list(geoms)
        for i, a in enumerate(names):
            for b in names[i + 1:]:
                assert geoms[a].intersection(geoms[b]).area < 1e-6
        assert by["green_fraction"] >= by["min_green_fraction"]
        assert by["status"] == "provisional"                                       # placeholder pool/shed rules
        assert any(c["check_id"] == "pool_safety_barrier" for c in by["checks"])


def test_deck_opens_from_the_dining_side(packages):
    pkg = packages["interior_50x100"]
    scheme = next(o for o in pkg["zoning"]["options"] if o["option_id"] == "n1")["schemes"][0]
    dining = next(c for c in scheme["cells"].values() if "dining_room" in c["spaces"])
    deck = shape(next(r for r in next(o for o in pkg["site_partition"]["options"] if o["option_id"] == "n1")
                      ["backyard"]["elements"] if r["element"] == "rear_deck")["polygon"])
    assert min(deck.bounds[2], dining["rect_local"][2]) - max(deck.bounds[0], dining["rect_local"][0]) > 3


def test_brief_green_override_shrinks_the_program():
    brief = load_brief("interior_50x100")
    brief["backyard_program"]["min_green_fraction"] = 0.9
    by = next(o for o in run_capacity(brief)["site_partition"]["options"] if o["option_id"] == "n1")["backyard"]
    assert by["min_green_fraction"] == 0.9 and by["green_fraction"] >= 0.9 - 1e-9
    assert any(r["status"] == "excluded" and r["reason"].startswith("area") for r in by["elements"])


def test_no_backyard_program_means_no_backyard(packages):
    assert all("backyard" not in o for o in packages["corner_55x100"]["site_partition"]["options"])


def test_deck_needs_its_minimum_depth():
    yard = box(0, 50, 30, 57)
    ctx = YardContext(yard=yard, footprint=(5.0, 20.0, 25.0, 50.0), lot_lines=[], deck_anchor_x=15.0, step=0.5)
    result = plan_backyard(CATALOG, RS, program("rear_deck"), ctx, Frame((0.0, 0.0), 0.0))
    assert result["elements"][0]["status"] == "excluded" and "8.0 ft" in result["elements"][0]["reason"]
