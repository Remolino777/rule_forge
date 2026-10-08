"""Area budget of a lot and of one floor split on it (step 6.6, stages E0 and E1).

E0 (arithmetic): construction and occupancy indices under every gross-floor-area variant, ground floor
against the realizable footprint of each strategy, containment of the upper floor, street frontage the
ground floor needs (garage lanes and entry hard; living-room street anchor soft).

E1 (measured, a few ms): access, front paving and garden of the ground footprint with each strategy that
holds it, through the site layer (lib.site_partition.measure_footprint), cached by footprint.

Statuses, in the order used to name the governing constraint:
    exceeds_far > exceeds_coverage > upper_exceeds_ground > exceeds_strategy > frontage_short > site_fails
    otherwise fits, or fits_small_garden below the indicative garden threshold.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from spaceplan.core.lib.catalog import Catalog
from spaceplan.core.lib.enums import Strategy
from spaceplan.core.lib.rules import RuleSet
from spaceplan.modules.areas.lib.building_indices import IndexLimits, indices_all_variants
from spaceplan.modules.areas.lib.vertical_split import FloorSplit
from spaceplan.modules.site.lib.site_partition import measure_footprint, site_context

STATUS_ORDER = ("exceeds_far", "exceeds_coverage", "upper_exceeds_ground", "exceeds_strategy", "frontage_short",
                "site_fails")
FITS, FITS_SMALL_GARDEN = "fits", "fits_small_garden"
TOL = 1e-6


@dataclass(frozen=True)
class StrategyCapacity:
    strategy_id: str
    strategy: str
    steps: int | None
    area_sqft: float
    front_width_ft: float


@dataclass
class LotBudget:
    lot_id: str
    lot_area_sqft: float
    limits: IndexLimits
    footprint_normative_sqft: float
    envelope_sqft: float
    strategies: list[StrategyCapacity]
    strategies_equal: bool
    garden_min_sqft: float
    front_yard_sqft: float
    extra_paving_sqft: float = 0.0
    notes: list[str] = field(default_factory=list)
    flag: dict | None = None
    far_alternatives: dict = field(default_factory=dict)
    lot_facts: dict = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "lot_id": self.lot_id,
            "lot_area_sqft": round(self.lot_area_sqft, 1),
            "far_gross_max_sqft": round(self.limits.gross_area_max_sqft, 1),
            "ic_max": round(self.limits.limit_ratio("gross_area_max"), 4),
            "io_max": self.limits.coverage_max,
            "footprint_normative_sqft": round(self.footprint_normative_sqft, 1),
            "envelope_sqft": round(self.envelope_sqft, 1),
            "strategies": [{"strategy_id": s.strategy_id, "strategy": s.strategy, "steps": s.steps,
                            "area_sqft": round(s.area_sqft, 1), "front_width_ft": round(s.front_width_ft, 2)}
                           for s in self.strategies],
            "strategies_equal": self.strategies_equal,
            "garden_min_sqft": round(self.garden_min_sqft, 1),
            "front_yard_sqft": round(self.front_yard_sqft, 1),
            "extra_paving_sqft": round(self.extra_paving_sqft, 1),
            "flag": self.flag,
            "far_alternatives": self.far_alternatives,
            "lot_facts": self.lot_facts,
            "notes": self.notes,
        }


def _front_width_b(profile) -> float:
    xl, xr = profile.interval(profile.ymin)
    return xr - xl


def lot_budget(catalog: Catalog, rs: RuleSet, brief: dict, setup, flag: dict | None = None) -> LotBudget:
    """Lot-level limits from the layer-0 objects (`setup` is modules.lotcap.main.run_lotcap.LotSetup)."""
    aa = catalog.data["area_analysis"]
    cap = setup.capacity.capacity
    lot_area = setup.lot.polygon.area
    coverage = cap["coverage_max"].value
    limits = IndexLimits(lot_area, cap["gross_area_max"].value, coverage)
    realizable = setup.capacity.realizable
    strategies = []
    for spec in aa["strategies"]:
        entry = next((r for r in realizable if r["strategy"] == spec["strategy"]
                      and (spec["steps"] is None or r.get("steps") == spec["steps"])), None)
        if entry is None:
            continue
        if spec["strategy"] == Strategy.A_INSCRIBED_RECTANGLE.value:
            front = entry["width_ft"] or 0.0
        elif setup.profile is not None:
            front = _front_width_b(setup.profile)
        else:
            continue
        strategies.append(StrategyCapacity(spec["strategy_id"], spec["strategy"], spec["steps"],
                                           entry["area"].value, front))
    tol = aa["strategy_equal_tolerance_sqft"]
    equal = all(abs(s.area_sqft - strategies[0].area_sqft) <= tol for s in strategies)
    notes = []
    if equal:
        notes.append("all strategies hold the same footprint: the strategy dimension collapses to A")
    if coverage is not None:
        notes.append(f"occupancy index limited to {coverage:.0%} (hillside, 131.0445(a))")
    terrain = brief.get("terrain", {})
    lot_facts = {"steep_hillside_fraction": terrain.get("steep_hillside_fraction", 0.0),
                 "view_side": terrain.get("view_side", "none")}
    extra_paving, far_alt = 0.0, {}
    if flag is not None:
        from spaceplan.modules.lotcap.lib import rule_variants as rv

        extra_paving = flag["access_strip_area_sqft"]
        full = flag["lot_area_sqft"]
        far, base = rv.floor_area_ratio(rs, full, lot_facts["steep_hillside_fraction"])
        far_alt = {"full_lot": {"far": far.value, "gross_max_sqft": round(far.value * base.value, 1),
                                "status": "provisional"}}
        notes.append(f"flag lot (provisional): FAR on the body; full-lot reading would allow "
                     f"{far_alt['full_lot']['gross_max_sqft']:.0f} sq ft")
    return LotBudget(
        lot_id=brief["meta"]["brief_id"], lot_area_sqft=lot_area, limits=limits,
        footprint_normative_sqft=cap["footprint_max_normative"].value,
        envelope_sqft=cap["envelope"]["area"].value, strategies=strategies, strategies_equal=equal,
        garden_min_sqft=aa["garden_min_fraction_of_lot"] * lot_area,
        front_yard_sqft=0.0, extra_paving_sqft=extra_paving, notes=notes, flag=flag,
        far_alternatives=far_alt, lot_facts=lot_facts)


# ---------------------------------------------------------------------------------------- frontage


def _match(match: dict, space: dict) -> bool:
    return all(space.get(k) in v for k, v in match.items())


def frontage_need(catalog: Catalog, program: dict, split: FloorSplit) -> dict[str, float]:
    """Street-facing width the ground floor needs (hard: garage and entry; soft: living anchor)."""
    fr = catalog.data["area_analysis"]["frontage"]
    hard, n = 0.0, 0
    for el in fr["hard_elements"]:
        for s in program["spaces"]:
            if split.floor_of.get(s["space_id"]) == 0 and _match(el["match"], s):
                hard += catalog.space_type(s["space_type"])[el["dimension"]]
                n += 1
    hard += fr["wall_allowance_ft"] * n
    anchor = next(a for a in catalog.data["zoning_profiles"]["house"]["anchors"]
                  if a["anchor_id"] == fr["soft_anchor_id"])
    on_ground = any(s["space_type"] in anchor["space_types"] and split.floor_of.get(s["space_id"]) == 0
                    for s in program["spaces"])
    soft = hard + (anchor["min_contact_ft"] + fr["wall_allowance_ft"] if on_ground else 0.0)
    return {"hard_ft": round(hard, 2), "soft_ft": round(soft, 2), "living_on_ground": on_ground}


# ------------------------------------------------------------------------------------- site (E1)


class SiteMeasurer:
    """Measured site of a ground footprint per strategy, cached (stage E1)."""

    def __init__(self, catalog: Catalog, rs: RuleSet, brief: dict, setup, budget: LotBudget) -> None:
        self.catalog, self.brief, self.budget = catalog, brief, budget
        self.ctx = site_context(rs, catalog, brief, setup.lot, setup.boundaries, setup.evaluation, setup.capacity)
        self.env_status = setup.capacity.capacity["envelope"]["area"].status
        self.budget.front_yard_sqft = self.ctx.front_yard.area
        self.cache: dict[tuple, dict] = {}
        self.calls = 0

    def measure(self, program: dict, strategy: StrategyCapacity, footprint: float, floors: int) -> dict:
        key = (strategy.strategy_id, round(footprint, 1), floors, program.get("garage_cars", 0),
               tuple(sorted(s["space_type"] for s in program["spaces"] if s["zone"] == "garage")))
        if key not in self.cache:
            self.calls += 1
            self.cache[key] = measure_footprint(
                self.ctx, self.catalog, self.brief, program, strategy.strategy, footprint, floors,
                self.budget.footprint_normative_sqft, self.env_status, strategy.steps or 2)
        return self.cache[key]


# ----------------------------------------------------------------------------------- one cell


def evaluate_split(catalog: Catalog, rs: RuleSet, budget: LotBudget, program: dict, split: FloorSplit,
                   measurer: SiteMeasurer | None) -> dict[str, Any]:
    """E0 + E1 of one floor split on one lot: indices, per-strategy verdicts, governing constraint."""
    idx = indices_all_variants(rs, budget.limits, split.gross_by_floor, split.gross_by_zone)
    ic, io = idx["indices"]["IC"], idx["indices"]["IO"]
    front = frontage_need(catalog, program, split)
    common: list[str] = []
    if not ic["passes"]:
        common.append("exceeds_far")
    if not io["passes"]:
        common.append("exceeds_coverage")
    if split.floors > 1 and split.upper > split.ground + TOL:
        common.append("upper_exceeds_ground")

    per_strategy = []
    strategies = budget.strategies[:1] if budget.strategies_equal else budget.strategies
    for st in strategies:
        fails = list(common)
        if split.ground > st.area_sqft + TOL:
            fails.append("exceeds_strategy")
        if front["hard_ft"] > st.front_width_ft + TOL:
            fails.append("frontage_short")
        site = None
        if measurer is not None and "exceeds_strategy" not in fails and "upper_exceeds_ground" not in fails:
            site = measurer.measure(program, st, split.ground, split.floors)
            if not site["feasible"]:
                fails.append("site_fails")
        garden = site["garden_sqft"] if site else None
        paving = (site["paving_sqft"] + site["deck_sqft"] if site else 0.0) + budget.extra_paving_sqft
        open_area = budget.lot_area_sqft - split.ground - paving
        status = next((s for s in STATUS_ORDER if s in fails), None)
        if status is None:
            status = FITS_SMALL_GARDEN if garden is not None and garden < budget.garden_min_sqft else FITS
        per_strategy.append({
            "strategy_id": st.strategy_id, "status": status, "fails": fails,
            "garden_sqft": garden,
            "open_area_sqft": round(open_area, 1),
            "paving_sqft": None if site is None else round(site["paving_sqft"] + budget.extra_paving_sqft, 1),
            "deck_sqft": None if site is None else site["deck_sqft"],
            "front_paving_fraction": None if site is None else site["front_paving_fraction"],
            "site_failed_checks": [] if site is None else site["failed_checks"] + site["reasons"],
            "frontage_margin_ft": round(st.front_width_ft - front["soft_ft"], 2),
        })
    feasible = [p for p in per_strategy if p["status"] in (FITS, FITS_SMALL_GARDEN)]
    chosen = feasible[0] if feasible else per_strategy[0]  # strategies are in order of simplicity
    return {
        "indices": idx,
        "frontage": front,
        "strategies": per_strategy,
        "strategies_ok": [p["strategy_id"] for p in feasible],
        "strategy_used": chosen["strategy_id"] if feasible else None,
        "status": chosen["status"] if feasible else _governing(per_strategy),
        "governing": None if feasible else _governing(per_strategy),
        "garden_sqft": chosen["garden_sqft"],
        "open_area_sqft": chosen["open_area_sqft"],
        "frontage_margin_ft": chosen["frontage_margin_ft"],
    }


def _governing(per_strategy: list[dict]) -> str:
    """The constraint that stops the cell: for the least-failing strategy, the first status in order."""
    return max(per_strategy, key=lambda p: STATUS_ORDER.index(p["status"]))["status"]


__all__ = ["FITS", "FITS_SMALL_GARDEN", "STATUS_ORDER", "LotBudget", "SiteMeasurer", "StrategyCapacity",
           "evaluate_split", "frontage_need", "lot_budget"]
