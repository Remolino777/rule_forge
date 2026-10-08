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
"""

from __future__ import annotations

import copy
import csv
import time
from collections import Counter
from pathlib import Path
from typing import Any

from spaceplan.core.lib.catalog import load_catalog
from spaceplan.core.lib.rules import load_ruleset
from spaceplan.core.lib.schema_validation import validate_brief
from spaceplan.core.lib_aux.json_io import dump_json, load_json, load_resource_json
from spaceplan.modules.areas.lib.area_budget import SiteMeasurer, lot_budget
from spaceplan.modules.areas.lib.area_matrix import (
    compact,
    household_cells,
    pareto_cells,
    profile_program,
)
from spaceplan.modules.cost.lib.cost_models import get_cost_model
from spaceplan.modules.cost.lib.quantities import reference_sheet
from spaceplan.modules.household.lib.household_catalog import load_household_catalog
from spaceplan.modules.household.main.run_household import household_stages, resolve_brief_household
from spaceplan.modules.lotcap.lib.flag_lot import resolve_flag_lot
from spaceplan.modules.lotcap.main.run_lotcap import prepare_lot
from spaceplan.modules.profiles.main.run_profiles import profile_programs
from spaceplan.pipeline.main.run_capacity import run_capacity

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


def _e2(catalog_path, body: dict, cells: list[dict], profiles_by_h: dict, k: int, sheets_dir, lang, display,
        lot_polygon) -> list[dict]:
    """Full one-floor zoning for the k best single-floor cells of the lot (distinct households).

    Only the optimum, accessible and staged-final profiles are candidates: the minimum rarely zones on one
    floor (known limitation of step 6.5a: closet laundry, few zones)."""
    order = {"optimum": 0, "accessible": 1, "staged_final": 2}
    candidates = sorted((c for c in cells if c["floors"] == 1 and c["best"] and c["profile"] in order),
                        key=lambda c: (order[c["profile"]], -c["score"]))
    done, seen_h, out = set(), set(), []
    for c in candidates:
        if len(out) >= k:
            break
        if c["archetype_id"] in seen_h:
            continue
        program = profile_program(profiles_by_h[c["household_id"]], c["profile"])["program"]
        key = repr(sorted((s["space_id"], s["target_area_sqft"]) for s in program["spaces"]))
        if key in done:
            continue
        done.add(key)
        seen_h.add(c["archetype_id"])
        trial = copy.deepcopy(body)
        trial.pop("program", None)
        trial["household"] = {"archetype_id": c["archetype_id"],
                              "cultural_profile": None if c["culture"] == "none" else c["culture"]}
        trial, _, _ = resolve_brief_household(trial, catalog_path)  # cultural overrides, as in step 6.5d
        trial.pop("household", None)
        trial["program"] = program
        trial["meta"]["brief_id"] = f"{body['meta']['brief_id']}-{c['household_id'].replace('.', '-')}-{c['profile']}"
        t0 = time.time()
        pkg = run_capacity(trial, corrections=False, catalog_path=catalog_path)
        option = pkg["zoning"]["options"][0]
        rec = {"household_id": c["household_id"], "profile": c["profile"], "scheme_id": c["scheme_id"],
               "status": option["status"], "valid": option.get("valid"),
               "space_level_valid": (option.get("space_level") or {}).get("valid"),
               "seconds": round(time.time() - t0, 1)}
        c["e2"] = {k2: rec[k2] for k2 in ("status", "valid", "space_level_valid")}
        if sheets_dir and option["status"] == "zoned":
            from spaceplan.modules.viz.lib.review_notes import (
                render_observations,
                scheme_observations,
            )
            from spaceplan.modules.viz.lib.visualize import plot_review_sheet, space_label_fn

            obs = scheme_observations(pkg, program)
            notes = render_observations(obs, display["review_notes"][lang], space_label_fn(display["labels"][lang],
                                                                                           program))
            s = option["schemes"][0]["scores"]
            header = [f"E2 · {body['meta']['brief_id']} · {c['household_id']} · {c['profile']} · {c['scheme_id']}",
                      f"IC {c['IC']:.2f} / {c['IC_max']:.2f} · IO {c['IO']:.2f} · jardín {c['garden_sqft']:.0f} ft² · "
                      f"índice {c['index']:.3f}" if lang == "es" else
                      f"IC {c['IC']:.2f} / {c['IC_max']:.2f} · IO {c['IO']:.2f} · garden {c['garden_sqft']:.0f} sq ft",
                      f"{option['valid']} zonificaciones válidas · puntaje {s['total']:.2f}" if lang == "es" else
                      f"{option['valid']} valid zonings · score {s['total']:.2f}"]
            path = Path(sheets_dir) / f"{body['meta']['brief_id']}_E2_{c['household_id']}_{c['profile']}.png"
            path.parent.mkdir(parents=True, exist_ok=True)
            plot_review_sheet(lot_polygon, pkg, program, path, header, notes, display, lang)
            rec["sheet"] = str(path)
        out.append(rec)
    return out


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


def run_area_matrix(
    lots: list[str] | None = None,
    households: list[tuple[str, str | None]] | None = None,
    cost_model: str | None = None,
    measure_site: bool = True,
    zone_top: int | None = None,
    sheets_dir: str | Path | None = None,
    lang: str | None = None,
    rules_path: str | Path | None = None,
    catalog_path: str | Path | None = None,
    household_catalog_path: str | Path | None = None,
    forced_schemes: tuple[str, ...] = (),
) -> dict[str, Any]:
    rs = load_ruleset(rules_path)
    catalog = load_catalog(catalog_path)
    display = catalog.data["display"]
    lang = lang or display["default_lang"]
    ci = catalog.data["cost_index"]
    model_name = cost_model or ci["default_model"]
    model = get_cost_model(model_name)
    lots = list(lots or PILOT_LOTS)
    households = households or default_households(household_catalog_path)
    zone_top = catalog.data["area_analysis"]["e2_top_k_per_lot"] if zone_top is None else zone_top
    stair_two_floors = 2 * catalog.space_type(ci["estimates"]["stair_space_type"])["area"]["target"]
    stages = {household_id(a, c): household_stages({"archetype_id": a, "cultural_profile": c},
                                                   household_catalog_path) for a, c in households}
    result: dict[str, Any] = {"meta": {"step": "6.6", "model": model_name, "legend": ci["legend"],
                                       "ruleset": rs.version, "catalog": catalog.data["catalog_version"],
                                       "households": list(stages), "lots": lots,
                                       "score_note": catalog.data["vertical_schemes"]["scoring"]["note"]},
                              "lots": [], "cells": []}
    for name in lots:
        t0 = time.time()
        brief = load_lot_brief(name)
        validate_brief(brief)
        body, flag = resolve_flag_lot(brief)
        setup = prepare_lot(body, rs, catalog)
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
        e2 = []
        if zone_top:
            e2 = _e2(catalog_path, body, cells, profiles_by_h, zone_top, sheets_dir, lang, display,
                     setup.lot.polygon)
        lot = {"budget": budget.to_dict(), "summary": lot_summary(cells), "e2": e2,
               "site_calls": measurer.calls if measurer else 0, "seconds": round(time.time() - t0, 1),
               "lot_polygon": [list(p) for p in brief["lot"]["vertices"]]}
        result["lots"].append(lot)
        result["cells"].extend(cells)
    if sheets_dir:
        from spaceplan.modules.viz.lib.visualize import (
            plot_area_budget,
            plot_decision_map,
            plot_ic_io,
            plot_scheme_matrix,
        )

        out = Path(sheets_dir)
        out.mkdir(parents=True, exist_ok=True)
        figures = []
        for lot in result["lots"]:
            lid = lot["budget"]["lot_id"]
            lot_cells = [c for c in result["cells"] if c["lot_id"] == lid]
            figures.append(plot_decision_map(lot, lot_cells, out / f"{lid}_decision_map.png", display, lang))
            figures.append(plot_area_budget(lot, lot_cells, out / f"{lid}_area_budget.png", display, lang))
            figures.append(plot_ic_io(lot, lot_cells, out / f"{lid}_ic_io.png", display, lang))
        figures.append(plot_scheme_matrix(result, out / "pilot_best_schemes.png", display, lang))
        result["figures"] = [str(f) for f in figures]
    return result


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


__all__ = ["PILOT_LOTS", "default_households", "household_id", "lot_summary", "run_area_matrix", "write_tables"]
