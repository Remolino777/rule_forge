import copy
import json
from pathlib import Path

import pytest

from spaceplan.core.lib.rules import load_ruleset
from spaceplan.core.lib_aux.json_io import load_resource_json
from spaceplan.pipeline.main.run_capacity import run_capacity

HOUSES = ["interior_50x100", "fan_curve_35_80x100", "fan_cul_de_sac_35_80x100", "corner_55x100", "fan_reverse_80_40x100"]
APARTMENTS = ["apt_2br_interior", "apt_2br_corner"]
BRIEFS = HOUSES + APARTMENTS


def load_brief(name: str) -> dict:
    return copy.deepcopy(load_resource_json("spaceplan", "data", "briefs", f"{name}.json"))


@pytest.fixture(scope="session")
def rs():
    return load_ruleset()


@pytest.fixture(scope="session")
def packages():
    return {name: run_capacity(load_brief(name)) for name in HOUSES}


@pytest.fixture(scope="session")
def apartments():
    return {name: run_capacity(load_brief(name)) for name in APARTMENTS}


# ------------------------------------------------------------------ contract fixtures (refactor tanda 4)
# tests/<module>/fixtures/<contract>_<subject>.json, produced by tools/make_fixtures.py and checked there against
# the frozen snapshot (tests/golden), so each module can be tested without running the whole pipeline.

TESTS = Path(__file__).resolve().parent
GOLDEN = TESTS / "golden"
FIXTURE_MODULE = {"lot_capacity": "lotcap", "site_plan": "site", "zoning_scheme": "zoning", "program": "household",
                  "cost_report": "cost", "program_portfolio": "profiles", "area_matrix": "areas",
                  "stack_plan": "stacking"}


def load_fixture(contract: str, subject: str) -> dict:
    path = TESTS / FIXTURE_MODULE[contract] / "fixtures" / f"{contract}_{subject}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def golden_package(name: str) -> dict:
    return json.loads((GOLDEN / f"package_{name}.json").read_text(encoding="utf-8"))


def _round6(obj):
    if isinstance(obj, float):
        return round(obj, 6)
    if isinstance(obj, dict):
        return {k: _round6(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_round6(v) for v in obj]
    return obj


def normalized(obj):
    """Same normalization as tools/golden_check.py (JSON round trip, floats to 6 decimals)."""
    return _round6(json.loads(json.dumps(obj, default=str)))


def without_seconds(contract: dict) -> dict:
    """Area-matrix contract without its volatile timing fields."""
    data = json.loads(json.dumps(contract))
    for lot in data.get("lots", []):
        lot.pop("seconds", None)
        for e in lot.get("e2", []):
            e.pop("seconds", None)
    return data


def assert_close(actual, expected, tol: float, path: str = "") -> None:
    """Same structure and strings; numbers within `tol` (a contract read back is rounded to the package decimals)."""
    assert type(actual) is type(expected) or {type(actual), type(expected)} <= {int, float}, path
    if isinstance(expected, dict):
        assert set(actual) == set(expected), path
        for k in expected:
            assert_close(actual[k], expected[k], tol, f"{path}/{k}")
    elif isinstance(expected, list):
        assert len(actual) == len(expected), path
        for i, (a, e) in enumerate(zip(actual, expected)):
            assert_close(a, e, tol, f"{path}[{i}]")
    elif isinstance(expected, float) and not isinstance(expected, bool):
        assert abs(actual - expected) <= tol, (path, actual, expected)
    else:
        assert actual == expected, (path, actual, expected)


# ------------------------------------------------------------------ S2.2j: the S2.1 mechanics before the bedroom rules
# Tests of stage S2.1 mechanics (S2.1, S2.1b) run on the interior lot's teens family, which the S2.2j bedroom rules
# (hard bed clearances, in-room paths, strips...) leave without a layout; they run with those rules relaxed.

PRE_S22J_CHANGES = [
    *({"id": f"space.{t}.furniture_{s}", "kind": "soft"} for t in ("bedroom", "primary_suite", "master_bedroom")
      for s in ("w_ft", "d_ft")),
    {"id": "circulation.in_room.enabled", "value": False},
    {"id": "space.strips.enabled", "value": False},
    {"id": "space.bath_fixtures.enabled", "value": False},
    {"id": "door.leaf.support_required", "value": False},
    {"id": "door.conflicts.off_corner", "value": True},
    {"id": "space.master_bedroom.largest", "value": False},
    {"id": "space.guest_room.shared_bath_required", "value": False},
    {"id": "space.policy.walk_through_scope", "value": ["primary_suite"]},
]


def pre_s22j_profile(extra: list | None = None) -> dict:
    from spaceplan.modules.design.lib import design_profile as dp
    from spaceplan.modules.design.lib.design_registry import load_registry

    reg = load_registry()
    return dp.apply(reg, dp.new_profile(reg, "pre_s22j"), [*PRE_S22J_CHANGES, *(extra or [])], "tests", "2026-10-14",
                    "S2.1 mechanics without the S2.2j bedroom rules")


# ------------------------------------------------------------------ V6.8 k1b: the S2.1 mechanics before the stair core
# Tests of earlier stages' mechanics (the S2.1 tiling, the S2.2j bedroom rules) run on cells that the k1b stair core
# (4 ft clear zones in one circulation unit, the core block pinned in S2, a slot per joint edge) draws differently or
# leaves without a layout; they run with the core settings of the registry turned back to the pre-k1b behaviour.

PRE_K1B_CHANGES = [
    {"id": "stair.arrival_clear.depth_ft", "value": 3.0},
    {"id": "stair.arrival_clear.width_from_stair", "value": False},
    {"id": "stair.arrival_clear.single_space", "value": False},
    {"id": "stair.arrival_clear.circulation_only", "value": False},
    {"id": "stair.core.block_first", "value": False},
    {"id": "stair.core.units_touched_weight", "value": 0.0},
    {"id": "stair.joint.rear_anchor", "value": False},
    {"id": "stair.joint.slots_per_edge", "value": 0},
]


# V6.8 k2: the garage -> kitchen route (garage against service or kitchen, service zoned with the kitchen, the
# dining - kitchen link in S2, the route checked in S2.1) changes which zonings and layouts the earlier-mechanics tests
# see; they run with it off as well.
PRE_K2_CHANGES = [
    {"id": "circulation.garage_route.required", "value": False},
    {"id": "circulation.garage_route.service_kitchen_adjacent", "value": False},
    {"id": "circulation.garage_route.service_with_kitchen", "value": False},
    {"id": "circulation.garage_route.length_weight", "value": 0.0},
    {"id": "circulation.garage_route.unit_weight", "value": 0.0},
]


# V6.8 k3: every room a rectangle (leftovers moved on the composed floor, the check hard) leaves the interior lot's
# drawn house of the earlier-mechanics tests without a layout; they run with the rule off as well.
PRE_K3_CHANGES = [
    {"id": "space.rectangles.enabled", "value": False},
]


def pre_k1b_profile(extra: list | None = None) -> dict:
    from spaceplan.modules.design.lib import design_profile as dp
    from spaceplan.modules.design.lib.design_registry import load_registry

    reg = load_registry()
    return dp.apply(reg, dp.new_profile(reg, "pre_k1b"), [*(extra or []), *PRE_K1B_CHANGES, *PRE_K2_CHANGES, *PRE_K3_CHANGES],
                    "tests", "2026-10-17",
                    "earlier S2.1 mechanics without the V6.8 k1b stair core, the k2 garage route nor the k3 rectangles")
