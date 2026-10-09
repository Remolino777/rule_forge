"""Workflow of the profiles module (step 6.5d): portfolio of programs of a household on one reading.

    household stages now / next + reading (lot capacity package, or the reference dwelling)
        -> expansion curve under the normative and budget ceilings -> minimum, optimum, maximum
        -> staged (minimum today + expansion to the next-stage optimum) and accessible (optimum adapted)
        -> area feasibility per profile (fits one floor / needs two floors / exceeds the code)
        -> portfolio summary and the texts of the review and portfolio sheets

Refactor tanda 3: this module receives the household stages and the capacity package as data. The composition
(household workflow, capacity pipeline, one-floor zoning of each profile, figures) lives in
spaceplan.pipeline.main.run_portfolio.run_profiles; `profile_programs` moved to profiles.lib.program_profiles.
"""

from __future__ import annotations

from dataclasses import dataclass

from spaceplan.core.lib.enums import HOUSEHOLD_TIERS as TIERS
from spaceplan.core.lib.rules import CRC_RULESET, load_ruleset_resource
from spaceplan.modules.cost.lib.budget import resolve_budget
from spaceplan.modules.cost.lib.cost_models import get_cost_model
from spaceplan.modules.cost.lib.quantities import reference_sheet
from spaceplan.modules.household.lib.program_review import review_program
from spaceplan.modules.profiles.lib.program_profiles import (
    floor_feasibility,
    profile_programs,
    public,
)

PROFILE_ORDER = ("minimum", "optimum", "maximum", "accessible", "staged")


def lot_limits(package: dict, catalog) -> dict:
    cap = package["capacity"]
    far = cap["gross_area_max"]["value"]
    realizable = max(r["area"]["value"] for r in package["realizable_capacity"])
    footprint_max = (cap.get("footprint_max_normative") or {}).get("value")
    one_floor = min(realizable, footprint_max) if footprint_max else realizable
    stair = catalog.space_type(catalog.data["cost_index"]["estimates"]["stair_space_type"])["area"]["target"]
    return {"far_sqft": far, "one_floor_max_sqft": one_floor, "stair_sqft": 2 * stair,
            "envelope_sqft": cap["envelope"]["area"]["value"]}


def profile_review(catalog, program: dict) -> dict:
    r = review_program(catalog, load_ruleset_resource(*CRC_RULESET), program)
    return {"buildable_as_stated": r["buildable_as_stated"], "counts": r["counts"],
            "findings": [f for f in r["findings"] if f["severity"] != "info"]}


def portfolio_model(catalog, budget: dict | None, cost_model: str | None) -> tuple[str, object]:
    """(cost model name, cost model): explicit model, else the budget's, else the catalog default."""
    ci = catalog.data["cost_index"]
    model_name = cost_model or (budget or {}).get("cost_model") or ci["default_model"]
    return model_name, get_cost_model(model_name)


@dataclass
class PortfolioReading:
    """Reading of the relative index: the lot (with its ceilings and budget) or the reference dwelling."""

    reading: str
    reference: object
    limits: dict | None
    resolved_budget: dict | None
    fraction: float | None


def portfolio_reading(catalog, package: dict | None, budget: dict | None) -> PortfolioReading:
    """Lot reading when a capacity package is given, otherwise the reference dwelling (no ceiling)."""
    ci = catalog.data["cost_index"]
    limits = None
    if package is not None:
        limits = lot_limits(package, catalog)
        reference = reference_sheet(catalog, limits["far_sqft"], "lot_normative_max")
        reading = "lot"
    else:
        reference = reference_sheet(catalog, ci["reference_dwelling_gross_sqft"], "reference_dwelling")
        reading = "reference_dwelling"
    resolved_budget = resolve_budget(ci, budget) if package is not None else None
    fraction = None if resolved_budget is None else resolved_budget["fraction_of_max"]
    return PortfolioReading(reading, reference, limits, resolved_budget, fraction)


def assess_profiles(stages: dict, catalog, model, rd: PortfolioReading, package: dict | None,
                    mean_slope: float | None) -> tuple[dict, dict]:
    """Expansion curve and profiles with their area feasibility and program review."""
    limits = rd.limits
    exp, profiles = profile_programs(
        stages, catalog, model, rd.reference,
        far_sqft=limits["far_sqft"] if limits else None, budget_fraction=rd.fraction,
        strategy=package["meta"]["realization_strategy"] if package else None,
        mean_slope=mean_slope)

    for name in ("minimum", "optimum", "maximum", "accessible"):
        p = profiles[name]
        p["feasibility"] = floor_feasibility(p["gross_area_sqft"], limits and limits["far_sqft"],
                                             limits and limits["one_floor_max_sqft"], limits["stair_sqft"] if limits
                                             else 0.0)
        p["review"] = profile_review(catalog, p["program"])
    for part in ("today", "final"):
        p = profiles["staged"][part]
        p["feasibility"] = floor_feasibility(p["gross_area_sqft"], limits and limits["far_sqft"],
                                             limits and limits["one_floor_max_sqft"], limits["stair_sqft"] if limits
                                             else 0.0)
    return exp, profiles


