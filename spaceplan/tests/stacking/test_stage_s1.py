"""Stage S1 of the stacking module (step 6.7a): stair rules and shapes, plan geometry, ground floor, garage,
upper-floor placements, roof against the 131.0444 plane and the S1 workflow through the contract and the CLI."""

import ast
import copy
import json
import math
from pathlib import Path

import pytest
from conftest import load_fixture
from shapely.geometry import LineString, box, shape

from spaceplan.core.lib.contracts import ContractValidationError
from spaceplan.modules.stacking.lib.cell_geometry import DRAWN, allowed_polygon
from spaceplan.modules.stacking.lib.lot_plan import lot_plan, strategy_key
from spaceplan.modules.stacking.lib.lot_vertical import lot_envelope
from spaceplan.modules.stacking.lib.plan_levels import (
    OVER_GARAGE,
    REAR,
    garage_area,
    garage_rect,
    ground_floor,
    upper_floor,
)
from spaceplan.modules.stacking.lib.roof_plane import (
    RIDGE_ALONG_X,
    RIDGE_ALONG_Y,
    check_roof,
    default_ridge,
)
from spaceplan.modules.stacking.lib.stacking_catalog import (
    check_stacking_catalog,
    load_stacking_catalog,
)
from spaceplan.modules.stacking.lib.stair import place_stair, risers_for, stair_shape
from spaceplan.modules.stacking.lib.stair_rules import (
    garage_separation,
    load_stair_ruleset,
    stair_limits,
)
from spaceplan.modules.stacking.lib.vertical_rules import load_vertical_ruleset
from spaceplan.modules.stacking.lib_aux.plan_geometry import (
    cut_band,
    inset_from_lines,
    joint_lines,
    polygon_json,
    rects_along_line,
    segments_of,
)
from spaceplan.modules.stacking.main.contract import from_contract, to_contract
from spaceplan.modules.stacking.main.run_stacking import (
    S1_TABLE_FIELDS,
    run_stacking,
    s1_table_rows,
)

SUBJECT = "interior_50x100_empty_nest_anglo"
STACKING = Path(__file__).resolve().parents[2] / "spaceplan" / "modules" / "stacking"


@pytest.fixture(scope="module")
def scat():
    return load_stacking_catalog()


@pytest.fixture(scope="module")
def limits():
    return stair_limits(load_stair_ruleset())


@pytest.fixture(scope="module")
def inputs():
    return load_fixture("area_matrix", SUBJECT), load_fixture("lot_capacity", "interior_50x100")


@pytest.fixture(scope="module")
def s1(inputs):
    am, lc = inputs
    return run_stacking(am, [lc], mode="all", stage="S1")


# ------------------------------------------------------------------ rules and stair


def test_stair_rules_in_feet_and_provisional(limits):
    assert limits.riser_max_ft == pytest.approx(7.75 / 12) and limits.tread_min_ft == pytest.approx(10 / 12)
    assert limits.width_min_ft == pytest.approx(3.0) and limits.headroom_min_ft == pytest.approx(80 / 12)
    assert limits.landing_min_ft == pytest.approx(3.0) and limits.status == "provisional"
    assert all("CRC 2025" in s for s in limits.sources)
    sep = garage_separation(load_stair_ruleset(), True)
    assert "Type X" in sep["requirement"] and sep["status"] == "provisional"
    assert "Type X" not in garage_separation(load_stair_ruleset(), False)["requirement"]


def test_risers_and_stair_shapes(scat, limits):
    assert risers_for(10.0, 7.75 / 12) == 16 and risers_for(9.0, 7.75 / 12) == 14
    shapes = {t["stair_id"]: stair_shape(t, 10.0, limits, scat.stair_design) for t in scat.stair_types}
    st = shapes["straight"]
    assert (st.risers, st.treads) == (16, 15) and st.riser_ft * 12 == pytest.approx(7.5)
    assert st.riser_ft <= limits.riser_max_ft and st.tread_ft >= limits.tread_min_ft
    assert (st.length_ft, st.span_ft, st.area_sqft) == pytest.approx((15.5, 3.0, 46.5))
    u = shapes["u_turn"]
    assert u.treads == 14 and u.span_ft == pytest.approx(6.0) and u.length_ft == pytest.approx(7 * 10 / 12 + 3)
    lt = shapes["l_turn"]
    assert lt.area_sqft < lt.length_ft * lt.span_ft  # an L takes less than its bounding rectangle
    assert [stair_shape(t, 10.0, limits, scat.stair_design).stair_id for t in scat.stair_types] \
        == ["straight", "u_turn", "l_turn"]


