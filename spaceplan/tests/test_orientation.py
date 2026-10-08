import math

import pytest

from spaceplan.lib.catalog import load_catalog
from spaceplan.lib.orientation import compass_azimuth, exposure, facade_affinity

MODEL = load_catalog().data["orientation_model"]


def test_south_dominates_in_san_diego():
    south, east = exposure(180, 32.7, MODEL)["sun"], exposure(90, 32.7, MODEL)["sun"]
    assert south == pytest.approx(1.0) and east == pytest.approx(0.0, abs=1e-9)


def test_east_west_dominate_near_the_equator():
    bogota = 4.6
    assert exposure(90, bogota, MODEL)["sun"] > exposure(180, bogota, MODEL)["sun"]
    assert exposure(270, bogota, MODEL)["sun"] == pytest.approx(exposure(90, bogota, MODEL)["sun"])


def test_southern_hemisphere_flips_to_north():
    assert exposure(0, -33.9, MODEL)["sun"] == pytest.approx(1.0)


def test_morning_and_afternoon():
    e = exposure(90, 32.7, MODEL)
    w = exposure(270, 32.7, MODEL)
    assert e["morning_light"] == pytest.approx(1) and w["afternoon_shade"] == pytest.approx(0)


def test_compass_azimuth_uses_north_vector():
    assert compass_azimuth(180, 0) == 180
    assert compass_azimuth(180, 90) == 90
    assert compass_azimuth(10, 30) == pytest.approx(340)


def test_affinity_prefers_south_garden_for_social_and_ignores_for_service():
    catalog = load_catalog()
    facades = [
        {"facade_id": "front", "sun": 0.0, "morning_light": 0.0, "street_exposure": 1.0},
        {"facade_id": "rear", "sun": 1.0, "morning_light": 0.0, "street_exposure": 0.0},
    ]
    a = facade_affinity(catalog, facades)
    assert a["social"]["rear"] > a["social"]["front"]
    assert a["service"] == {"front": 0.0, "rear": 0.0}
    assert all(0 <= v <= 1 for row in a.values() for v in row.values())
    assert math.isclose(a["private"]["front"], 0.0)
