"""Step 6.7a: vertical ruleset (131.0444 plane geometry, 113.0270 height, 113.0234 basements, 113.0261 stories)
and the domain-free vertical geometry."""

import ast
import math
from pathlib import Path

import pytest

from spaceplan.modules.stacking.lib.vertical_rules import (
    BASEMENT_RULE,
    GARAGE_RULE,
    HEIGHT_RULE,
    PLANE_RULE,
    STORY_RULE,
    classify_below_grade,
    first_story_ok,
    garage_counts_in_gfa,
    height_envelope,
    load_vertical_ruleset,
    overall_height_limit,
    slope_class,
)
from spaceplan.modules.stacking.lib_aux.vertical_geometry import (
    floor_sides,
    plane_offset,
    roof_rise,
    scaled_sides,
)

STACKING = Path(__file__).resolve().parents[2] / "spaceplan" / "modules" / "stacking"


@pytest.fixture(scope="module")
def vrs():
    return load_vertical_ruleset()


def test_ruleset_rules_have_source_and_status(vrs):
    ids = {r["rule_id"] for r in vrs.data["rules"]}
    assert {PLANE_RULE, HEIGHT_RULE, BASEMENT_RULE, STORY_RULE, GARAGE_RULE} == ids
    for rule in vrs.data["rules"]:
        assert rule["source"]["document"] and rule["source"]["section"]
        assert isinstance(rule["verified"], bool) and rule["text"]
    # the plane start height is only in Diagram 131-04L: it must stay provisional until verified
    assert vrs.status(PLANE_RULE) == "provisional"
    assert vrs.status(BASEMENT_RULE) == vrs.status(STORY_RULE) == "verified"


def test_vertical_ruleset_does_not_touch_the_capacity_ruleset():
    """The capacity ruleset (and so the golden packages) stays as it was: Z05 keeps 24 ft as its maximum."""
    from spaceplan.core.lib.rules import load_ruleset

    rs = load_ruleset()
    assert rs.version == "0.4.0" and rs.rule("Z05-HEIGHT-MAX")["value"] == 24


@pytest.mark.parametrize("exposure, slope, band", [
    (0.0, 0.0, "outside_gfa"),
    (3.5, 0.0, "outside_gfa"),       # 'exceeds 3 ft 6 in': 3.5 is not counted
    (3.6, 0.0, "gfa_not_story"),
    (4.5, 0.03, "gfa_not_story"),
    (4.5, 0.05, "outside_gfa"),      # 5 percent or more: the threshold is 5 ft
    (5.0, 0.20, "outside_gfa"),
    (5.5, 0.20, "gfa_not_story"),
    (6.0, 0.0, "story"),             # 6 ft or more at any point: a story
    (6.0, 0.20, "story"),
])
def test_below_grade_bands(vrs, exposure, slope, band):
    out = classify_below_grade(vrs, exposure, slope)
    assert out["band"] == band
    assert out["counts_in_gfa"] == (band != "outside_gfa")
    assert out["is_story"] == (band == "story")


def test_slope_class_and_first_story(vrs):
    assert slope_class(vrs, None) == slope_class(vrs, 0.049) == "flat"
    assert slope_class(vrs, 0.05) == "sloped"
    assert first_story_ok(vrs, 1.0) and first_story_ok(vrs, 2.5) and not first_story_ok(vrs, 2.6)


def test_overall_height_limit_caps_the_grade_differential(vrs):
    assert overall_height_limit(vrs, 30.0, 0.0) == 30.0
    assert overall_height_limit(vrs, 30.0, 4.0) == 34.0
    assert overall_height_limit(vrs, 30.0, 25.0) == 40.0
    assert overall_height_limit(vrs, 30.0, -3.0) == 30.0


def test_height_envelope_combines_lotcap_plane_and_v01(vrs):
    env = height_envelope(vrs, {"angle_deg": 45, "front_trigger_height_ft": 27, "status": "provisional",
                                "source": "SDMC 131.0444(b)(c)"})
    assert (env.start_ft, env.overall_max_ft, env.angle_deg, env.front_trigger_ft) == (24.0, 30.0, 45, 27)
    assert env.status == "provisional"
    assert height_envelope(vrs, {"angle_deg": None, "front_trigger_height_ft": 27}).angle_deg is None


def test_garage_counts_in_gfa(vrs):
    assert garage_counts_in_gfa(vrs) is True


def test_plane_offset_and_roof_rise():
    assert plane_offset(-1.0, 45) == 0.0 and plane_offset(0.0, 45) == 0.0
    assert plane_offset(2.0, 45) == pytest.approx(2.0)
    assert plane_offset(3.0, 30) == pytest.approx(3.0 * math.tan(math.radians(30)))
    assert roof_rise(30.0, 1 / 3) == pytest.approx(5.0)
    assert roof_rise(-4.0, 0.5) == 0.0


def test_floor_sides_and_scaling():
    s = floor_sides(1200.0, 40.0)
    assert (s.width, s.depth, s.short, s.short_is_width) == (40.0, 30.0, 30.0, False)
    up = scaled_sides(s, 300.0)
    assert up.width * up.depth == pytest.approx(300.0)
    assert up.width / up.depth == pytest.approx(s.width / s.depth)
    assert floor_sides(0.0, 40.0).depth == 0.0 and scaled_sides(s, 0.0).width == 0.0


NORMATIVE = {24, 30, 27, 3.5, 6.0, 2.5, 0.05, 45}


@pytest.mark.parametrize("path", sorted((STACKING / "lib").glob("*.py")) + sorted((STACKING / "lib_aux").glob("*.py")),
                         ids=lambda p: p.name)
def test_no_normative_numbers_in_stacking_code(path):
    """Heights, thresholds and angles come from the rulesets, never from literals."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    literals = {n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, (int, float))
                and not isinstance(n.value, bool)}
    assert not literals & NORMATIVE
