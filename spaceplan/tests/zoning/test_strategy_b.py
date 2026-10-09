"""Step 6: strategy B (stepped / polygonal), joint articulation, CRC-aware polygonal extension,
multivariable minimal correction and its Pareto frontier."""

import pytest
from shapely.geometry import Polygon, box

from spaceplan.core.lib.catalog import load_catalog
from spaceplan.core.lib_aux.allocation import ranked_product
from spaceplan.core.lib_aux.section import SectionProfile
from spaceplan.modules.zoning.lib.corrections import (
    candidate_combos,
    garage_program,
    minimal_recess,
)
from spaceplan.modules.zoning.lib.polygonal import (
    ExtensionPolicy,
    Member,
    extend_members,
    min_corner_angle,
)
from spaceplan.modules.zoning.lib.realization import (
    FootprintDomain,
    StrategyA,
    StrategyB,
    ZoneTopology,
    carve_joint,
)
from spaceplan.modules.zoning.main.run_corrections import pareto_frontier

FAN = [(-15.65, 10), (15.65, 10), (32.975, 87), (-32.975, 87)]  # cul-de-sac fan envelope (local frame)
AREAS = {"garage": 450, "circulation": 150, "social": 440, "kitchen": 220, "private": 850, "service": 60}
TOPO = ZoneTopology(front=(("garage",), ("circulation",), ("social",)), rear=(("kitchen",), ("private",), ("service",)))


@pytest.fixture(scope="module")
def prof():
    return SectionProfile(FAN)


def test_profile_areas_match_shapely(prof):
    poly = Polygon(FAN)
    assert prof.area == pytest.approx(poly.area)
    for ya, yb, c0, c1 in ((10, 50, -5, 40), (20, 60, -100, 0), (10, 87, -20, -10)):
        assert prof.strip_area(ya, yb, c0, c1) == pytest.approx(poly.intersection(box(c0, ya, c1, yb)).area)
    x = prof.x_for_area(10, 50, 500)
    assert prof.strip_area(10, 50, c1=x) == pytest.approx(500, abs=1e-6)


def test_profile_rejects_non_horizontally_convex():
    with pytest.raises(ValueError):
        SectionProfile([(0, 0), (10, 0), (10, 10), (6, 10), (6, 4), (4, 4), (4, 10), (0, 10)])


def test_stepped_capacity_beats_rectangle(prof):
    one, _ = prof.best_steps(10, 1)
    two, rects = prof.best_steps(10, 2)
    three, _ = prof.best_steps(10, 3)
    assert two / prof.area >= 0.80 and three > two > one
    assert len(rects) == 2 and rects[1][2] - rects[1][0] > rects[0][2] - rects[0][0]  # the rear step is wider


def test_y_for_width_gives_frontage(prof):
    y = prof.y_for_width(36.0, prof.ymin)
    assert prof.width(y) == pytest.approx(36.0, abs=1e-6)
    assert minimal_recess(prof, 36.0, 0.5, 20) == pytest.approx(10.5)
    assert minimal_recess(prof, 30.0, 0.5, 20) == 0.0
    assert minimal_recess(prof, 80.0, 0.5, 20) is None


@pytest.mark.parametrize("mode", ["rectangle", "polygonal"])
def test_strategy_b_areas_exact(prof, mode):
    r = StrategyB(mode).realize(FootprintDomain((-15.65, 10, 15.65, 87), prof, 10.0), TOPO, AREAS, 3.5)
    assert r is not None and r.mode == mode
    for cell, area in AREAS.items():
        assert r.areas[cell] == pytest.approx(area, rel=1e-6)
    for cell, (x0, y0, x1, y1) in r.cells.items():  # cores lie inside the envelope
        assert Polygon(FAN).buffer(1e-6).covers(box(x0, y0, max(x1, x0 + 1e-9), y1))


