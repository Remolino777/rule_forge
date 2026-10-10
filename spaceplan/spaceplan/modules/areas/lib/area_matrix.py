"""Area matrix of one lot (step 6.6): program profile x vertical scheme x strategy, per household.

For each household (archetype + cultural profile) the five program profiles of step 6.5d (minimum,
optimum, maximum, accessible, staged final) are split over floors by every applicable vertical scheme
(lib.vertical_split), evaluated on the lot (lib.area_budget: indices, strategies, frontage, measured
site) and scored with the household-weighted metrics. A cell is one (profile, scheme); its strategy is
the simplest one that holds it, and the per-strategy verdicts are kept.

Open area = lot - ground footprint - paving - deck (the complement of the occupancy index, net of
access); it is monotone in the footprint, unlike the rear garden the site layer reports.

Outputs per household and profile: the best scheme, the runner-up and the metric that decides between
them. Per household: the Pareto front over open area (max), relative cost index (min) and program quality (max).
Scores are a provisional indicator until the common quality score of step 6.8.
"""

from __future__ import annotations

from typing import Any

from spaceplan.core.lib.catalog import Catalog
from spaceplan.core.lib.rules import RuleSet
from spaceplan.core.lib_aux.pareto import pareto_front
from spaceplan.modules.areas.lib.area_budget import (
    FITS,
    FITS_SMALL_GARDEN,
    LotBudget,
    SiteMeasurer,
    evaluate_split,
)
from spaceplan.modules.areas.lib.floor_balance import balance_split, balanced
from spaceplan.modules.areas.lib.vertical_split import (
    applicable_schemes,
    dedupe_splits,
    has_empty_upper,
    metric_weights,
    program_group_facts,
    split_program,
    vertical_metrics,
    weighted_score,
)
from spaceplan.modules.cost.lib.cost_models import CostModel, mode_point, relative_index
from spaceplan.modules.cost.lib.quantities import QuantitySheet, build_sheet

FEASIBLE = (FITS, FITS_SMALL_GARDEN)


def profile_program(profiles: dict, name: str) -> dict:
    if name == "staged_final":
        return profiles["staged"]["final"]
    return profiles[name]


def _clip(x: float) -> float:
    return max(0.0, min(1.0, x))


def lot_metrics(catalog: Catalog, budget: LotBudget, ev: dict, index: float) -> dict[str, float]:
    sc = catalog.data["vertical_schemes"]["scoring"]
    fr = catalog.data["area_analysis"]["frontage"]
    return {
        "open_area": _clip(ev["open_area_sqft"] / (sc["open_area_reference_fraction_of_lot"] * budget.lot_area_sqft)),
        "frontage": _clip(0.5 + ev["frontage_margin_ft"] / (2 * fr["margin_scale_ft"])),
        "cost": _clip(1.0 - index),
    }


