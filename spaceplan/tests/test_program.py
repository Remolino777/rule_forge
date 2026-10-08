import pytest

from conftest import load_brief
from spaceplan.lib.catalog import load_catalog
from spaceplan.lib.program_builder import expand_typology
from spaceplan.lib.program_review import review_program
from spaceplan.lib.rules import CRC_RULESET, load_ruleset_resource
from spaceplan.lib.schema_validation import BriefValidationError, validate_brief
from spaceplan.main.run_capacity import run_capacity


@pytest.fixture(scope="module")
def catalog():
    return load_catalog()


@pytest.fixture(scope="module")
def crc():
    return load_ruleset_resource(*CRC_RULESET)


def checks(review, severity=None):
    return {f["check_id"] for f in review["findings"] if severity is None or f["severity"] == severity}


@pytest.mark.parametrize("typology", ["t2_compact", "t3_standard", "t4_family", "apt_1br", "apt_2br"])
@pytest.mark.parametrize("cars", [0, 1, 2])
@pytest.mark.parametrize("profile", ["balanced", "compact", "social", "private"])
def test_every_typology_expands_to_a_clean_program(catalog, crc, typology, cars, profile):
    if typology.startswith("apt") and cars:
        from spaceplan.lib.catalog import CatalogError

        with pytest.raises(CatalogError):
            expand_typology(catalog, typology, cars, profile)
        return
    program = expand_typology(catalog, typology, cars, profile)
    review = review_program(catalog, crc, program)
    assert review["counts"]["error"] == 0, review["findings"]
    assert review["counts"]["warning"] == 0, review["findings"]
    assert sum(s["zone"] == "garage" for s in program["spaces"]) == (1 if cars else 0)


def test_t3_ids_hosts_and_budgets(catalog):
    program = expand_typology(catalog, "t3_standard", 2)
    ids = [s["space_id"] for s in program["spaces"]]
    assert ids.count("bedroom_1") == 1 and "bedroom" not in ids and "garage_2car" in ids
    hosts = {s["space_id"]: s["host_space_id"] for s in program["spaces"]}
    assert hosts["closet_1"] == "bedroom_1" and hosts["closet_2"] == "bedroom_2"
    assert hosts["pantry"] == "kitchen" and hosts["living_room"] is None
    garage = next(s for s in program["spaces"] if s["zone"] == "garage")
    assert garage["floor_preference"] == 0
    private = [s for s in program["spaces"] if s["zone"] == "private"]
    assert program["zone_budgets"]["private"]["min_sqft"] == sum(s["min_area_sqft"] for s in private)


def test_profile_moves_targets_within_ranges(catalog):
    balanced = {s["space_id"]: s for s in expand_typology(catalog, "t3_standard", 2, "balanced")["spaces"]}
    social = {s["space_id"]: s for s in expand_typology(catalog, "t3_standard", 2, "social")["spaces"]}
    assert social["living_room"]["target_area_sqft"] > balanced["living_room"]["target_area_sqft"]
    assert social["bedroom_1"]["target_area_sqft"] <= balanced["bedroom_1"]["target_area_sqft"]
    for space_id, s in social.items():
        area = catalog.space_type(s["space_type"])["area"]
        assert area["min"] <= s["target_area_sqft"] <= area["max"], space_id


def test_expansion_is_deterministic(catalog):
    assert expand_typology(catalog, "t4_family", 1, "private") == expand_typology(catalog, "t4_family", 1, "private")


def test_expanded_program_drops_into_a_brief_and_runs(catalog):
    brief = load_brief("interior_50x100")
    brief["program"] = expand_typology(catalog, "t4_family", 2)
    brief["relations"] = [r for r in brief["relations"]]  # zone-level relations stay valid
    validate_brief(brief)
    pkg = run_capacity(brief)
    assert pkg["program_review"]["buildable_as_stated"] is True
    required = pkg["capacity"]["required_gross_area"]
    assert required["status"] == "provisional" and required["value"] == pytest.approx(
        pkg["program_review"]["summary"]["gross_estimate_sqft"]
    )


def test_reference_briefs_review_clean(packages):
    for pkg in packages.values():
        assert pkg["program_review"]["counts"] == {"error": 0, "warning": 0, "info": 0}


def test_small_bedroom_violates_crc(catalog, crc):
    program = expand_typology(catalog, "t2_compact", 1)
    bedroom = next(s for s in program["spaces"] if s["space_type"] == "bedroom")
    bedroom["min_area_sqft"] = 60
    review = review_program(catalog, crc, program)
    crc_findings = [f for f in review["findings"] if f["check_id"] == "crc_habitable_area"]
    assert len(crc_findings) == 1 and crc_findings[0]["status"] == "provisional"
    assert review["buildable_as_stated"] is False


def test_small_kitchen_is_exempt_from_crc_area(catalog, crc):
    program = expand_typology(catalog, "t2_compact", 1)
    kitchen = next(s for s in program["spaces"] if s["space_type"] == "kitchen")
    kitchen["min_area_sqft"] = 60
    kitchen["target_area_sqft"] = 65
    review = review_program(catalog, crc, program)
    assert "crc_habitable_area" not in checks(review)
    assert {"type_range", "scale_range"} & checks(review, "warning")
    assert review["summary"]["min_side_ft"]["kitchen"] is None


def test_structural_errors_are_reported(catalog, crc):
    program = expand_typology(catalog, "t3_standard", 2)
    program["spaces"] = [s for s in program["spaces"] if s["zone"] not in ("garage", "kitchen")]
    program["spaces"][0]["zone"] = "service"
    program["required_gross_area_sqft"] = 500
    review = review_program(catalog, crc, program)
    assert {"garage_missing", "kitchen_missing", "zone_mismatch", "gross_below_net"} <= checks(review, "error")


def test_satellite_without_host_and_unknown_type(catalog, crc):
    program = expand_typology(catalog, "t3_standard", 2)
    program["spaces"].append({"space_id": "linen", "space_type": "closet", "zone": "private", "scale": "support",
                              "wet": False, "min_area_sqft": 6, "target_area_sqft": 10, "host_space_id": None})
    program["spaces"].append({"space_id": "gym", "space_type": "gym", "zone": "social", "scale": "normal",
                              "wet": False, "min_area_sqft": 110, "target_area_sqft": 150})
    review = review_program(catalog, crc, program)
    assert "satellite_without_host" in checks(review, "warning")
    assert "space_type_unknown" in checks(review, "error")


def test_brief_rejects_dangling_host():
    brief = load_brief("interior_50x100")
    brief["program"]["spaces"][1]["host_space_id"] = "nowhere"
    with pytest.raises(BriefValidationError, match="host_space_id"):
        validate_brief(brief)


def test_out_of_scope_package_still_reviews_program():
    brief = load_brief("interior_50x100")
    brief["overlays"]["vhfhsz"] = True
    pkg = run_capacity(brief)
    assert pkg["scope"]["in_scope"] is False and pkg["program_review"]["summary"]["net_area_sqft"] == 1800
