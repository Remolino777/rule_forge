"""Design variables of the client (FOS, FOT, floors policy, profiles): editable values with source and status.

Read from data/rules/client_design_variables.json (kind "client") and overridable per run. The legal limits
stay in the SDMC rulesets; this module only combines them with the client's design caps:

    design footprint  = FOS x base area (envelope inside the setbacks, or the lot)
    effective footprint = min(legal footprint, design footprint)     legal = envelope and hillside coverage
    effective FOT area  = SDMC FAR area (source "sdmc") or fixed FOT x FAR base area (source "fixed", a scenario)
    effective maximum   = min(effective FOT area, floors allowed by height x effective footprint)

Each result names the limit that governs, so a report can say whether the law or the client's choice decides.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from spaceplan.core.lib.rules import RuleSet, load_ruleset, load_ruleset_resource

DESIGN_RULESET = ("data", "rules", "client_design_variables.json")
FOS_RULE, FOT_RULE, FLOORS_RULE, PROFILES_RULE = ("D01-DESIGN-FOS", "D02-FOT", "D03-FLOORS-POLICY",
                                                  "D04-PROFILES")
ENVELOPE, LOT = "envelope", "lot"
SDMC, FIXED = "sdmc", "fixed"
ONE_FLOOR_FIRST, SCORE = "one_floor_first", "score"
FOOTPRINT, KNEE = "footprint", "knee"


class DesignVariablesError(ValueError):
    pass


@dataclass(frozen=True)
class DesignVariables:
    fos: float
    fos_base: str
    fot_source: str
    fot_fixed: float
    floors_policy: str
    optimum_policy: str
    lot_minimum: dict[str, Any]
    ruleset_id: str
    version: str
    sha256: str
    overridden: tuple[str, ...] = ()

    @property
    def normative(self) -> bool:
        """False when a fixed FOT replaces the SDMC FAR (scenario run)."""
        return self.fot_source == SDMC

    def with_overrides(self, **values: Any) -> DesignVariables:
        keys = {k: v for k, v in values.items() if v is not None}
        out = replace(self, **keys, overridden=tuple(sorted(set(self.overridden) | set(keys))))
        check(out)
        return out

    def to_dict(self) -> dict[str, Any]:
        return {"fos": self.fos, "fos_base": self.fos_base, "fot_source": self.fot_source,
                "fot_fixed": self.fot_fixed, "floors_policy": self.floors_policy,
                "optimum_policy": self.optimum_policy, "lot_minimum": dict(self.lot_minimum),
                "normative": self.normative, "ruleset_id": self.ruleset_id, "version": self.version,
                "sha256": self.sha256, "overridden": list(self.overridden)}


def check(dv: DesignVariables) -> None:
    problems = []
    if not 0.0 < dv.fos <= 1.0:
        problems.append(f"fos must be in (0, 1], got {dv.fos}")
    if dv.fos_base not in (ENVELOPE, LOT):
        problems.append(f"fos_base must be '{ENVELOPE}' or '{LOT}', got {dv.fos_base!r}")
    if dv.fot_source not in (SDMC, FIXED):
        problems.append(f"fot_source must be '{SDMC}' or '{FIXED}', got {dv.fot_source!r}")
    if not dv.fot_fixed > 0.0:
        problems.append(f"fot (fixed value) must be > 0, got {dv.fot_fixed}")
    if dv.floors_policy not in (ONE_FLOOR_FIRST, SCORE):
        problems.append(f"floors_policy must be '{ONE_FLOOR_FIRST}' or '{SCORE}', got {dv.floors_policy!r}")
    if dv.optimum_policy not in (FOOTPRINT, KNEE):
        problems.append(f"optimum_policy must be '{FOOTPRINT}' or '{KNEE}', got {dv.optimum_policy!r}")
    if problems:
        raise DesignVariablesError("invalid design variables:\n  - " + "\n  - ".join(problems))


def load_design_variables(path: str | Path | None = None, **overrides: Any) -> DesignVariables:
    rs: RuleSet = load_ruleset(path) if path else load_ruleset_resource(*DESIGN_RULESET)
    fos, fot, floors, prof = (rs.rule(FOS_RULE), rs.params(FOT_RULE), rs.params(FLOORS_RULE),
                              rs.params(PROFILES_RULE))
    dv = DesignVariables(
        fos=float(fos["value"]), fos_base=fos["parameters"]["base"], fot_source=fot["source"],
        fot_fixed=float(fot["fixed_value"]), floors_policy=floors["policy"], optimum_policy=prof["optimum"],
        lot_minimum=dict(prof["lot_minimum"]), ruleset_id=rs.ruleset_id, version=rs.version, sha256=rs.sha256)
    check(dv)
    return dv.with_overrides(**overrides) if any(v is not None for v in overrides.values()) else dv


def design_limits(dv: DesignVariables, lot_area_sqft: float, envelope_sqft: float, legal_footprint_sqft: float,
                  legal_gross_max_sqft: float, far_base_sqft: float, floors_by_height: int) -> dict[str, Any]:
    """Effective footprint and area ceilings of one lot, each with the limit that governs it."""
    base = envelope_sqft if dv.fos_base == ENVELOPE else lot_area_sqft
    design_fp = dv.fos * base
    footprint = min(legal_footprint_sqft, design_fp)
    fp_gov = "design_fos" if design_fp < legal_footprint_sqft else "legal_envelope_or_coverage"
    if dv.fot_source == SDMC:
        fot_area, fot_gov = legal_gross_max_sqft, "sdmc_far"
    else:
        fot_area, fot_gov = dv.fot_fixed * far_base_sqft, "fixed_fot_scenario"
    by_floors = floors_by_height * footprint
    maximum = min(fot_area, by_floors)
    return {
        "fos": dv.fos, "fos_base": dv.fos_base, "fos_base_sqft": round(base, 1),
        "design_footprint_sqft": round(design_fp, 1), "legal_footprint_sqft": round(legal_footprint_sqft, 1),
        "footprint_sqft": round(footprint, 1), "footprint_governing": fp_gov,
        "fot_source": dv.fot_source, "fot": round(fot_area / far_base_sqft, 4) if far_base_sqft else None,
        "far_base_sqft": round(far_base_sqft, 1), "lot_area_sqft": round(lot_area_sqft, 1),
        "envelope_sqft": round(envelope_sqft, 1),
        "fot_area_sqft": round(fot_area, 1), "legal_far_area_sqft": round(legal_gross_max_sqft, 1),
        "floors_by_height": floors_by_height, "floors_x_footprint_sqft": round(by_floors, 1),
        "maximum_sqft": round(maximum, 1),
        "maximum_governing": fot_gov if fot_area <= by_floors else "height_floors_x_footprint",
        "normative": dv.normative,
        "exceeds_legal_far": fot_area > legal_gross_max_sqft + 1e-6,
    }


__all__ = [
    "DESIGN_RULESET",
    "ENVELOPE",
    "FIXED",
    "FLOORS_RULE",
    "FOOTPRINT",
    "FOS_RULE",
    "FOT_RULE",
    "KNEE",
    "LOT",
    "ONE_FLOOR_FIRST",
    "PROFILES_RULE",
    "SCORE",
    "SDMC",
    "DesignVariables",
    "DesignVariablesError",
    "check",
    "design_limits",
    "load_design_variables",
]