def test_stepped_shoulders_and_wedges(prof):
    r = StrategyB("rectangle").realize(FootprintDomain((-15.65, 10, 15.65, 87), prof, 10.0), TOPO, AREAS, 3.5)
    shoulders = {c: f["front_shoulder"] for c, f in r.facades.items() if "front_shoulder" in f}
    assert shoulders and all(c in ("kitchen", "private", "service") for c in shoulders)
    slab = sum(prof.strip_area(s[1], s[3]) for s in r.steps)
    steps = sum((s[2] - s[0]) * (s[3] - s[1]) for s in r.steps)
    assert sum(w["area"] for w in r.wedges) == pytest.approx(slab - steps, rel=1e-6)


def test_strategy_a_unchanged_by_domain():
    fp = (0.0, 0.0, 40.0, 60.0)
    a = StrategyA().realize(fp, TOPO, AREAS)
    b = StrategyA().realize(FootprintDomain(fp), TOPO, AREAS)
    assert a.cells == b.cells


def test_width_fitting_widens_garage_within_shift(prof):
    dom = FootprintDomain((-18, 20.5, 18, 87), prof, 20.5)
    topo = ZoneTopology(front=(("social",), ("circulation",), ("garage",)), rear=(("kitchen",), ("private",), ("service",)))
    plain = StrategyB("rectangle").realize(dom, topo, AREAS)
    floor = {"social": 12.0, "circulation": 4.0, "garage": 20.0}  # the rear band keeps its proportional widths
    fitted = StrategyB("rectangle").realize(dom, topo, AREAS, 0.0, floor, 0.30)
    g0, g1 = plain.cells["garage"], fitted.cells["garage"]
    assert g0[2] - g0[0] < 20.0 <= g1[2] - g1[0] + 1e-9
    assert sum(fitted.areas[c] for c in ("social", "circulation", "garage")) == pytest.approx(
        sum(AREAS[c] for c in ("social", "circulation", "garage")))
    assert StrategyB("rectangle").realize(dom, topo, AREAS, 0.0, floor, 0.01) is None  # shift cap


def test_joint_corridor_reaches_rear_rooms():
    cells = {"social": (0, 0, 12, 30), "circulation": (12, 0, 16, 30), "garage": (16, 0, 36, 30),
             "kitchen": (-6, 30, 6, 50), "private": (6, 30, 40, 50)}
    steps = ((0, 0, 36, 30), (-6, 30, 40, 50))
    joint = carve_joint(cells, (("kitchen",), ("private",)), steps, ("right", 3.5, ("circulation",), 3.0))
    assert joint == (6, 30, 40, 33.5)
    assert cells["private"][1] == pytest.approx(33.5) and cells["kitchen"][1] == 30  # kitchen keeps its contact
    assert carve_joint(dict(cells), (("kitchen",), ("private",)), steps, ("left", 3.5, ("nowhere",), 3.0)) is None


def test_ranked_product_is_complete_and_best_first():
    order = list(ranked_product([3, 2, 2], 100))
    assert len(order) == 12 and len(set(order)) == 12
    sums = [sum(i) for i in order]
    assert sums == sorted(sums) and order[0] == (0, 0, 0)
    assert len(list(ranked_product([5, 5, 5], 7))) == 7


def test_polygonal_extension_policy():
    cell = Polygon([(0, 0), (20, 0), (20, 20), (-5, 20)])
    policy = ExtensionPolicy(frozenset({"closet"}), 2.0, 0.25, 60)
    members = {"bed": Member((0, 0, 12, 12), "bedroom"), "clo": Member((0, 12, 12, 20), "closet"),
               "bath": Member((12, 0, 20, 20), "bathroom")}
    polys, residual, log = extend_members(cell, box(0, 0, 20, 20), members, policy)
    decisions = {row["space"]: row["decision"] for row in log}
    assert decisions["bed"] == "too_thin" and decisions["clo"] == "tolerant"
    assert polys["clo"].area == pytest.approx(96 + 32)
    assert sum(r["area_sqft"] for r in residual) == pytest.approx(18)
    assert polys["bed"].area == pytest.approx(144)  # the bedroom keeps its rectangle