def test_stair_placed_at_the_joint_out_of_the_garage(scat, limits):
    ground = box(0, 0, 40, 30)
    upper = box(0, 15, 40, 30)
    garage = box(28, 0, 40, 24)
    shapes = [stair_shape(t, 10.0, limits, scat.stair_design) for t in scat.stair_types]
    joints = joint_lines(upper, ground)
    assert len(joints) == 1 and joints[0].length == pytest.approx(40.0, abs=0.01)
    p = place_stair(shapes, joints, upper, ground, garage, 1.0)
    assert p is not None and p.shape.stair_id == "straight" and p.run_along_joint
    r = p.placed.rect
    assert upper.buffer(1e-6).contains(r) and r.intersection(garage).area == pytest.approx(0.0)
    assert r.bounds[1] == pytest.approx(15.0)  # touches the joint
    assert place_stair(shapes, joints, box(0, 15, 2, 30), ground, None, 1.0) is None  # too narrow for any type


# ------------------------------------------------------------------ plan geometry (lib_aux)


def test_cut_band_both_sides_and_too_small():
    poly = box(0, 0, 10, 20)
    front, y = cut_band(poly, 50.0, "y", "low")
    assert front.area == pytest.approx(50.0, abs=1e-6) and y == pytest.approx(5.0)
    rear, y = cut_band(poly, 50.0, "y", "high")
    assert rear.bounds[1] == pytest.approx(15.0) and rear.area == pytest.approx(50.0, abs=1e-6)
    assert cut_band(poly, 500.0) is None
    trapezoid = shape({"type": "Polygon", "coordinates": [[[0, 0], [10, 0], [14, 20], [-4, 20], [0, 0]]]})
    part, _ = cut_band(trapezoid, 100.0)
    assert part.area == pytest.approx(100.0, abs=1e-6)


def test_segments_rects_and_inset():
    line = LineString([(0, 0), (5, 0), (10, 0), (10, 4)])
    segs = segments_of(line)
    assert [s.length for s in segs] == pytest.approx([10.0, 4.0])
    placed = rects_along_line(LineString([(0, 10), (20, 10)]), 6.0, 2.0, 1.0, box(0, 0, 20, 10))
    assert placed and all(p.rect.bounds[3] == pytest.approx(10.0) for p in placed)
    assert placed[0].offset_ft == pytest.approx(0.0)
    assert rects_along_line(LineString([(0, 0), (3, 4)]), 1.0, 1.0, 1.0, box(-9, -9, 9, 9)) == []
    cut = inset_from_lines(box(0, 0, 10, 10), [(LineString([(0, 0), (0, 10)]), 2.0)])
    assert cut.bounds[0] == pytest.approx(2.0)
    assert polygon_json(box(0, 0, 1, 1))["type"] == "Polygon" and polygon_json(None) is None


# ------------------------------------------------------------------ ground, garage, upper floor


def test_ground_floor_and_garage_from_the_area_matrix(inputs, scat):
    am, lc = inputs
    plan = lot_plan(lc)
    cell = next(c for c in am["cells"] if c["floors"] == 2)
    fp = plan.footprint_for(*strategy_key(am["lots"][0]["budget"], cell["strategy_used"]))
    ground = ground_floor(fp, cell["split"]["gross_by_floor_sqft"][0], scat.geometry)
    assert ground.area == pytest.approx(cell["split"]["gross_by_floor_sqft"][0], abs=1.0)
    assert ground.bounds[1] == pytest.approx(fp.bounds[1])  # front-anchored
    g = garage_area(cell, plan.far_base_sqft)
    assert g == pytest.approx((cell["IC"] - cell["IC_alternatives"]["garage_excluded"]["IC"]) * 5000.0)
    rect = garage_rect(ground, g, scat.garage)
    assert rect.area == pytest.approx(g, abs=1.0) and rect.bounds[2] == pytest.approx(ground.bounds[2])
    assert rect.bounds[3] <= ground.bounds[3] + 1e-9
    assert garage_area({"IC": 0.3, "IC_alternatives": {}}, 5000.0) == 0.0


