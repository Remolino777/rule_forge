"""Workflow of the `areas` command (step 6.6): area analysis of the pilot lots for every household.

    pilot lots (briefs) -> flag-lot transform and layer 0 per lot (lotcap) -> households (archetype x cultural
    profile) -> stages now / next (household) -> cells of each lot: five program profiles x vertical schemes x
    strategies, E0 and E1 (areas) -> [zone_top] E2: full one-floor zoning of the best single-floor cells
    (capacity pipeline) -> review sheets and figures (viz)

Moved from spaceplan.modules.areas.main.run_area_matrix in refactor tanda 3 without changes: composing
workflows of several modules is the pipeline's job.
"""

from __future__ import annotations

import copy
import time
from pathlib import Path
from typing import Any

from spaceplan.core.lib.catalog import load_catalog
from spaceplan.core.lib.design_variables import load_design_variables
from spaceplan.core.lib.rules import load_ruleset
from spaceplan.core.lib.schema_validation import validate_brief
from spaceplan.modules.areas.lib.area_matrix import profile_program
from spaceplan.modules.areas.main.run_area_matrix import (
    PILOT_LOTS,
    analyze_lot,
    default_households,
    household_id,
    load_lot_brief,
    lot_summary,
    matrix_meta,
)
from spaceplan.modules.cost.lib.cost_models import get_cost_model
from spaceplan.modules.household.main.run_household import household_stages, resolve_brief_household
from spaceplan.modules.lotcap.main.run_lotcap import flag_lot_body, prepare_lot
from spaceplan.pipeline.main.run_capacity import run_capacity


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
            from spaceplan.modules.viz.lib.review_sheets import plot_review_sheet, space_label_fn

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
    design=None,
) -> dict[str, Any]:
    """`design`: the client's design variables (core.lib.design_variables); None loads the defaults of
    data/rules/client_design_variables.json, False runs the step-6.6 logic without them (legacy)."""
    rs = load_ruleset(rules_path)
    if design is None:
        design = load_design_variables()
    elif design is False:
        design = None
    catalog = load_catalog(catalog_path)
    display = catalog.data["display"]
    lang = lang or display["default_lang"]
    ci = catalog.data["cost_index"]
    model_name = cost_model or ci["default_model"]
    model = get_cost_model(model_name)
    lots = list(lots or PILOT_LOTS)
    households = households or default_households(household_catalog_path)
    zone_top = catalog.data["area_analysis"]["e2_top_k_per_lot"] if zone_top is None else zone_top
    stages = {household_id(a, c): household_stages({"archetype_id": a, "cultural_profile": c},
                                                   household_catalog_path) for a, c in households}
    result: dict[str, Any] = {"meta": matrix_meta(catalog, rs, model_name, stages, lots, design), "lots": [],
                              "cells": []}
    for name in lots:
        t0 = time.time()
        brief = load_lot_brief(name)
        validate_brief(brief)
        body, flag = flag_lot_body(brief)
        setup = prepare_lot(body, rs, catalog)
        budget, measurer, cells, profiles_by_h = analyze_lot(catalog, rs, body, setup, flag, stages, model,
                                                             measure_site, forced_schemes, design)
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
        from spaceplan.modules.viz.main.run_viz import area_matrix_figures

        result["figures"] = [str(f) for f in area_matrix_figures(result, sheets_dir, display, lang)]
    return result


__all__ = ["run_area_matrix"]
