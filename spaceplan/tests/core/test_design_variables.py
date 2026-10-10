"""Client design variables (2026-10-09): editable FOS and FOT, overrides and the limit that governs."""

import json

import pytest

from spaceplan.core.lib.design_variables import (
    ENVELOPE,
    FIXED,
    LOT,
    SDMC,
    DesignVariablesError,
    design_limits,
    load_design_variables,
)


def test_defaults_are_the_client_decisions():
    dv = load_design_variables()
    assert (dv.fos, dv.fos_base, dv.fot_source, dv.fot_fixed) == (0.6, ENVELOPE, SDMC, 0.85)
    assert (dv.floors_policy, dv.optimum_policy) == ("one_floor_first", "footprint")
    assert dv.lot_minimum["typology_id"] == "h1_basic" and dv.normative and dv.overridden == ()


def test_overrides_are_validated_and_recorded():
    dv = load_design_variables(fos=0.5, fot_source=FIXED, fot_fixed=0.9)
    assert (dv.fos, dv.fot_source, dv.fot_fixed, dv.normative) == (0.5, FIXED, 0.9, False)
    assert set(dv.overridden) == {"fos", "fot_source", "fot_fixed"}
    with pytest.raises(DesignVariablesError):
        load_design_variables(fos=1.4)
    with pytest.raises(DesignVariablesError):
        load_design_variables(fos_base="parcel")


def test_values_are_editable_in_the_file(tmp_path):
    from spaceplan.core.lib_aux.json_io import load_resource_json

    data = load_resource_json("spaceplan", "data", "rules", "client_design_variables.json")
    data["rules"][0]["value"] = 0.55
    data["rules"][1]["parameters"]["source"] = "fixed"
    path = tmp_path / "dv.json"
    path.write_text(json.dumps(data))
    dv = load_design_variables(path)
    assert dv.fos == 0.55 and dv.fot_source == FIXED and not dv.normative


def test_limits_on_the_interior_lot():
    dv = load_design_variables()
    lim = design_limits(dv, 5000, 3024, 3024, 3000, 5000, 2)
    assert lim["footprint_sqft"] == pytest.approx(1814.4) and lim["footprint_governing"] == "design_fos"
    assert lim["maximum_sqft"] == 3000 and lim["maximum_governing"] == "sdmc_far" and not lim["exceeds_legal_far"]
    lot = design_limits(dv.with_overrides(fos_base=LOT), 5000, 3024, 3024, 3000, 5000, 2)
    assert lot["footprint_sqft"] == pytest.approx(3000) and lot["footprint_governing"] == "design_fos"
    fixed = design_limits(dv.with_overrides(fot_source=FIXED), 5000, 3024, 3024, 3000, 5000, 2)
    assert fixed["fot_area_sqft"] == pytest.approx(4250) and fixed["exceeds_legal_far"]
    assert fixed["maximum_sqft"] == pytest.approx(2 * 1814.4) and fixed["maximum_governing"] == "height_floors_x_footprint"
    legal = design_limits(dv.with_overrides(fos=0.9), 5000, 3024, 1500, 3000, 5000, 2)
    assert legal["footprint_sqft"] == 1500 and legal["footprint_governing"] == "legal_envelope_or_coverage"
