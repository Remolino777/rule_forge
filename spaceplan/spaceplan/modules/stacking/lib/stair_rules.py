"""Stair and garage-separation rules (step 6.7a, stage S1): CRC R311.7 and R302.6.

Reads the stair ruleset (data/rules/crc_2025_stairs.json); no normative number lives in this file. Values are
converted to feet here, once, so the geometry works in one unit.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from spaceplan.core.lib.rules import RuleSet, load_ruleset, load_ruleset_resource

STAIR_RULESET = ("data", "rules", "crc_2025_stairs.json")
RISER_RULE = "S01-STAIR-RISER"
TREAD_RULE = "S02-STAIR-TREAD"
WIDTH_RULE = "S03-STAIR-WIDTH"
HEADROOM_RULE = "S04-STAIR-HEADROOM"
LANDING_RULE = "S05-STAIR-LANDING"
GARAGE_SEPARATION_RULE = "S06-GARAGE-SEPARATION"
FLIGHT_RISE_RULE = "S07-STAIR-FLIGHT-RISE"
TOP_DOOR_RULE = "S08-STAIR-TOP-DOOR"
UNDER_STAIR_RULE = "S09-UNDER-STAIR-PROTECTION"
HALF_BATH_CLEARANCE_RULE = "S10-HALF-BATH-CLEARANCE"
FIXTURE_HEADROOM_RULE = "S11-FIXTURE-HEADROOM"
STAIR_RULES = (RISER_RULE, TREAD_RULE, WIDTH_RULE, HEADROOM_RULE, LANDING_RULE)
INCH_FT = 1.0 / 12.0


def load_stair_ruleset(path: str | Path | None = None) -> RuleSet:
    return load_ruleset(path) if path else load_ruleset_resource(*STAIR_RULESET)


@dataclass(frozen=True)
class StairLimits:
    """Code limits of a dwelling stair, in feet."""

    riser_max_ft: float
    tread_min_ft: float
    width_min_ft: float
    headroom_min_ft: float
    landing_min_ft: float
    status: str
    sources: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {"riser_max_in": round(self.riser_max_ft / INCH_FT, 4),
                "tread_min_in": round(self.tread_min_ft / INCH_FT, 4),
                "width_min_in": round(self.width_min_ft / INCH_FT, 4),
                "headroom_min_in": round(self.headroom_min_ft / INCH_FT, 4),
                "landing_min_in": round(self.landing_min_ft / INCH_FT, 4),
                "status": self.status, "sources": list(self.sources)}


def _inches(rs: RuleSet, rule_id: str) -> float:
    rule = rs.rule(rule_id)
    if rule.get("unit") != "in":
        raise ValueError(f"{rule_id}: expected a value in inches, got unit {rule.get('unit')!r}")
    return float(rule["value"]) * INCH_FT


def stair_limits(rs: RuleSet) -> StairLimits:
    statuses = {rs.status(r) for r in STAIR_RULES}
    return StairLimits(
        riser_max_ft=_inches(rs, RISER_RULE),
        tread_min_ft=_inches(rs, TREAD_RULE),
        width_min_ft=_inches(rs, WIDTH_RULE),
        headroom_min_ft=_inches(rs, HEADROOM_RULE),
        landing_min_ft=_inches(rs, LANDING_RULE),
        status="provisional" if "provisional" in statuses else "verified",
        sources=tuple(rs.source_tag(r) for r in STAIR_RULES),
    )


def flight_rise_max_ft(rs: RuleSet) -> float:
    return _inches(rs, FLIGHT_RISE_RULE)


def fixture_headroom_ft(rs: RuleSet) -> float:
    """Clear height a half bath needs over its fixture clearances (R305.1 exception)."""
    return _inches(rs, FIXTURE_HEADROOM_RULE)


def half_bath_width_min_ft(rs: RuleSet) -> float:
    """Narrowest room that holds a water closet: twice its centre-to-side clearance (R307)."""
    return 2.0 * rs.params(HALF_BATH_CLEARANCE_RULE)["wc_center_to_side_in"] * INCH_FT


def under_stair_protection(rs: RuleSet) -> dict[str, Any]:
    return {"rule_id": UNDER_STAIR_RULE, "requirement": rs.params(UNDER_STAIR_RULE)["requirement"],
            "status": rs.status(UNDER_STAIR_RULE), "source": rs.source_tag(UNDER_STAIR_RULE)}


def garage_separation(rs: RuleSet, habitable_above: bool) -> dict[str, Any]:
    """What R302.6 asks of the garage-dwelling separation (a construction note, not a planning limit)."""
    params = rs.params(GARAGE_SEPARATION_RULE)
    return {"rule_id": GARAGE_SEPARATION_RULE,
            "habitable_above": habitable_above,
            "requirement": params["under_habitable_room" if habitable_above else "otherwise"],
            "status": rs.status(GARAGE_SEPARATION_RULE),
            "source": rs.source_tag(GARAGE_SEPARATION_RULE)}


__all__ = [
    "FIXTURE_HEADROOM_RULE",
    "FLIGHT_RISE_RULE",
    "GARAGE_SEPARATION_RULE",
    "HALF_BATH_CLEARANCE_RULE",
    "HEADROOM_RULE",
    "LANDING_RULE",
    "RISER_RULE",
    "STAIR_RULES",
    "STAIR_RULESET",
    "TOP_DOOR_RULE",
    "TREAD_RULE",
    "UNDER_STAIR_RULE",
    "WIDTH_RULE",
    "StairLimits",
    "fixture_headroom_ft",
    "flight_rise_max_ft",
    "garage_separation",
    "half_bath_width_min_ft",
    "load_stair_ruleset",
    "stair_limits",
    "under_stair_protection",
]