def test_polygonal_extension_refuses_sharp_corners():
    cell = Polygon([(0, 0), (20, 0), (20, 10), (-8, 10)])  # 6 ft wide piece with a sharp corner
    policy = ExtensionPolicy(frozenset(), 2.0, 1.0, 60)
    polys, residual, log = extend_members(cell, box(0, 0, 20, 10), {"bed": Member((0, 0, 20, 10), "bedroom")}, policy)
    assert log[0]["decision"] == "sharp_corner" and residual
    assert min_corner_angle(Polygon([(0, 0), (10, 0), (0, 10)])) == pytest.approx(45)
    assert min_corner_angle(box(0, 0, 3, 4)) == pytest.approx(90)


def test_garage_variants_and_combo_order(prof):
    cat = load_catalog()
    program = {"garage_cars": 2, "spaces": [{"space_id": "g", "zone": "garage", "space_type": "garage_2car",
                                             "min_area_sqft": 380, "target_area_sqft": 420}]}
    tandem = garage_program(cat, program, "tandem")
    assert tandem["spaces"][0]["space_type"] == "garage_2car_tandem" and program["spaces"][0]["space_type"] == "garage_2car"
    assert garage_program(cat, tandem, "tandem") is None
    assert garage_program(cat, program, "one_car")["garage_cars"] == 1
    diag = {"strict": [{"demand_by_cell": {"social": 12, "circulation": 4, "garage": 20}}],
            "relaxed": [{"demand_by_cell": {"circulation": 4, "garage": 20}}]}
    combos = candidate_combos(cat, program, prof, diag, ("A_inscribed_rectangle", "as_brief", 0.0), (5.0,))
    costs = [c.cost for c in combos]
    assert costs == sorted(costs)
    assert any(c.strategy == "B_stepped_footprint" and c.recess_ft == pytest.approx(10.5) for c in combos)
    assert all((c.strategy, c.garage, c.recess_ft) != ("A_inscribed_rectangle", "as_brief", 0.0) for c in combos)


def test_pareto_frontier_marks_dominated_rows():
    rows = [{"cost": 0.5, "score": 0.60}, {"cost": 1.0, "score": 0.70}, {"cost": 1.5, "score": 0.65},
            {"cost": 0.5, "score": 0.55}]
    out = pareto_frontier(rows)
    on = [(r["cost"], r["score"]) for r in out if r["on_frontier"]]
    assert on == [(0.5, 0.60), (1.0, 0.70)]


def test_fan_cul_de_sac_is_corrected_without_losing_the_garage(packages):
    c = packages["fan_cul_de_sac_35_80x100"]["corrections"]
    assert c["status"] == "corrected"
    combo = c["applied"]["combo"]
    assert combo["garage_layout"] == "as_brief" and combo["strategy"].startswith("B_")
    assert any(r["on_frontier"] for r in c["pareto"])
    scheme = c["applied"]["zoning_option"]["schemes"][0]
    assert scheme["realization"]["mode"] == "rectangle"


def test_reverse_fan_zones_with_strategy_b(packages):
    p = packages["fan_reverse_80_40x100"]
    assert p["zoning"]["selection"]["strategy"] == "B_stepped_footprint"
    option = p["zoning"]["options"][0]
    assert option["status"] == "zoned" and p["corrections"] is None
    assert "rear_shoulder" in option["schemes"][0]["realization"]["shoulders"]


def test_strategy_b_capacity_reported(packages):
    rows = packages["fan_cul_de_sac_35_80x100"]["realizable_capacity"]
    by = {(r["strategy"], r.get("steps")): r["utilization"]["value"] for r in rows}
    assert by[("B_stepped_footprint", 2)] > 0.8 > rows[0]["utilization"]["value"]
    assert by[("B_polygonal_footprint", None)] == pytest.approx(1.0)
