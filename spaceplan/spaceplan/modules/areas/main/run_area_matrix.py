"""Workflow for step 6.6: area analysis per lot (program profile x vertical scheme x strategy).

    pilot lots (briefs) -> flag-lot transform -> layer 0 per lot (setbacks, FAR, coverage, realizable
    footprint per strategy) -> lot budget (IC and IO limits, front widths)
    households (archetype x cultural profile) -> stages now / next -> five program profiles on the lot
    (6.5d, with the lot's FAR as ceiling)
    -> applicable vertical schemes (V0-V5) -> floor split -> E0 indices, containment, frontage
    -> E1 measured site per strategy -> household-weighted score -> best scheme and decisive metric
    -> Pareto per household (garden, index, program quality)
    -> [zone_top] E2: full one-floor zoning of the best single-floor cells -> review sheets
    -> figures: decision map, area budget per floor, IC-IO chart per lot; best scheme per household

Refactor tanda 3: this module analyses one prepared lot with the household stages it receives (`analyze_lot`);
the composition (flag lot and layer 0 from lotcap, stages from household, E2 through the capacity pipeline,
figures from viz) lives in spaceplan.pipeline.main.run_area_analysis.run_area_matrix.
"""

from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path
from typing import Any

from spaceplan.core.lib_aux.json_io import dump_json, load_json, load_resource_json
from spaceplan.modules.areas.lib.area_budget import SiteMeasurer, lot_budget
from spaceplan.modules.areas.lib.area_matrix import compact, household_cells, pareto_cells
from spaceplan.modules.cost.lib.quantities import reference_sheet
from spaceplan.modules.household.lib.household_catalog import load_household_catalog
from spaceplan.modules.profiles.lib.program_profiles import profile_programs

PILOT_LOTS = (
    "interior_50x100", "corner_55x100", "shallow_50x95", "narrow_40x125", "hillside_50x100",
    "fan_cul_de_sac_35_80x100", "fan_curve_35_80x100", "fan_reverse_80_40x100", "trapezoid_asym_45_65x100",
    "flag_70x80_pole20",
)
CULTURES = (None, "latino", "anglo")


def load_lot_brief(name_or_path: str) -> dict:
    path = Path(name_or_path)
    if path.suffix == ".json" and path.exists():
        return load_json(path)
    return load_resource_json("spaceplan", "data", "briefs", f"{name_or_path}.json")


def default_households(household_catalog_path: str | Path | None = None) -> list[tuple[str, str | None]]:
    hcat = load_household_catalog(household_catalog_path)
    return [(a["archetype_id"], c) for a in hcat.data["archetypes"] for c in CULTURES]


def household_id(archetype: str, culture: str | None) -> str:
    return f"{archetype}.{culture or 'none'}"


def lot_summary(cells: list[dict]) -> dict[str, Any]:
    best = [c for c in cells if c["best"]]
    status = Counter(c["status"] for c in cells)
    governing = Counter(c["governing"] for c in cells if c["governing"])
    by_floors = {}
    for f in (1, 2):
        sub = [c for c in cells if c["floors"] == f]
        by_floors[str(f)] = {"cells": len(sub), "feasible": sum(c["score"] is not None for c in sub)}
    return {
        "cells": len(cells),
        "status_counts": dict(status),
        "governing_counts": dict(governing),
        "by_floors": by_floors,
        "best_scheme_counts": dict(Counter(c["scheme_id"] for c in best)),
        "decisive_metric_counts": dict(Counter(c.get("decisive_metric") for c in best)),
        "variant_sensitive_cells": sum(bool(c["variant_sensitive"]) for c in cells),
    }


def matrix_meta(catalog, rs, model_name: str, stages: dict, lots: list[str]) -> dict[str, Any]:
    ci = catalog.data["cost_index"]
    return {"step": "6.6", "model": model_name, "legend": ci["legend"], "ruleset": rs.version,
            "catalog": catalog.data["catalog_version"], "households": list(stages), "lots": lots,
            "score_note": catalog.data["vertical_schemes"]["scoring"]["note"]}


def analyze_lot(catalog, rs, body: dict, setup, flag: dict | None, stages: dict, model, measure_site: bool = True,
                forced_schemes: tuple[str, ...] = ()) -> tuple[Any, Any, list[dict], dict]:
    """Cells of one lot (stages E0 and E1) for every household: (lot budget, site measurer or None, cells,
    program profiles per household). `body` is the brief after the flag-lot transform; `setup` is lotcap's
    LotSetup of the body."""
    ci = catalog.data["cost_index"]
    stair_two_floors = 2 * catalog.space_type(ci["estimates"]["stair_space_type"])["area"]["target"]
    budget = lot_budget(catalog, rs, body, setup, flag)
    measurer = SiteMeasurer(catalog, rs, body, setup, budget) if measure_site else None
    reference = reference_sheet(catalog, budget.limits.gross_area_max_sqft, "lot_normative_max")
    slope = (body.get("terrain") or {}).get("mean_slope")
    cells, profiles_by_h = [], {}
    for hid, st in stages.items():
        _, profiles = profile_programs(st, catalog, model, reference,
                                       far_sqft=budget.limits.gross_area_max_sqft,
                                       strategy=budget.strategies[0].strategy, mean_slope=slope)
        _, profiles_2f = profile_programs(st, catalog, model, reference,
                                          far_sqft=budget.limits.gross_area_max_sqft - stair_two_floors,
                                          strategy=budget.strategies[0].strategy, mean_slope=slope)
        profiles_by_h[hid] = profiles
        hc = household_cells(catalog, rs, budget, measurer, hid, st, profiles, model, reference, slope,
                             profiles_two_floors=profiles_2f, forced_schemes=tuple(forced_schemes))
        front = {id(c) for c in pareto_cells(hc)}
        for c in hc:
            c["pareto"] = id(c) in front
        cells.extend(hc)
    return budget, measurer, cells, profiles_by_h


def write_tables(result: dict, out_dir: str | Path) -> list[str]:
    """Full JSON, one CSV row per cell, and a CSV of the best scheme per household and profile."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    dump_json(result, out / "area_matrix.json")
    rows = [compact(c) for c in result["cells"]]
    paths = [str(out / "area_matrix.json")]
    for name, subset in (("area_matrix_cells.csv", rows), ("area_matrix_best.csv", [r for r in rows if r["best"]])):
        with open(out / name, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(subset)
        paths.append(str(out / name))
    return paths


__all__ = ["CULTURES", "PILOT_LOTS", "analyze_lot", "default_households", "household_id", "load_lot_brief",
           "lot_summary", "matrix_meta", "write_tables"]