def program_key(program: dict) -> str:
    """Identity of a program for zoning (profiles with the same spaces zone the same)."""
    return repr(sorted((s["space_id"], s["target_area_sqft"], s["floor_preference"]) for s in program["spaces"]))


def zoning_summary(option: dict) -> dict:
    """Summary of the one-floor zoning option of a profile."""
    status_key = "zoned" if option["status"] == "zoned" else "not_zoned"
    return {"status": option["status"], "status_key": status_key, "valid": option.get("valid"),
            "space_level_valid": (option.get("space_level") or {}).get("valid"),
            "best_score": option["schemes"][0]["scores"]["total"] if option.get("schemes") else None}


def review_sheet_header(brief: dict, name: str, stages: dict, option: dict, p: dict, limits: dict, model_name: str,
                        words: dict, lang: str) -> list[str]:
    """Header lines of the review sheet of a zoned profile."""
    s = option["schemes"][0]["scores"]
    return [
        f"{words['title']} — {words['profiles'][name]} · {brief['meta']['brief_id']}",
        household_line(stages, lang),
        f"{option['valid']} zon. válidas · puntaje {s['total']:.2f} (rel. {s['relations']:.2f}, "
        f"orient. {s['orientation']:.2f}, forma {s['shape']:.2f})" if lang == "es" else
        f"{option['valid']} valid zonings · score {s['total']:.2f}",
        f"Bruta {p['gross_area_sqft']:.0f} ft² · FAR {limits['far_sqft']:.0f} ft² · índice {p['index']:.3f} "
        f"({model_name}) · calidad {p['quality']:.2f}" if lang == "es" else
        f"Gross {p['gross_area_sqft']:.0f} sq ft · FAR {limits['far_sqft']:.0f} · index {p['index']:.3f}",
    ]


def portfolio_summary(brief: dict, rd: PortfolioReading, model_name: str, catalog, exp: dict, profiles: dict,
                      stages: dict, sheets: list[str]) -> dict:
    """The portfolio returned by the `profiles` command (before the portfolio sheet texts)."""
    ci = catalog.data["cost_index"]
    limits = rd.limits
    return {
        "brief_id": brief.get("meta", {}).get("brief_id"),
        "reading": rd.reading,
        "model": model_name,
        "legend": ci["legend"],
        "ceilings": {"far_sqft": limits and limits["far_sqft"], "one_floor_max_sqft": limits and
                     limits["one_floor_max_sqft"], "budget_fraction": rd.fraction, "budget": rd.resolved_budget,
                     "governing": exp["maximum"]["governing"]},
        "household": {"archetype_id": stages["household"].archetype_id,
                      "kitchen_typology": stages["now"]["derivation"].kitchen_typology,
                      "culture_applied": any(t["layer"] == "culture" for t in stages["now"]["derivation"].trace)},
        "quality_note": stages["hcat"].data["program_quality"]["note"],
        "curve": exp["curve"],
        "profiles": {k: public(profiles[k]) for k in PROFILE_ORDER},
        "sheets": sheets,
    }


def portfolio_sheet_texts(portfolio: dict, brief: dict, stages: dict, exp: dict, profiles: dict, words: dict,
                          lang: str) -> None:
    """Title, subtitle, staged lines and notes of the portfolio sheet (in place)."""
    st = profiles["staged"]
    portfolio["title"] = brief.get("meta", {}).get("brief_id") or "household"
    portfolio["subtitle"] = household_line(stages, lang) + f" · {words['governing'][exp['maximum']['governing']]}"
    portfolio["staged_lines"] = (
        [f"Hoy: índice {st['index_today']:.3f} · después: {st['index_later']:.3f} · total {st['index_total']:.3f}",
         f"Construir el final de una vez: {st['index_build_final_now']:.3f} · prima por etapas "
         f"{st['staging_premium']:+.3f}",
         f"Ampliación {st['expansion_gross_sqft']:.0f} ft²; convertibles hoy: {', '.join(st['convertible_now']) or '-'}"]
        if lang == "es" else
        [f"Today {st['index_today']:.3f} · later {st['index_later']:.3f} · total {st['index_total']:.3f}",
         f"Build final now {st['index_build_final_now']:.3f} · staging premium {st['staging_premium']:+.3f}"])
    portfolio["notes"] = [words["cost_legend"]]


def household_line(stages: dict, lang: str) -> str:
    h = stages["household"]
    d = stages["now"]["derivation"]
    culture = h.cultural_profile or ("aspectos propios" if h.culture_aspects else "sin perfil")
    if lang != "es":
        culture = h.cultural_profile or ("own aspects" if h.culture_aspects else "no profile")
        return f"Household {h.archetype_id or 'custom'} · {len(h.members)} members · culture {culture} · kitchen {d.kitchen_typology}"
    return (f"Hogar {h.archetype_id or 'propio'} · {len(h.members)} personas · perfil cultural {culture} · "
            f"cocina {d.kitchen_typology}")


__all__ = ["PROFILE_ORDER", "TIERS", "PortfolioReading", "assess_profiles", "household_line", "lot_limits",
           "portfolio_model", "portfolio_reading", "portfolio_sheet_texts", "portfolio_summary", "profile_programs",
           "profile_review", "program_key", "review_sheet_header", "zoning_summary"]
