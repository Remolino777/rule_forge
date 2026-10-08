"""Building indices as a ratio-rule family (step 6.6): construction index (IC) and occupancy index (IO).

The ruleset declares each index (numerator, denominator, the rule that limits it) and the variants of
what counts as gross floor area (garage included or excluded). This module only measures numerators
from a floor split and compares them with the limits the capacity layer already resolved, so another
jurisdiction declares its own indices in data:

    IC = gross floor area / lot area        limit: FAR (SDMC Table 131-04J on the FAR base area)
    IO = ground-floor footprint / lot area  limit: hillside coverage (131.0445(a)); none on flat lots
    IC per floor = floor gross area / lot area (breakdown, no limit)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from spaceplan.lib.rules import RuleSet

INDICES_RULE = "Z15-BUILDING-INDICES"
TOL = 1e-6


@dataclass(frozen=True)
class IndexLimits:
    """Limits resolved for one lot (by the capacity layer)."""

    lot_area_sqft: float
    gross_area_max_sqft: float
    coverage_max: float | None

    def limit_ratio(self, kind: str) -> float | None:
        if kind == "gross_area_max":
            return self.gross_area_max_sqft / self.lot_area_sqft
        if kind == "coverage_max":
            return self.coverage_max
        raise KeyError(f"unknown limit kind {kind!r}")


def index_rule(rs: RuleSet) -> dict[str, Any]:
    return rs.rule(INDICES_RULE)


def variant_ids(rs: RuleSet) -> list[str]:
    return [v["variant_id"] for v in index_rule(rs).get("variants", [])]


def default_variant(rs: RuleSet) -> str:
    return index_rule(rs)["parameters"]["default_variant"]


def numerators(gross_by_floor: tuple[float, ...], gross_by_zone: dict[str, float],
               excluded_zones: list[str]) -> dict[str, float]:
    excluded = sum(gross_by_zone.get(z, 0.0) for z in excluded_zones)
    return {"gross_floor_area": sum(gross_by_floor) - excluded, "ground_footprint": gross_by_floor[0]}


def evaluate_indices(rs: RuleSet, limits: IndexLimits, gross_by_floor: tuple[float, ...],
                     gross_by_zone: dict[str, float], variant_id: str | None = None) -> dict[str, Any]:
    """Every index of the ruleset for one floor split under one gross-floor-area variant."""
    rule = index_rule(rs)
    variant_id = variant_id or default_variant(rs)
    excluded = rs.params(INDICES_RULE, variant_id).get("excluded_zones", [])
    nums = numerators(gross_by_floor, gross_by_zone, excluded)
    denominators = {"lot_area": limits.lot_area_sqft}
    out: dict[str, Any] = {"variant": variant_id, "indices": {}}
    for spec in rule["parameters"]["indices"]:
        value = nums[spec["numerator"]] / denominators[spec["denominator"]]
        limit = limits.limit_ratio(spec["limit_kind"])
        out["indices"][spec["symbol"]] = {
            "index_id": spec["index_id"],
            "value": round(value, 4),
            "limit": None if limit is None else round(limit, 4),
            "passes": True if limit is None else value <= limit + TOL,
            "limit_rule_id": spec["limit_rule_id"],
        }
    out["by_floor"] = [round(g / limits.lot_area_sqft, 4) for g in gross_by_floor]
    out["gross_floor_area_sqft"] = round(nums["gross_floor_area"], 1)
    return out


def indices_all_variants(rs: RuleSet, limits: IndexLimits, gross_by_floor: tuple[float, ...],
                         gross_by_zone: dict[str, float]) -> dict[str, Any]:
    """Default variant plus the alternatives; flags an index whose verdict depends on the variant."""
    base_id = default_variant(rs)
    base = evaluate_indices(rs, limits, gross_by_floor, gross_by_zone, base_id)
    alternatives = {v: evaluate_indices(rs, limits, gross_by_floor, gross_by_zone, v)
                    for v in variant_ids(rs) if v != base_id}
    sensitive = sorted({sym for alt in alternatives.values() for sym, r in alt["indices"].items()
                        if r["passes"] != base["indices"][sym]["passes"]})
    return {**base, "alternatives": {v: {s: r["value"] for s, r in a["indices"].items()} | {
        "passes": all(r["passes"] for r in a["indices"].values())} for v, a in alternatives.items()},
            "variant_sensitive": sensitive}


__all__ = ["INDICES_RULE", "IndexLimits", "default_variant", "evaluate_indices", "index_rule",
           "indices_all_variants", "variant_ids"]
