"""Workflow of the multivariable minimal correction (step 6).

Triggered when the one-floor option of a house does not zone. Candidate combinations of strategy,
garage layout and front recess come ordered by cost (lib/corrections.py); each one is first tested
for frontage (cheap), then the site partition is rebuilt (cheap) and finally the one-floor option is
zoned (expensive). The first combination that zones is the minimal correction. The search then
keeps going for a few more runs (catalog `pareto_extra_runs`) and reports the Pareto frontier of
cost (lower is better) against design quality (best scheme score, higher is better): a costlier
correction is only worth showing if it buys a better house. The number of full runs is capped.
"""

from __future__ import annotations

import copy

from spaceplan.lib.corrections import (
    candidate_combos,
    driveway_width,
    frontage_demand,
    frontage_supply,
    garage_program,
    garage_zone_min_width,
)
from spaceplan.lib.realization import get_strategy
from spaceplan.lib.site_partition import build_site_partition
from spaceplan.lib.zoning import frontage_diagnostics, zone_site_options

ONE_FLOOR = "n1"


def _option(container: dict, option_id: str) -> dict | None:
    return next((o for o in container["options"] if o["option_id"] == option_id), None)


def needs_correction(site: dict, zoning: dict) -> str | None:
    """Why the one-floor option needs a correction (None when it zones)."""
    z = _option(zoning, ONE_FLOOR)
    if z is None:
        return None
    if z["status"] == "zoned":
        return None
    if z["status"] == "not_feasible":
        return f"site: {z.get('reason') or 'not feasible'}"
    return f"zoning: {z['status']}"


def search_corrections(brief: dict, rs, catalog, lot, boundaries, evaluation, capacity, profile, rect_width,
                       baseline_strategy: str, site: dict, zoning: dict) -> dict | None:
    trigger = needs_correction(site, zoning)
    if trigger is None:
        return None
    cfg = catalog.data["corrections"]
    site_n1 = _option(site, ONE_FLOOR)
    area = site_n1["footprint_area_sqft"]
    dw = driveway_width(catalog, brief["program"])
    diagnostics = {"strict": frontage_diagnostics(catalog, brief, area, False, dw),
                   "relaxed": frontage_diagnostics(catalog, brief, area, True, dw)}
    # the entry deck sits in front of the footprint: a recess of its depth takes it out of the front yard
    deck = (site_n1.get("access") or {}).get("deck_depth_ft")
    extra = (deck,) if deck else ()
    combos = candidate_combos(catalog, brief["program"], profile, diagnostics, (baseline_strategy, "as_brief", 0.0),
                              extra)
    evaluated, chosen, runs = [], None, 0
    successes: list[dict] = []
    extra_left = cfg.get("pareto_extra_runs", 0)
    garage_min = garage_zone_min_width(catalog)
    for combo in combos:
        row = {**combo.as_dict(), "outcome": None, "detail": None}
        evaluated.append(row)
        program = garage_program(catalog, brief["program"], combo.garage)
        kind = "strict" if combo.strategy == "A_inscribed_rectangle" else "relaxed"
        demand = frontage_demand(diagnostics[kind], driveway_width(catalog, program), garage_min)
        supply = frontage_supply(combo.strategy, combo.recess_ft, profile, rect_width)
        if demand is not None and supply < demand - 1e-6:
            row.update(outcome="pruned_frontage", detail=f"front {supply:.1f} ft < demand {demand:.1f} ft")
            continue
        if runs >= cfg["max_evaluations"] or (chosen is not None and extra_left <= 0):
            row.update(outcome="not_evaluated", detail="evaluation budget reached")
            continue
        if chosen is not None:
            extra_left -= 1
        runs += 1
        trial = copy.deepcopy(brief)
        trial["program"] = program
        trial_site, _ = build_site_partition(rs, catalog, trial, lot, boundaries, evaluation, capacity,
                                             combo.strategy, combo.recess_ft)
        site_opt = _option(trial_site, ONE_FLOOR)
        if site_opt is None or not site_opt.get("feasible"):
            reasons = (site_opt or {}).get("reasons") or [c["check_id"] for c in (site_opt or {}).get("checks", [])
                                                         if c["kind"] == "normative" and not c["passes"]]
            row.update(outcome="site_not_feasible", detail="; ".join(reasons) or "site option not compliant")
            continue
        trial_zoning = zone_site_options(catalog, trial, boundaries.frame, trial_site, get_strategy(combo.strategy),
                                         profile, options=(ONE_FLOOR,), retry=False)
        z = _option(trial_zoning, ONE_FLOOR)
        if z["status"] != "zoned":
            row.update(outcome=z["status"], detail=z.get("reason"))
            continue
        best = z["schemes"][0]
        row.update(outcome="zoned", detail=f"{len(z['schemes'])} scheme(s); best {best['topology']['key']}")
        successes.append(quality_row(combo, best))
        if chosen is None:
            chosen = {"combo": combo.as_dict(), "site_option": site_opt, "zoning_option": z,
                      "program_garage": next((s for s in program["spaces"] if s["zone"] == "garage"), None)}
    return {
        "triggered_by": trigger,
        "baseline": {"strategy": baseline_strategy, "garage_layout": "as_brief", "front_recess_ft": 0.0},
        "candidates": len(combos),
        "full_runs": runs,
        "evaluated": evaluated,
        "applied": chosen,
        "pareto": pareto_frontier(successes),
        "status": "corrected" if chosen else "no_correction_found",
        "cost_model_source": cfg["source"],
    }


def quality_row(combo, scheme: dict) -> dict:
    """Design quality of the best scheme a correction produced (inputs to the Pareto frontier)."""
    circ = scheme.get("circulation", {}).get("fraction")
    real = scheme.get("realization", {})
    return {**combo.as_dict(), "score": scheme["scores"]["total"], "circulation_fraction": circ,
            "envelope_use": real.get("envelope_use"), "topology": scheme["topology"]["key"]}


def pareto_frontier(rows: list[dict]) -> list[dict]:
    """Mark the rows not dominated in (cost: lower, score: higher); frontier rows first, by cost."""
    out = []
    for r in rows:
        dominated = any((o["cost"] <= r["cost"] and o["score"] >= r["score"])
                        and (o["cost"] < r["cost"] or o["score"] > r["score"]) for o in rows)
        out.append({**r, "on_frontier": not dominated})
    out.sort(key=lambda r: (not r["on_frontier"], r["cost"], -r["score"]))
    return out


__all__ = ["needs_correction", "pareto_frontier", "quality_row", "search_corrections"]
