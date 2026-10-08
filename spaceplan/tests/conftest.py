import copy

import pytest

from spaceplan.lib.rules import load_ruleset
from spaceplan.lib_aux.json_io import load_resource_json
from spaceplan.main.run_capacity import run_capacity

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
