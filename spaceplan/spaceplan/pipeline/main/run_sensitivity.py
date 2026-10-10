"""Workflow of the `sensitivity` command: normative sensitivity of the pilot to the design FOS and the FOT.

    pilot lots (briefs) -> flag-lot transform and layer 0 (lotcap) -> lot budgets with the design variables (areas)
    households (archetype x cultural profile) -> uncapped expansion curve (profiles): minimum and complete program
    -> FOS sweep (SDMC FOT) and fixed-FOT sweep (base FOS) per lot (areas.lib.sensitivity)
    -> thresholds per lot, table and figure (viz)

Lot budgets can come from an area_matrix contract instead (`lots[].budget.design`).
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from spaceplan.core.lib.catalog import load_catalog
from spaceplan.core.lib.contracts import read_contract
from spaceplan.core.lib.design_variables import DesignVariables, load_design_variables
from spaceplan.core.lib.rules import load_ruleset
from spaceplan.core.lib.schema_validation import validate_brief
from spaceplan.core.lib_aux.json_io import dump_json
from spaceplan.modules.areas.lib.area_budget import lot_budget
from spaceplan.modules.areas.lib.floor_balance import min_ground
from spaceplan.modules.areas.lib.sensitivity import sweep, thresholds
from spaceplan.modules.areas.main.run_area_matrix import (
    PILOT_LOTS,
    default_households,
    household_id,
    load_lot_brief,
)
from spaceplan.modules.cost.lib.cost_models import get_cost_model
from spaceplan.modules.cost.lib.quantities import reference_sheet
from spaceplan.modules.household.main.run_household import household_stages
from spaceplan.modules.lotcap.main.run_lotcap import flag_lot_body, prepare_lot
from spaceplan.modules.profiles.lib.program_profiles import profile_programs

DEFAULT_FOS = [round(0.40 + 0.05 * i, 2) for i in range(9)]
DEFAULT_FOT = [round(0.45 + 0.05 * i, 2) for i in range(16)]


def lot_budgets(lots: list[str], design: DesignVariables, catalog, rs) -> list[dict[str, Any]]:
    out = []
    for name in lots:
        brief = load_lot_brief(name)
        validate_brief(brief)
        body, flag = flag_lot_body(brief)
        setup = prepare_lot(body, rs, catalog)
        out.append({"budget": lot_budget(catalog, rs, body, setup, flag, design).to_dict()})
    return out


def household_demands(households, catalog) -> dict[str, dict[str, float]]:
    """Minimum and complete program (expansion curve without ceilings) of every household, with the smallest ground
    floor a balanced two-floor split of each reaches (step 9a): lot-independent."""
    model = get_cost_model(catalog.data["cost_index"]["default_model"])
    reference = reference_sheet(catalog, 3000.0, "lot_normative_max")
    out = {}
    for a, c in households:
        st = household_stages({"archetype_id": a, "cultural_profile": c})
        _, profiles = profile_programs(st, catalog, model, reference)
        facts = st["now"]["derivation"].facts
        out[household_id(a, c)] = {
            "minimum": profiles["minimum"]["gross_area_sqft"],
            "complete": profiles["maximum"]["gross_area_sqft"],
            "minimum_ground_min": min_ground(catalog, profiles["minimum"]["program"], facts),
            "complete_ground_min": min_ground(catalog, profiles["maximum"]["program"], facts)}
    return out


def run_sensitivity(area_matrix: dict | None = None, lots: list[str] | None = None,
                    households: list[tuple[str, str | None]] | None = None, design: DesignVariables | None = None,
                    fos_grid: list[float] | None = None, fot_grid: list[float] | None = None) -> dict[str, Any]:
    catalog, rs = load_catalog(), load_ruleset()
    design = design or load_design_variables()
    if area_matrix is not None:
        am = read_contract(area_matrix, "area_matrix")
        budgets = [{"budget": lot["budget"]} for lot in am["lots"] if lot["budget"].get("design")]
        if not budgets:
            raise ValueError("sensitivity: the area_matrix contract has no design budgets (run areas with the "
                             "design variables)")
    else:
        budgets = lot_budgets(list(lots or PILOT_LOTS), design, catalog, rs)
    demands = household_demands(households or default_households(), catalog)
    stair = 2 * catalog.space_type(catalog.data["cost_index"]["estimates"]["stair_space_type"])["area"]["target"]
    rows = sweep(design, budgets, demands, fos_grid or DEFAULT_FOS, fot_grid or DEFAULT_FOT, stair)
    return {"meta": {"step": "6.7a-areas", "design_variables": design.to_dict(), "stair_two_floors_sqft": stair,
                     "fos_grid": fos_grid or DEFAULT_FOS, "fot_grid": fot_grid or DEFAULT_FOT,
                     "lots": [b["budget"]["lot_id"] for b in budgets],
                     "note": "FOS sweep with the SDMC FOT; FOT sweep with fixed values (scenario) at the base FOS. "
                             "Classes: one_floor (demand <= footprint), two_floors (demand + stair on both floors "
                             "<= effective maximum), split_fails (two floors hold the area but the smallest balanced "
                             "ground floor exceeds the footprint, step 9a), exceeds."},
            "demands": demands, "rows": rows, "thresholds": thresholds(rows, demands)}


def write_sensitivity(result: dict[str, Any], out_dir: str | Path) -> list[Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    dump_json(result, out / "sensitivity.json")
    path = out / "sensitivity_grid.csv"
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(result["rows"][0]))
        writer.writeheader()
        writer.writerows(result["rows"])
    return [out / "sensitivity.json", path]


def sensitivity_lines(result: dict[str, Any]) -> list[str]:
    dv = result["meta"]["design_variables"]
    lines = [f"sensitivity  base FOS {dv['fos']:g} x {dv['fos_base']}  FOT {dv['fot_source']}  "
             f"households {len(result['demands'])}  lots {len(result['meta']['lots'])}"]
    for t in result["thresholds"]:
        lines.append(f"  {t['lot_id']:<26} median complete {t['median_complete_sqft']:.0f} sq ft  one floor from FOS "
                     f"{t['fos_for_median_one_floor']}  all complete programs fit from FOT {t['fot_for_all_complete']}"
                     f"  every split from FOS {t.get('fos_for_every_split')}  (high FOT capped by {t['governing_at_high_fot']})")
    return lines


__all__ = ["DEFAULT_FOS", "DEFAULT_FOT", "household_demands", "lot_budgets", "run_sensitivity", "sensitivity_lines",
           "write_sensitivity"]
