"""Workflow for step 6.5d: household + lot -> portfolio of programs -> optional zoning -> review sheets.

    brief with household (and culture) -> stages now / next -> capacity of the lot (FAR, one-floor area)
        -> expansion curve under the normative and budget ceilings -> minimum, optimum, maximum
        -> staged (minimum today + expansion to the next-stage optimum) and accessible (optimum adapted)
        -> area feasibility per profile (fits one floor / needs two floors / exceeds the code)
        -> [--zone] one-floor zoning of each distinct profile that fits -> review sheet per zoned profile
        -> portfolio sheet (quality vs cost curve, profiles, ceilings)

Without a lot (`household` only) the reading is the reference dwelling and there is no ceiling.
"""

from __future__ import annotations

import copy
from pathlib import Path

from spaceplan.modules.cost.lib.budget import resolve_budget
from spaceplan.core.lib.catalog import load_catalog
from spaceplan.modules.cost.lib.cost_models import get_cost_model
from spaceplan.core.lib.enums import HOUSEHOLD_TIERS as TIERS
from spaceplan.modules.lotcap.lib.lot import build_lot
from spaceplan.modules.profiles.lib.program_profiles import (
    ProfileContext,
    accessible_program,
    expansion_profiles,
    floor_feasibility,
    public,
    staged_profile,
)
from spaceplan.modules.household.lib.program_review import review_program
from spaceplan.modules.cost.lib.quantities import build_sheet, reference_sheet
from spaceplan.modules.viz.lib.review_notes import render_observations, scheme_observations
from spaceplan.core.lib.rules import CRC_RULESET, load_ruleset_resource
from spaceplan.core.lib_aux.json_io import dump_json
from spaceplan.pipeline.main.run_capacity import run_capacity
from spaceplan.modules.household.main.run_household import household_stages, resolve_brief_household

PROFILE_ORDER = ("minimum", "optimum", "maximum", "accessible", "staged")


def _lot_limits(package: dict, catalog) -> dict:
    cap = package["capacity"]
    far = cap["gross_area_max"]["value"]
    realizable = max(r["area"]["value"] for r in package["realizable_capacity"])
    footprint_max = (cap.get("footprint_max_normative") or {}).get("value")
    one_floor = min(realizable, footprint_max) if footprint_max else realizable
    stair = catalog.space_type(catalog.data["cost_index"]["estimates"]["stair_space_type"])["area"]["target"]
    return {"far_sqft": far, "one_floor_max_sqft": one_floor, "stair_sqft": 2 * stair,
            "envelope_sqft": cap["envelope"]["area"]["value"]}


def _review(catalog, program: dict) -> dict:
    r = review_program(catalog, load_ruleset_resource(*CRC_RULESET), program)
    return {"buildable_as_stated": r["buildable_as_stated"], "counts": r["counts"],
            "findings": [f for f in r["findings"] if f["severity"] != "info"]}