def household_cells(
    catalog: Catalog,
    rs: RuleSet,
    budget: LotBudget,
    measurer: SiteMeasurer | None,
    household_id: str,
    stages: dict,
    profiles: dict,
    model: CostModel,
    reference: QuantitySheet,
    mean_slope: float | None = None,
    profiles_two_floors: dict | None = None,
    forced_schemes: tuple[str, ...] = (),
    floors_policy: str | None = None,
) -> list[dict[str, Any]]:
    """Every (profile, scheme) cell of one household on one lot.

    profiles_two_floors: the profiles recomputed with the FAR ceiling net of the stair repeated on two
    floors; the maximum of a two-floor scheme comes from it (otherwise the one-floor maximum plus the
    stair would always exceed the construction index)."""
    aa = catalog.data["area_analysis"]
    vs = catalog.data["vertical_schemes"]
    ci = catalog.data["cost_index"]
    point = mode_point(model, ci)
    strategy_name = {s["strategy_id"]: s["strategy"] for s in aa["strategies"]}
    facts_now = stages["now"]["derivation"].facts
    facts_later = stages["later"]["derivation"].facts
    cells = []
    for prof in aa["profiles"]:
        p1 = profile_program(profiles, prof)
        p2 = profile_program(profiles_two_floors, prof) if profiles_two_floors and prof == "maximum" else p1
        gfacts = program_group_facts(vs, p1["program"])
        facts = {**facts_now, **gfacts, **budget.lot_facts}
        later = {**facts_later, **gfacts, **budget.lot_facts}
        weights, fired = metric_weights(catalog, facts, later)
        splits, source = [], {}
        applicable = applicable_schemes(vs, facts)
        forced = [s for s in vs["schemes"] if s["scheme_id"] in forced_schemes and s not in applicable]
        for scheme in applicable + forced:
            pp = p2 if scheme["floors"] > 1 else p1
            g2 = program_group_facts(vs, pp["program"])
            if scheme in applicable and scheme["floors"] > 1 and pp is not p1 and not applicable_schemes(
                    vs, {**facts_now, **g2, **budget.lot_facts}).count(scheme):
                continue
            sp = balance_split(catalog, pp["program"], split_program(catalog, pp["program"], scheme, facts),
                               budget.footprint_design_sqft)
            splits.append(sp)
            source[sp.scheme_id] = pp
        forced_ids = {s["scheme_id"] for s in forced}
        degenerate = [sp.scheme_id for sp in splits if has_empty_upper(catalog, sp) and sp.scheme_id not in forced_ids]
        splits = [sp for sp in splits if sp.scheme_id not in degenerate]
        kept, equivalent = dedupe_splits(splits)
        for sp in kept:
            p = source[sp.scheme_id]
            program = p["program"]
            ev = evaluate_split(catalog, rs, budget, program, sp, measurer)
            used = ev["strategy_used"] or budget.strategies[0].strategy_id
            sheet = build_sheet(catalog, program, prof, floors=sp.floors, strategy=strategy_name[used],
                                mean_slope=mean_slope, floor_shares=sp.shares if sp.floors > 1 else None)
            index = relative_index(model, sheet, reference, ci, point)
            metrics = {**vertical_metrics(catalog, sp, program, facts), **lot_metrics(catalog, budget, ev, index)}
            feasible = ev["status"] in FEASIBLE
            score, parts = weighted_score(weights, metrics)
            ic, io = ev["indices"]["indices"]["IC"], ev["indices"]["indices"]["IO"]
            cells.append({
                "lot_id": budget.lot_id,
                "household_id": household_id,
                "archetype_id": stages["household"].archetype_id,
                "culture": stages["household"].cultural_profile or "none",
                "profile": prof,
                "program_quality": p.get("quality"),
                "scheme_id": sp.scheme_id,
                "equivalent_schemes": sorted(k for k, v in equivalent.items() if v == sp.scheme_id),
                "forced": sp.scheme_id in forced_ids,
                "floors": sp.floors,
                "gross_sqft": round(sp.gross, 1),
                "ground_sqft": round(sp.ground, 1),
                "upper_sqft": round(sp.upper, 1),
                "split": sp.to_dict(),
                "balanced_up": balanced(sp),
                "maximum_trim": p.get("trim") if prof == "maximum" else None,
                "IC": ic["value"], "IC_max": ic["limit"], "IO": io["value"], "IO_max": io["limit"],
                "IC_by_floor": ev["indices"]["by_floor"],
                "IC_alternatives": ev["indices"]["alternatives"],
                "variant_sensitive": ev["indices"]["variant_sensitive"],
                "status": ev["status"],
                "governing": ev["governing"],
                "strategy_used": ev["strategy_used"],
                "strategies_ok": ev["strategies_ok"],
                "strategies": ev["strategies"],
                "frontage": ev["frontage"],
                "garden_sqft": ev["garden_sqft"],
                "open_area_sqft": ev["open_area_sqft"],
                "open_area_ratio": round(ev["open_area_sqft"] / budget.lot_area_sqft, 4),
                "index": round(index, 4),
                "metrics": {k: round(v, 4) for k, v in metrics.items()},
                "weights": {k: round(v, 3) for k, v in weights.items()},
                "weight_rules": fired,
                "score": round(score, 4) if feasible else None,
                "score_parts": {k: round(v, 4) for k, v in parts.items()},
                "degenerate_schemes": degenerate,
            })
    rank_schemes(cells, floors_policy)
    return cells


