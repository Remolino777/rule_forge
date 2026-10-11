"""Stage S1.2 of one cell (step 6.7a): the stair from the main door, as candidates in S1 and as a decision in S2.

Client decision 2026-10-10 (option B): the joint selector of S1.1 and the S2 backtrack are gone; the stair is placed
from the main door against the permitted walls (strategies A, D, C, B as the last resort).

  S1  for every upper-floor placement: the door, the permitted walls, the candidates of each strategy (two-level
      search, discards, natural light); a global preselection per strategy (the half bath looked for afterwards);
      the cell is drawn with the best candidate by a proxy (strategy preference, light, occupied area, distance to
      the vestibule), flagged provisional;
  S2  every preselected candidate is drawn and zoned; the choice in three levels (access_rank) picks the stair; the
      contract keeps the reason, the Pareto front and the best candidate of each strategy (portfolio).
Only reads contracts (area matrix, lot capacity, site plan) and the catalogs.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from spaceplan.modules.stacking.lib.access_core import (
    EntryDoor,
    entry_door,
    permitted_walls,
    site_entry,
)
from spaceplan.modules.stacking.lib.access_rank import rank_stair_candidates
from spaceplan.modules.stacking.lib.access_stair import (
    AccessCandidate,
    access_candidates,
    preselect,
    with_half_bath,
)
from spaceplan.modules.stacking.lib.cell_geometry import DRAWN, S1Context, draw_cell
from spaceplan.modules.stacking.lib.stair import StairShape, stair_shape
from spaceplan.modules.stacking.lib.stair_access import u_min_span_ft
from spaceplan.modules.stacking.lib.zone_cell import ZONED, S2Context, zone_cell
from spaceplan.modules.stacking.lib_aux.plan_geometry import polygon_json

LIGHT_RULE, STRATEGY_RULE = "K06-STAIR-NATURAL-LIGHT", "K07-STAIR-STRATEGY"


@dataclass(frozen=True)
class AccessContext:
    """Catalog and rule values of stage S1.2 shared by every cell."""

    acc: dict[str, Any]
    shapes: dict[str, StairShape]
    required: dict[str, bool]
    preference: list[str]
    tolerance_ft: float
    top_k: int


def access_context(scat, limits, client_rs) -> AccessContext:
    acc = scat.access_core
    design = {**scat.stair_design, "u_well_gap_ft": acc["void"]["well_ft"], "u_min_span_ft": u_min_span_ft(client_rs)}
    ftf = scat.levels["floor_to_floor_ft"]
    shapes = {t["stair_id"]: stair_shape(t, ftf, limits, design) for t in scat.data["stair"]["types"]}
    return AccessContext(acc, shapes, client_rs.params(LIGHT_RULE)["required_by_strategy"],
                         list(client_rs.params(STRATEGY_RULE)["preference"]),
                         float(acc["comparison"]["route_tolerance_ft"]), int(acc["comparison"]["top_k_per_strategy"]))


@dataclass
class CellPool:
    """Candidates of one cell gathered in S1 (kept in memory for S2; summarized in the contract)."""

    door: EntryDoor | None = None
    picks: list[tuple[str, AccessCandidate]] = field(default_factory=list)   # (upper placement, candidate)
    stats: Counter = field(default_factory=Counter)
    site: dict[str, Any] = field(default_factory=dict)


def _proxy_key(actx: AccessContext, a: AccessCandidate) -> tuple:
    rank = actx.preference.index(a.strategy) if a.strategy in actx.preference else len(actx.preference)
    return (rank, 0 if a.light.source != "none" else 1, round(a.occupied_sqft), round(a.entry_ft, 1), a.cand.key)


def _access_block(plan, door: EntryDoor, a: AccessCandidate, placement: str, provisional: bool) -> dict[str, Any]:
    return {"provisional": provisional, "fixed": True, "placement": placement, **a.summary(),
            "half_bath_fit": a.cand.half_bath is not None,
            "door": polygon_json(plan.to_world(door.segment.buffer(0.25, cap_style="flat"))),
            "swing": polygon_json(plan.to_world(door.swing)),
            "vestibule": polygon_json(plan.to_world(door.vestibule)),
            "void": polygon_json(plan.to_world(a.well)) if a.well is not None else None}


def draw_with(cell, s0, plan, strategy, ctx: S1Context, pool: CellPool, placement: str, a: AccessCandidate,
              provisional: bool) -> dict[str, Any]:
    """The S1 block of a cell drawn with one access candidate."""
    s1 = draw_cell(cell, s0, plan, strategy, ctx, placements=[placement], garage_side=pool.site.get("garage_side"),
                   picker=lambda *_: ([a.cand], a.cand))
    if s1["status"] == DRAWN:
        s1["access_core"] = _access_block(plan, pool.door, a, placement, provisional)
    return s1


def stage_s1(cell, s0, plan, strategy, ctx: S1Context, actx: AccessContext, site_plan: dict | None,
             lot_local) -> tuple[dict[str, Any], CellPool]:
    """S1 of a cell: candidates of every placement and strategy, preselection, provisional drawing."""
    pool = CellPool(site=site_entry(site_plan) if site_plan else {"garage_side": None, "deck_offset_ft": None})
    found: list[tuple[str, AccessCandidate]] = []
    ground_ref: dict[str, Any] = {}

    def collect(placement, upper_cand, ground, garage, cfg):
        door = entry_door(ground, garage, pool.site.get("garage_side"), pool.site.get("deck_offset_ft"), actx.acc)
        if door is None:
            pool.stats["no_door"] += 1
            return [], None
        pool.door = door
        ground_ref.update(ground=ground, garage=garage, cfg=cfg)
        walls = permitted_walls(ground, upper_cand.polygon, garage, lot_local, actx.acc)
        cands, stats = access_candidates(upper_cand.polygon, ground, garage, door, walls, actx.shapes, cfg, actx.acc,
                                         ctx.stair_rs, actx.required)
        pool.stats.update(stats)
        found.extend((placement, a) for a in cands)
        return [a.cand for a in cands], None

    probe = draw_cell(cell, s0, plan, strategy, ctx, garage_side=pool.site.get("garage_side"), picker=collect)
    if not found:
        probe["access_core"] = {"provisional": True, "candidates": [], "discards": dict(pool.stats),
                                "door": None if pool.door is None else polygon_json(plan.to_world(pool.door.segment.buffer(0.25, cap_style="flat")))}
        return probe, pool
    placement_of = {id(a): p for p, a in found}
    originals = preselect([a for _, a in found], actx.top_k)
    placements = [placement_of[id(o)] for o in originals]
    chosen = with_half_bath(originals, ground_ref["ground"], ground_ref["garage"], pool.door, ground_ref["cfg"])
    pool.picks = list(zip(placements, chosen))
    best_p, best_a = min(pool.picks, key=lambda pa: _proxy_key(actx, pa[1]))
    s1 = draw_with(cell, s0, plan, strategy, ctx, pool, best_p, best_a, provisional=True)
    if s1["status"] == DRAWN:
        s1["access_core"]["candidates"] = [{"placement": p, **a.summary(), "half_bath_fit": a.cand.half_bath is not None}
                                           for p, a in pool.picks]
        s1["access_core"]["discards"] = dict(pool.stats)
        s1["upper_candidates"] = probe.get("upper_candidates", [])
    return s1, pool


def stage_s2(cell, s0, out: dict[str, Any], plan, strategy, ctx: S1Context, s2ctx: S2Context, actx: AccessContext,
             pool: CellPool, refine=None, max_tries: int | None = None) -> None:
    """S2 of a cell: every preselected candidate drawn and zoned, the choice in three levels, the portfolio.

    With `refine` (stage S2.1: (s1, s2) -> s21 block), the chosen candidate is laid out space by space; when it gets
    no valid layout the next candidate of the ranked list is tried (client decision E1, 2026-10-11), up to
    `max_tries` candidates; the first one laid out becomes the choice."""
    trials = []
    provisional = out["s1"]
    for placement, a in pool.picks:
        same = (provisional.get("access_core") or {}).get("placement") == placement and \
            provisional["stair"]["polygon"] == polygon_json(plan.to_world(a.cand.geom.footprint))
        s1 = provisional if same else draw_with(cell, s0, plan, strategy, ctx, pool, placement, a, provisional=True)
        if s1["status"] != DRAWN:
            continue
        s2 = zone_cell(cell, s1, plan, s2ctx)
        opt = s2["options"].get(s2.get("chosen_option")) if s2["status"] == ZONED else None
        routes = (opt or {}).get("routes") or {}
        trials.append({"s1": s1, "s2": s2, "strategy": a.strategy, "stair_id": a.stair_id, "placement": placement,
                       "route_ft": routes.get("total_ft") if opt else None,
                       "occupied_sqft": a.occupied_sqft, "light": a.light.source,
                       "arrival_kind": (s2.get("upper") or {}).get("arrival_kind"),
                       "half_bath": (opt or {}).get("half_bath") == "under_stair"})
    order = None
    for t in trials:
        order = (t["s2"].get("arrival") or {}).get("order") or order
    ranked = rank_stair_candidates(trials, actx.tolerance_ft, actx.preference, order)

    def summary(t, r=None):
        return {"strategy": t["strategy"], "stair_id": t["stair_id"], "placement": t["placement"],
                "route_ft": t["route_ft"], "occupied_sqft": round(t["occupied_sqft"], 1), "light": t["light"],
                "arrival_kind": t["arrival_kind"], "half_bath": t["half_bath"], "s2_status": t["s2"]["status"],
                **({"pareto": r.pareto, "near_best": r.near_best, "reason": r.reason} if r else {})}

    portfolio = {}
    for r in ranked:
        portfolio.setdefault(r.trial["strategy"], summary(r.trial, r))
    choice = {"tolerance_ft": actx.tolerance_ft, "strategy_preference": actx.preference,
              "candidates": len(trials), "zoned": len(ranked), "portfolio": portfolio, "arrival_order": order,
              "ranked": [summary(r.trial, r) for r in ranked],          # every zoned candidate, in choice order
              "pareto": [summary(r.trial, r) for r in ranked if r.pareto],
              "not_zoned": [summary(t) for t in trials if t["route_ft"] is None]}
    pick, s21 = 0, None
    if ranked and refine is not None:
        tries = ranked[: max_tries or len(ranked)]
        attempts = []
        for k, r in enumerate(tries):
            block = refine(r.trial["s1"], r.trial["s2"])
            attempts.append({"rank": k, "strategy": r.trial["strategy"], "stair_id": r.trial["stair_id"],
                             "status": block["status"], "first_violation": block.get("first_violation")})
            if s21 is None or block["status"] == "spaced":
                pick, s21 = k, block
            if block["status"] == "spaced":
                break
        s21["stair_rank"] = pick
        s21["attempts"] = attempts
    if ranked:
        best = ranked[pick].trial
        reason = ranked[pick].reason if pick == 0 else f"S2.1 fallback to rank {pick}: {ranked[pick].reason}"
        choice.update({"chosen": summary(best, ranked[pick]), "reason": reason})
        best["s1"]["access_core"]["provisional"] = False
        for k in ("candidates", "discards"):                      # what S1 handed over stays with the chosen drawing
            if k in (provisional.get("access_core") or {}):
                best["s1"]["access_core"][k] = provisional["access_core"][k]
        if "upper_candidates" in provisional:
            best["s1"]["upper_candidates"] = provisional["upper_candidates"]
        out["s1"], s2 = best["s1"], best["s2"]
    else:
        choice.update({"chosen": None, "reason": "no candidate zoned" if trials else "no candidate drawn"})
        s2 = trials[0]["s2"] if trials else zone_cell(cell, provisional, plan, s2ctx)
    for t in trials:                                     # S2.1 alternatives live in memory only
        t["s2"].pop("_alternatives", None)
    s2.pop("_alternatives", None)
    s2["stair_choice"] = choice
    out["s2"] = s2
    out["next_stage"] = s2["next_stage"]
    if s21 is not None:
        out["s21"] = s21
        out["next_stage"] = None


__all__ = ["AccessContext", "CellPool", "access_context", "draw_with", "stage_s1", "stage_s2"]