def test_garage_width_single_double_and_tandem(scat):
    g = scat.garage
    wide, narrow = box(0, 0, 60, 40), box(0, 0, 24, 60)
    assert garage_rect(wide, 300.0, g).bounds[2] - garage_rect(wide, 300.0, g).bounds[0] == g["single_width_ft"]
    double = garage_rect(wide, 480.0, g)
    assert double.bounds[2] - double.bounds[0] == pytest.approx(g["double_width_ft"])
    tandem = garage_rect(narrow, 480.0, g)  # a double would take more than the allowed share of the width
    assert tandem.bounds[2] - tandem.bounds[0] == pytest.approx(g["single_width_ft"])
    assert garage_rect(wide, 0.0, g) is None


def test_upper_floor_placements_are_contained(scat):
    ground = box(0, 0, 40, 30)
    garage = box(28, 0, 40, 24)
    rear = upper_floor(REAR, ground, 400.0, garage, "right", scat.geometry)
    assert rear.polygon.area == pytest.approx(400.0, abs=1e-6) and rear.polygon.bounds[3] == pytest.approx(30.0)
    assert rear.polygon.difference(ground).area == pytest.approx(0.0)
    og = upper_floor(OVER_GARAGE, ground, 400.0, garage, "right", scat.geometry)
    assert og.polygon.bounds[2] == pytest.approx(40.0) and og.polygon.area == pytest.approx(400.0, abs=1.0)
    assert upper_floor(REAR, ground, 2000.0, garage, "right", scat.geometry).polygon is None
    assert upper_floor(OVER_GARAGE, ground, 400.0, None, "right", scat.geometry).reason == "no garage"
    assert scat.upper_placements("V4")[0] == OVER_GARAGE and scat.upper_placements("V1")[0] == REAR


# ------------------------------------------------------------------ roof against the plane


def test_roof_rotation_frees_the_side_plane(inputs, scat):
    _, lc = inputs
    plan, vrs = lot_plan(lc), load_vertical_ruleset()
    env = lot_envelope(vrs, lc)
    wide = box(4, 40, 46, 70)                 # full envelope width: walls on the side setback lines
    assert default_ridge(wide) == RIDGE_ALONG_X  # spans the short (depth) side: gables face the side lines
    roof = scat.roof("pitched_4_12")
    gable = check_roof(wide, roof, RIDGE_ALONG_X, 20.0, plan, env, vrs, 0.0)
    eave = check_roof(wide, roof, RIDGE_ALONG_Y, 20.0, plan, env, vrs, 0.0)
    flat = check_roof(wide, scat.roof("flat"), None, 20.0, plan, env, vrs, 0.0)
    assert gable["status"] == "plane_governs" and gable["inset_needed_ft"] > 0
    assert gable["governing_edge"] in {"e1", "e3"}
    assert eave["status"] == "within_plane" and eave["top_ft"] > gable["top_ft"]  # wider span, higher ridge
    assert flat["status"] == "within_plane" and flat["top_ft"] == pytest.approx(22.0)
    narrow = box(10, 40, 40, 70)              # 6 ft in from the setback lines
    assert check_roof(narrow, roof, RIDGE_ALONG_X, 20.0, plan, env, vrs, 0.0)["status"] == "within_plane"
    assert allowed_polygon(plan, env, 20.0).equals(plan.envelope)  # walls under the plane start
    assert allowed_polygon(plan, env, 26.0).area < plan.envelope.area


# ------------------------------------------------------------------ workflow and contract


def test_s1_draws_every_two_floor_cell(s1):
    cells = [c for c in s1["cells"] if c.get("s1")]
    assert cells and all(c["floors"] == 2 for c in cells)
    assert all(c["s1"]["status"] == DRAWN and c["next_stage"] == "S2" for c in cells)
    assert not any("s1" in c for c in s1["cells"] if c["floors"] == 1)
    assert s1["meta"]["stage"] == "S1" and s1["meta"]["stair_ruleset"] == "crc-2025-stairs"
    assert s1["meta"]["s1"]["to_s2"] == len(cells)
    assert s1["lots"][0]["summary"]["to_s1"] == len(cells) and "plan" in s1["lots"][0]


