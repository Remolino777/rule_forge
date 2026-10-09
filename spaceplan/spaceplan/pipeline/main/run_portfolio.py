"""Workflow of the `profiles` command (step 6.5d): household + lot -> portfolio of programs -> zoning -> sheets.

    brief with household (and culture) -> stages now / next (household) -> capacity of the lot (capacity
        pipeline: FAR, one-floor area) -> portfolio of profiles (profiles module)
        -> [--zone] one-floor zoning of each distinct profile that fits (capacity pipeline)
        -> review sheet per zoned profile and portfolio sheet (viz)

Without a lot (`household` only) the reading is the reference dwelling and there is no ceiling.
Moved from spaceplan.modules.profiles.main.run_profiles in refactor tanda 3 without changes: composing
workflows of several modules is the pipeline's job.
"""

from __future__ import annotations

import copy
from pathlib import Path

from spaceplan.core.lib.catalog import load_catalog
from spaceplan.core.lib_aux.json_io import dump_json
from spaceplan.modules.household.main.run_household import household_stages, resolve_brief_household
from spaceplan.modules.lotcap.lib.lot import build_lot
from spaceplan.modules.profiles.main.run_profiles import (
    assess_profiles,
    portfolio_model,
    portfolio_reading,
    portfolio_sheet_texts,
    portfolio_summary,
    program_key,
    review_sheet_header,
    zoning_summary,
)
from spaceplan.modules.viz.lib.review_notes import render_observations, scheme_observations
from spaceplan.pipeline.main.run_capacity import run_capacity


def run_profiles(
    brief: dict,
    budget: dict | None = None,
    cost_model: str | None = None,
    zone: bool = False,
    sheets_dir: str | Path | None = None,
    lang: str | None = None,
    catalog_path: str | Path | None = None,
) -> dict:
    """Portfolio of program profiles for the household of a brief (lot reading) or a bare household."""
    has_lot = "lot" in brief and brief.get("dwelling_type", "house") == "house"
    raw = brief.get("household", brief)
    catalog = load_catalog(catalog_path)
    display = catalog.data["display"]
    lang = lang or display["default_lang"]
    stages = household_stages(raw, catalog_path, dwelling_type=brief.get("dwelling_type", "house"))
    budget = budget if budget is not None else brief.get("budget")
    model_name, model = portfolio_model(catalog, budget, cost_model)

    package, resolved = None, None
    if has_lot:
        resolved, _, _ = resolve_brief_household(brief, catalog_path)
        package = run_capacity(brief, corrections=False, catalog_path=catalog_path, cost_model=model_name)
    rd = portfolio_reading(catalog, package, budget)
    limits = rd.limits
    exp, profiles = assess_profiles(stages, catalog, model, rd, package,
                                    (brief.get("terrain") or {}).get("mean_slope"))

    sheets = []
    if zone and has_lot:
        zoned_programs: dict[str, dict] = {}
        for name in ("minimum", "optimum", "maximum", "accessible"):
            p = profiles[name]
            if p["feasibility"] != "fits_one_floor":
                p["zoning_status"] = None
                continue
            key = program_key(p["program"])
            if key in zoned_programs:
                p["zoning"] = {**zoned_programs[key]["summary"], "same_as": zoned_programs[key]["profile"]}
                p["zoning_status"] = zoned_programs[key]["summary"]["status_key"]
                continue
            trial = copy.deepcopy(resolved)
            trial.pop("household", None)
            trial["program"] = p["program"]
            trial["meta"]["brief_id"] = f"{brief['meta']['brief_id']}-{name}"
            pkg = run_capacity(trial, corrections=False, catalog_path=catalog_path, cost_model=model_name)
            option = pkg["zoning"]["options"][0]
            summary = zoning_summary(option)
            status_key = summary["status_key"]
            p["zoning"], p["zoning_status"] = summary, status_key
            zoned_programs[key] = {"profile": name, "summary": summary}
            if status_key == "zoned":
                obs = scheme_observations(pkg, p["program"])
                p["observations"] = obs
                if sheets_dir:
                    from spaceplan.modules.viz.lib.review_sheets import (
                        plot_review_sheet,
                        space_label_fn,
                    )

                    label = space_label_fn(display["labels"][lang], p["program"])
                    notes = render_observations(obs, display["review_notes"][lang], label)
                    words = display["sheet"][lang]
                    header = review_sheet_header(brief, name, stages, option, p, limits, model_name, words, lang)
                    out = Path(sheets_dir) / f"{brief['meta']['brief_id']}_{name}.png"
                    out.parent.mkdir(parents=True, exist_ok=True)
                    plot_review_sheet(build_lot(brief["lot"]).polygon, pkg, p["program"], out, header, notes,
                                      display, lang)
                    sheets.append(str(out))

    portfolio = portfolio_summary(brief, rd, model_name, catalog, exp, profiles, stages, sheets)
    if sheets_dir:
        from spaceplan.modules.viz.lib.portfolio_sheet import plot_portfolio_sheet

        words = display["sheet"][lang]
        portfolio_sheet_texts(portfolio, brief, stages, exp, profiles, words, lang)
        out = Path(sheets_dir) / f"{portfolio['title']}_portfolio.png"
        out.parent.mkdir(parents=True, exist_ok=True)
        plot_portfolio_sheet(portfolio, out, display, lang)
        portfolio["sheets"].append(str(out))
    return portfolio


def run_profiles_file(path: str | Path, out: str | Path | None = None, **kwargs) -> dict:
    from spaceplan.core.lib_aux.json_io import load_json

    result = run_profiles(load_json(path), **kwargs)
    if out:
        dump_json(result, out)
    return result


__all__ = ["run_profiles", "run_profiles_file"]