ONE_FLOOR_FIRST = "one_floor_first"


def rank_schemes(cells: list[dict], floors_policy: str | None = None) -> None:
    """Rank feasible schemes inside each (household, profile); name the metric that decides #1 vs #2.

    floors_policy "one_floor_first" (client rule D03): when a one-floor scheme is feasible, two-floor schemes are
    kept (scored) but not ranked - the second floor exists only when the program does not fit on one floor."""
    groups: dict[tuple, list[dict]] = {}
    for c in cells:
        groups.setdefault((c["lot_id"], c["household_id"], c["profile"]), []).append(c)
    for group in groups.values():
        one_floor_ok = any(c["floors"] == 1 and c["score"] is not None for c in group)
        for c in group:
            c["policy_excluded"] = (floors_policy == ONE_FLOOR_FIRST and one_floor_ok and c["floors"] > 1
                                    and c["score"] is not None)
        ok = sorted((c for c in group if c["score"] is not None and not c["policy_excluded"]),
                    key=lambda c: -c["score"])
        for i, c in enumerate(ok):
            c["rank"] = i + 1
        for c in group:
            c.setdefault("rank", None)
            c["best"] = bool(ok) and c is ok[0]
        if len(ok) >= 2:
            a, b = ok[0], ok[1]
            diff = {k: a["score_parts"][k] - b["score_parts"][k] for k in a["score_parts"]}
            ok[0]["decisive_metric"] = max(diff, key=diff.get)
            ok[0]["runner_up"] = b["scheme_id"]
            ok[0]["margin"] = round(a["score"] - b["score"], 4)
        elif ok:
            ok[0]["decisive_metric"] = "only_feasible"
            ok[0]["runner_up"] = None
            ok[0]["margin"] = None


def pareto_cells(cells: list[dict]) -> list[dict]:
    """Non-dominated feasible cells over open area (max), index (min), program quality (max)."""
    ok = [c for c in cells if c["score"] is not None]
    return pareto_front(ok, key=lambda c: (c["open_area_sqft"], c["index"], c["program_quality"] or 0.0),
                        senses=("max", "min", "max"))


def compact(cell: dict) -> dict:
    """Row for tables (no nested per-strategy detail)."""
    keep = ("lot_id", "household_id", "profile", "scheme_id", "floors", "gross_sqft", "ground_sqft", "upper_sqft",
            "IC", "IC_max", "IO", "IO_max", "status", "governing", "strategy_used", "garden_sqft", "open_area_sqft",
            "index",
            "score", "rank", "best", "decisive_metric", "runner_up")
    row = {k: cell.get(k) for k in keep}
    row["IC_garage_excluded"] = (cell["IC_alternatives"].get("garage_excluded") or {}).get("IC")
    row["variant_sensitive"] = ",".join(cell["variant_sensitive"])
    row["equivalent_schemes"] = ",".join(cell["equivalent_schemes"])
    row["balanced_up"] = ",".join(cell.get("balanced_up") or [])  # step 9a
    trim = cell.get("maximum_trim")
    row["maximum_trimmed"] = bool(trim and trim.get("fits"))
    return row


__all__ = ["FEASIBLE", "ONE_FLOOR_FIRST", "compact", "household_cells", "lot_metrics", "pareto_cells", "profile_program",
           "rank_schemes"]
