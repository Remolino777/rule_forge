import copy

import pytest

from spaceplan.lib.catalog import CatalogError, catalog_errors, load_catalog
from spaceplan.lib.enums import Scale, Zone
from spaceplan.lib.rules import CRC_RULESET, load_ruleset_resource
from spaceplan.lib.schema_validation import load_schema
from spaceplan.main.run_program import parameter_table


@pytest.fixture(scope="module")
def catalog():
    return load_catalog()


@pytest.fixture(scope="module")
def crc():
    return load_ruleset_resource(*CRC_RULESET)


def test_catalog_is_valid(catalog):
    assert catalog_errors(catalog.data) == []


def test_catalog_vocabulary_matches_enums(catalog):
    assert {z["zone"] for z in catalog.data["zones"]} == {z.value for z in Zone}
    assert {s["scale"] for s in catalog.data["scales"]} == {s.value for s in Scale}
    brief_profiles = set(load_schema("brief")["properties"]["preferences"]["properties"]["profile"]["enum"])
    assert set(catalog.data["profiles"]) == brief_profiles
    for profile in catalog.data["profiles"].values():
        assert set(profile) == {z.value for z in Zone}


def test_habitable_minima_respect_crc(catalog, crc):
    """No catalog range may let a habitable room fall below the CRC minimum area."""
    minimum = crc.rule("C01-HABITABLE-AREA")["value"]
    exempt = crc.params("C01-HABITABLE-AREA", "kitchen_exempt")["exempt_space_types"]
    for t in catalog.data["space_types"]:
        if t["habitable"] and t["space_type"] not in exempt:
            assert t["area"]["min"] >= minimum, t["space_type"]


def test_type_ranges_fit_their_scale_or_declare_exception(catalog):
    for t in catalog.data["space_types"]:
        scale = catalog.scale(t["scale"])
        inside = scale["area_min"] <= t["area"]["min"] and t["area"]["max"] <= scale["area_max"]
        assert inside or "scale_range_exception" in t, t["space_type"]


def test_satellites_are_support_scale(catalog):
    for t in catalog.data["space_types"]:
        assert bool(t.get("host_types")) == (t["scale"] == "support"), t["space_type"]


def test_invalid_catalog_is_rejected(catalog):
    bad = copy.deepcopy(catalog.data)
    bad["space_types"][0]["area"]["min"] = 999
    assert any("min <= target <= max" in e for e in catalog_errors(bad))
    bad = copy.deepcopy(catalog.data)
    bad["typologies"][0]["spaces"].append({"space_type": "sauna", "count": 1})
    assert any("unknown space type" in e for e in catalog_errors(bad))


def test_load_catalog_raises_on_invalid_file(tmp_path, catalog):
    import json

    bad = copy.deepcopy(catalog.data)
    bad["scales"][0]["facade"] = "glass"
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(bad))
    with pytest.raises(CatalogError):
        load_catalog(path)


def test_parameter_table_lists_every_type_with_status(catalog):
    table = parameter_table()
    for t in catalog.data["space_types"]:
        assert f"| {t['space_type']} |" in table
    assert "provisional" in table and "C01-HABITABLE-AREA" in table