def profile_programs(stages: dict, catalog, model, reference, far_sqft: float | None = None,
                     budget_fraction: float | None = None, strategy: str | None = None,
                     mean_slope: float | None = None) -> tuple[dict, dict]:
    """Expansion curve and the five program profiles of a household on one reading (shared with step 6.6)."""
    from spaceplan.modules.cost.lib.cost_models import relative_index

    ci = catalog.data["cost_index"]
    common = {"catalog": catalog, "hcat": stages["hcat"], "reference": reference, "model": model,
              "far_sqft": far_sqft, "budget_fraction": budget_fraction, "strategy": strategy,
              "mean_slope": mean_slope}
    later_ctx = ProfileContext(derivation=stages["later"]["derivation"], needs=stages["later"]["needs"], **common)
    ctx = ProfileContext(derivation=stages["now"]["derivation"], needs=stages["now"]["needs"],
                         next_needs=stages["later"]["needs"], **common)
    exp = expansion_profiles(ctx)
    states = exp["_states"]
    profiles = {k: exp[k] for k in ("minimum", "optimum", "maximum")}

    acc_program, features = accessible_program(catalog, profiles["optimum"]["program"])
    acc_sheet = build_sheet(catalog, acc_program, "accessible", strategy=strategy, mean_slope=mean_slope)
    acc_index = relative_index(model, acc_sheet, reference, ci, ctx.point)
    profiles["accessible"] = {**{k: v for k, v in profiles["optimum"].items() if k not in ("program", "curve_step")},
                              "profile": "accessible", "program": acc_program,
                              "gross_area_sqft": round(acc_sheet.gross_area, 1), "index": round(acc_index, 4),
                              "accessibility": features}
    profiles["staged"] = staged_profile(ctx, later_ctx, states["minimum"], states["optimum"])
    return exp, profiles


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
    ci = catalog.data["cost_index"]
    display = catalog.data["display"]
    lang = lang or display["default_lang"]
    stages = household_stages(raw, catalog_path, dwelling_type=brief.get("dwelling_type", "house"))
    hcat = stages["hcat"]
    budget = budget if budget is not None else brief.get("budget")
    model_name = cost_model or (budget or {}).get("cost_model") or ci["default_model"]
    model = get_cost_model(model_name)

    package, limits, resolved = None, None, None
    if has_lot:
        resolved, _, _ = resolve_brief_household(brief, catalog_path)
        package = run_capacity(brief, corrections=False, catalog_path=catalog_path, cost_model=model_name)
        limits = _lot_limits(package, catalog)
        reference = reference_sheet(catalog, limits["far_sqft"], "lot_normative_max")
        reading = "lot"
    else:
        reference = reference_sheet(catalog, ci["reference_dwelling_gross_sqft"], "reference_dwelling")
        reading = "reference_dwelling"
    resolved_budget = resolve_budget(ci, budget) if has_lot else None
    fraction = None if resolved_budget is None else resolved_budget["fraction_of_max"]
    exp, profiles = profile_programs(
        stages, catalog, model, reference,
        far_sqft=limits["far_sqft"] if limits else None, budget_fraction=fraction,
        strategy=package["meta"]["realization_strategy"] if package else None,
        mean_slope=(brief.get("terrain") or {}).get("mean_slope"))

    for name in ("minimum", "optimum", "maximum", "accessible"):
        p = profiles[name]
        p["feasibility"] = floor_feasibility(p["gross_area_sqft"], limits and limits["far_sqft"],
                                             limits and limits["one_floor_max_sqft"], limits["stair_sqft"] if limits
                                             else 0.0)
        p["review"] = _review(catalog, p["program"])
    for part in ("today", "final"):
        p = profiles["staged"][part]
        p["feasibility"] = floor_feasibility(p["gross_area_sqft"], limits and limits["far_sqft"],
                                             limits and limits["one_floor_max_sqft"], limits["stair_sqft"] if limits
                                             else 0.0)

    sheets = []
    if zone and has_lot:
        zoned_programs: dict[str, dict] = {}
        for name in ("minimum", "optimum", "maximum", "accessible"):
            p = profiles[name]
            if p["feasibility"] != "fits_one_floor":
                p["zoning_status"] = None
                continue
            key = repr(sorted((s["space_id"], s["target_area_sqft"], s["floor_preference"])
                              for s in p["program"]["spaces"]))
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
            status_key = "zoned" if option["status"] == "zoned" else "not_zoned"
            summary = {"status": option["status"], "status_key": status_key, "valid": option.get("valid"),
                       "space_level_valid": (option.get("space_level") or {}).get("valid"),
                       "best_score": option["schemes"][0]["scores"]["total"] if option.get("schemes") else None}
            p["zoning"], p["zoning_status"] = summary, status_key
            zoned_programs[key] = {"profile": name, "summary": summary}
            if status_key == "zoned":
                obs = scheme_observations(pkg, p["program"])
                p["observations"] = obs
                if sheets_dir:
                    from spaceplan.modules.viz.lib.visualize import plot_review_sheet, space_label_fn

                    label = space_label_fn(display["labels"][lang], p["program"])
                    notes = render_observations(obs, display["review_notes"][lang], label)
                    words = display["sheet"][lang]
                    s = option["schemes"][0]["scores"]
                    header = [
                        f"{words['title']} — {words['profiles'][name]} · {brief['meta']['brief_id']}",
                        _household_line(stages, lang),
                        f"{option['valid']} zon. válidas · puntaje {s['total']:.2f} (rel. {s['relations']:.2f}, "
                        f"orient. {s['orientation']:.2f}, forma {s['shape']:.2f})" if lang == "es" else
                        f"{option['valid']} valid zonings · score {s['total']:.2f}",
                        f"Bruta {p['gross_area_sqft']:.0f} ft² · FAR {limits['far_sqft']:.0f} ft² · índice {p['index']:.3f} "
                        f"({model_name}) · calidad {p['quality']:.2f}" if lang == "es" else
                        f"Gross {p['gross_area_sqft']:.0f} sq ft · FAR {limits['far_sqft']:.0f} · index {p['index']:.3f}",
                    ]
                    out = Path(sheets_dir) / f"{brief['meta']['brief_id']}_{name}.png"
                    out.parent.mkdir(parents=True, exist_ok=True)
                    plot_review_sheet(build_lot(brief["lot"]).polygon, pkg, p["program"], out, header, notes,
                                      display, lang)
                    sheets.append(str(out))

    portfolio = {
        "brief_id": brief.get("meta", {}).get("brief_id"),
        "reading": reading,
        "model": model_name,
        "legend": ci["legend"],
        "ceilings": {"far_sqft": limits and limits["far_sqft"], "one_floor_max_sqft": limits and
                     limits["one_floor_max_sqft"], "budget_fraction": fraction, "budget": resolved_budget,
                     "governing": exp["maximum"]["governing"]},
        "household": {"archetype_id": stages["household"].archetype_id,
                      "kitchen_typology": stages["now"]["derivation"].kitchen_typology,
                      "culture_applied": any(t["layer"] == "culture" for t in stages["now"]["derivation"].trace)},
        "quality_note": hcat.data["program_quality"]["note"],
        "curve": exp["curve"],
        "profiles": {k: public(profiles[k]) for k in PROFILE_ORDER},
        "sheets": sheets,
    }
    if sheets_dir:
        from spaceplan.modules.viz.lib.visualize import plot_portfolio_sheet

        words = display["sheet"][lang]
        st = profiles["staged"]
        portfolio["title"] = brief.get("meta", {}).get("brief_id") or "household"
        portfolio["subtitle"] = _household_line(stages, lang) + f" · {words['governing'][exp['maximum']['governing']]}"
        portfolio["staged_lines"] = (
            [f"Hoy: índice {st['index_today']:.3f} · después: {st['index_later']:.3f} · total {st['index_total']:.3f}",
             f"Construir el final de una vez: {st['index_build_final_now']:.3f} · prima por etapas "
             f"{st['staging_premium']:+.3f}",
             f"Ampliación {st['expansion_gross_sqft']:.0f} ft²; convertibles hoy: {', '.join(st['convertible_now']) or '-'}"]
            if lang == "es" else
            [f"Today {st['index_today']:.3f} · later {st['index_later']:.3f} · total {st['index_total']:.3f}",
             f"Build final now {st['index_build_final_now']:.3f} · staging premium {st['staging_premium']:+.3f}"])
        portfolio["notes"] = [words["cost_legend"]]
        out = Path(sheets_dir) / f"{portfolio['title']}_portfolio.png"
        out.parent.mkdir(parents=True, exist_ok=True)
        plot_portfolio_sheet(portfolio, out, display, lang)
        portfolio["sheets"].append(str(out))
    return portfolio


def _household_line(stages: dict, lang: str) -> str:
    h = stages["household"]
    d = stages["now"]["derivation"]
    culture = h.cultural_profile or ("aspectos propios" if h.culture_aspects else "sin perfil")
    if lang != "es":
        culture = h.cultural_profile or ("own aspects" if h.culture_aspects else "no profile")
        return f"Household {h.archetype_id or 'custom'} · {len(h.members)} members · culture {culture} · kitchen {d.kitchen_typology}"
    return (f"Hogar {h.archetype_id or 'propio'} · {len(h.members)} personas · perfil cultural {culture} · "
            f"cocina {d.kitchen_typology}")


def run_profiles_file(path: str | Path, out: str | Path | None = None, **kwargs) -> dict:
    from spaceplan.core.lib_aux.json_io import load_json

    result = run_profiles(load_json(path), **kwargs)
    if out:
        dump_json(result, out)
    return result


__all__ = ["TIERS", "profile_programs", "run_profiles", "run_profiles_file"]
