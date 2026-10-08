import pytest

from spaceplan.lib.realization import STRATEGIES, StrategyA, ZoneTopology, get_strategy

FP = (0.0, 15.0, 40.0, 65.0)  # 40 x 50 = 2,000 sq ft
AREAS = {"a": 600.0, "b": 400.0, "c": 300.0, "d": 700.0}


def test_areas_are_exact_and_cells_tile_the_footprint():
    topo = ZoneTopology(front=(("a",), ("b", "c")), rear=(("d",),))
    r = StrategyA().realize(FP, topo, AREAS)
    for zone, area in AREAS.items():
        x0, y0, x1, y1 = r.cells[zone]
        assert (x1 - x0) * (y1 - y0) == pytest.approx(area)
    assert sum((x1 - x0) * (y1 - y0) for x0, y0, x1, y1 in r.cells.values()) == pytest.approx(2000)
    assert r.front_depth == pytest.approx(32.5)  # 1,300 of 2,000 sq ft in front


def test_contacts_and_facades():
    topo = ZoneTopology(front=(("a",), ("b", "c")), rear=(("d",),))
    r = StrategyA().realize(FP, topo, AREAS)
    assert r.contact("b", "c") == pytest.approx(r.cells["b"][2] - r.cells["b"][0])
    assert r.contact("a", "b") > 0 and r.contact("a", "d") > 0
    assert set(r.facade_contacts("a")) == {"front", "left"}
    assert set(r.facade_contacts("c")) == {"right"}  # stacked behind b: no front contact
    assert set(r.facade_contacts("d")) == {"rear", "left", "right"}


def test_single_band_uses_full_depth():
    r = StrategyA().realize(FP, ZoneTopology(front=(("a",), ("b",)), rear=()), {"a": 1000, "b": 1000})
    assert r.cells["a"] == pytest.approx((0, 15, 20, 65))


def test_registry_and_interface():
    assert get_strategy("A_inscribed_rectangle") is STRATEGIES["A_inscribed_rectangle"]
    with pytest.raises(KeyError):
        get_strategy("Z_unknown")


def test_topology_key_is_readable():
    assert ZoneTopology((("garage",), ("circulation", "service")), (("social",),)).key == \
        "F:garage|circulation+service/R:social"
