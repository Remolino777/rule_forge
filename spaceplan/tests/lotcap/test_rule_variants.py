import pytest

from spaceplan.modules.lotcap.lib import rule_variants as rv


@pytest.mark.parametrize(
    "depth, expected, variant",
    [
        (95, 9.5, "shallow_lot"),
        (99.99, 9.999, "shallow_lot"),
        (100, 13, "base"),
        (100.01, 13, "base"),
        (150, 13, "base"),
        (150.01, 15.001, "deep_lot"),
        (160, 16, "deep_lot"),
        (40, 5, "shallow_lot"),
    ],
)
def test_rear_setback_by_depth(rs, depth, expected, variant):
    d = rv.rear_setback(rs, depth)
    assert d.value == pytest.approx(expected)
    assert d.variant_id == variant


def test_rear_setback_alley_credit(rs):
    assert rv.rear_setback(rs, 100, alley_width_ft=12).value == pytest.approx(7)
    assert rv.rear_setback(rs, 100, alley_width_ft=30).value == pytest.approx(5)


@pytest.mark.parametrize("width, expected", [(45, 3.6), (50, 4), (49.99, 0.08 * 49.99), (60, 4)])
def test_side_setback_narrow_lot(rs, width, expected):
    decision, _ = rv.side_setback(rs, width, is_corner=False)
    assert decision.value == pytest.approx(expected)


def test_side_reassignment_flag(rs):
    assert rv.side_setback(rs, 50, False)[1] is False
    assert rv.side_setback(rs, 55, True)[1] is True


def test_corner_lot_uses_corner_minimum_width(rs):
    decision, _ = rv.side_setback(rs, 52, is_corner=True)
    assert decision.variant_id == "narrow_lot"


def test_front_setback_variants(rs):
    assert rv.front_setback(rs, "local", 0.0).value == 15
    assert rv.front_setback(rs, "cul_de_sac", 0.0).value == 10
    assert rv.front_setback(rs, "local", 0.5).value == 6
    assert rv.front_setback(rs, "cul_de_sac", 0.6).variant_id == "front_slope"


@pytest.mark.parametrize(
    "area, far",
    [(4000, 0.60), (5000, 0.60), (5000.01, 0.59), (6000, 0.59), (10000, 0.55), (10001, 0.54),
     (19000, 0.46), (19001, 0.45), (40000, 0.45)],
)
def test_far_table_boundaries(rs, area, far):
    decision, base = rv.floor_area_ratio(rs, area, 0.0)
    assert decision.value == pytest.approx(far)
    assert base.value == pytest.approx(area)


def test_far_hillside_base_area(rs):
    decision, base = rv.floor_area_ratio(rs, 8000, 0.6)
    # non-steep 3200 < zone minimum 5000 -> 5000 + 25% of 3000
    assert base.value == pytest.approx(5750)
    assert "hillside" in decision.variant_id
    assert decision.quantity.status == "provisional"


def test_hillside_coverage(rs):
    assert rv.hillside_coverage(rs, 0.5).value is None
    assert rv.hillside_coverage(rs, 0.51).value == pytest.approx(0.5)


def test_height_overlay_map(rs):
    assert rv.height_limit(rs, None).value == 24
    d = rv.height_limit(rs, 20)
    assert d.value == 20 and d.variant_id == "height_limit_overlay_map"


def test_third_floor_limits(rs):
    limits = rv.third_floor_limits(rs, 50, 100)
    assert limits["max_width"].value == pytest.approx(35)
    assert limits["max_depth"].value == pytest.approx(50)


def test_angled_plane_angle(rs):
    assert rv.angled_plane(rs, 50)["angle_deg"] == 45
    assert rv.angled_plane(rs, 80)["angle_deg"] == 30