def test_s1_geometry_is_consistent(s1):
    for c in (c for c in s1["cells"] if c.get("s1")):
        b = c["s1"]
        ground, upper = shape(b["levels"][0]["polygon"]), shape(b["levels"][1]["polygon"])
        stair = shape(b["stair"]["polygon"])
        assert ground.area == pytest.approx(c["levels"][0]["gross_sqft"], abs=1.0)
        assert upper.area == pytest.approx(c["levels"][1]["gross_sqft"], abs=1.0)
        assert upper.difference(ground).area < 1.0 and b["containment"]["upper_in_ground"]
        assert stair.difference(upper).area < 1e-3 and stair.difference(ground).area < 1e-3
        garage = b["ground"]["garage_polygon"]
        if garage:
            assert stair.intersection(shape(garage)).area < 1e-3
        assert b["stair"]["area_delta_sqft"] == pytest.approx(b["stair"]["area_sqft"] - 60.0)
        assert b["roof"]["kept"] is not None or b["roof"]["inset_needed_ft"] > 0
        assert all(lv["within_allowed"] for lv in b["levels"])


def test_s1_contract_validates_and_round_trips(s1):
    contract = to_contract(s1)
    back = from_contract(contract)
    assert back["meta"]["stage"] == "S1" and back["cells"][0].keys() == s1["cells"][0].keys()
    bad = copy.deepcopy(contract)
    next(c for c in bad["cells"] if c.get("s1"))["s1"]["status"] = "maybe"
    with pytest.raises(ContractValidationError):
        from_contract(bad)


def test_s0_output_is_unchanged_by_stage_s1(inputs, s1):
    am, lc = inputs
    s0 = run_stacking(am, [lc], mode="all")
    for a, b in zip(s0["cells"], s1["cells"]):
        assert {k: v for k, v in a.items() if k != "next_stage"} == \
            {k: v for k, v in b.items() if k not in ("next_stage", "s1")}


def test_s1_table_and_default_mode(s1, inputs, scat):
    rows = s1_table_rows(s1)
    assert rows and set(rows[0]) == set(S1_TABLE_FIELDS)
    assert scat.stage_default_mode("S1") == "best" and scat.stage_default_mode("S0") == "top2"
    am, lc = inputs
    assert run_stacking(am, [lc], stage="S1")["meta"]["selection_mode"] == "best"
    with pytest.raises(ValueError):
        run_stacking(am, [lc], stage="S3")


def test_cli_stacking_stage_s1(tmp_path):
    from spaceplan.pipeline.main.cli import main

    am, lc = tmp_path / "am.json", tmp_path / "lc.json"
    am.write_text(json.dumps(load_fixture("area_matrix", SUBJECT)))
    lc.write_text(json.dumps(load_fixture("lot_capacity", "interior_50x100")))
    out = tmp_path / "sp.json"
    assert main(["stacking", "--stage", "S1", "--cells", "all", "--area-matrix", str(am), "--lot-capacity", str(lc),
                 "-o", str(out), "--tables", str(tmp_path / "t"), "--plans", str(tmp_path / "p")]) == 0
    assert json.loads(out.read_text())["meta"]["stage"] == "S1"
    assert (tmp_path / "t" / "stack_plan_s1.csv").exists()
    assert (tmp_path / "p" / "interior-50x100_stack_plan.png").stat().st_size > 0


# ------------------------------------------------------------------ catalog and data discipline


def test_catalog_s1_blocks_are_checked():
    data = json.loads((STACKING.parents[1] / "data" / "catalog" / "stacking_catalog.json").read_text())
    assert check_stacking_catalog(data) == []
    bad = copy.deepcopy(data)
    bad["stair"]["type_order"] = ["spiral"]
    bad["garage"]["side"] = "middle"
    problems = check_stacking_catalog(bad)
    assert any("type_order" in p for p in problems) and any("garage.side" in p for p in problems)
    missing = copy.deepcopy(data)
    del missing["roof_orientation"]
    assert any("roof_orientation" in p for p in check_stacking_catalog(missing))


STAIR_NUMBERS = {7.75, 36, 80}


@pytest.mark.parametrize("name", ["stair.py", "stair_rules.py", "cell_geometry.py", "plan_levels.py", "roof_plane.py",
                                  "lot_plan.py"])
def test_no_stair_numbers_in_s1_code(name):
    tree = ast.parse((STACKING / "lib" / name).read_text(encoding="utf-8"))
    literals = {n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, (int, float))
                and not isinstance(n.value, bool)}
    assert not literals & STAIR_NUMBERS and not math.isnan(0.0)
