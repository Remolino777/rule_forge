"""Stacking catalog (step 6.7): design parameters of the vertical layer, with source and status.

A separate catalog owned by the stacking module (like the household catalog), so the residential catalog and the
golden packages stay unchanged. Normative values are not here: they live in the rulesets.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from spaceplan.core.lib_aux.hashing import sha256_of
from spaceplan.core.lib_aux.json_io import load_json, load_resource_json

STACKING_CATALOG = ("data", "catalog", "stacking_catalog.json")
ROOF_KINDS = ("flat", "pitched")


class StackingCatalogError(ValueError):
    pass


@dataclass(frozen=True)
class StackingCatalog:
    data: dict[str, Any]
    sha256: str

    @property
    def version(self) -> str:
        return self.data["catalog_version"]

    @property
    def levels(self) -> dict[str, Any]:
        return self.data["levels"]

    @property
    def default_mode(self) -> str:
        return self.data["selection"]["default_mode"]

    def stage_default_mode(self, stage: str) -> str:
        """Selection mode a stage uses when none is given (S1 draws fewer cells than S0 checks)."""
        return self.data["selection"].get("stage_default_modes", {}).get(stage, self.default_mode)

    def selection_k(self, mode: str | None) -> int | None:
        """Rank cut of a selection mode (None = every ranked cell)."""
        modes = self.data["selection"]["modes"]
        mode = mode or self.default_mode
        if mode not in modes:
            raise StackingCatalogError(f"unknown selection mode {mode!r}; expected one of {', '.join(modes)}")
        return modes[mode]

    @property
    def roofs(self) -> list[dict[str, Any]]:
        return self.data["roofs"]["types"]

    @property
    def default_roof(self) -> str:
        return self.data["roofs"]["default_roof"]

    def roof(self, roof_id: str) -> dict[str, Any]:
        for roof in self.roofs:
            if roof["roof_id"] == roof_id:
                return roof
        raise StackingCatalogError(f"unknown roof {roof_id!r}")

    @property
    def stair_space_type(self) -> str:
        return self.data["stair"]["space_type"]

    @property
    def stair_tolerance_sqft(self) -> float:
        return self.data["stair"]["consistency_tolerance_sqft"]

    @property
    def probe_exposures(self) -> list[float]:
        return list(self.data["below_grade"]["probe_exposures_ft"])

    # ----------------------------------------------------------------- stage S1

    @property
    def stair_design(self) -> dict[str, Any]:
        return self.data["stair"]["design"]

    @property
    def stair_types(self) -> list[dict[str, Any]]:
        """Stair types in the order stage S1 tries them."""
        by_id = {t["stair_id"]: t for t in self.data["stair"]["types"]}
        return [by_id[i] for i in self.data["stair"]["type_order"]]

    @property
    def stair_search_step(self) -> float:
        return float(self.data["stair"]["placement"]["search_step_ft"])

    def upper_placements(self, scheme_id: str | None) -> list[str]:
        """Upper-floor placements in the order stage S1 tries them for a vertical scheme."""
        uf = self.data["upper_floor"]
        return list(uf.get("scheme_order", {}).get(scheme_id or "", uf["placements"]))

    @property
    def garage(self) -> dict[str, Any]:
        return self.data["garage"]

    @property
    def roof_order(self) -> list[str]:
        return list(self.data["roof_orientation"]["order"])

    @property
    def flat_roof_id(self) -> str:
        return self.data["roof_orientation"]["flat_roof"]

    @property
    def geometry(self) -> dict[str, Any]:
        return self.data["geometry"]


STAIR_TYPES = ("straight", "u_turn", "l_turn")
PLACEMENTS = ("rear", "front", "over_garage")
ROOF_STEPS = ("default", "rotated", "flat")
S1_BLOCKS = ("upper_floor", "garage", "roof_orientation", "geometry")


def _check_s1(data: dict[str, Any]) -> list[str]:
    """Structural problems of the stage-S1 blocks."""
    problems = []
    for key in S1_BLOCKS:
        if key not in data:
            problems.append(f"missing block {key!r}")
    stair = data["stair"]
    for key in ("design", "types", "type_order", "placement"):
        if key not in stair:
            problems.append(f"missing stair.{key}")
    if problems:
        return problems
    for key in ("tread_in", "width_ft", "landing_ft", "u_turn_gap_ft"):
        if not isinstance(stair["design"].get(key), (int, float)) or stair["design"][key] < 0:
            problems.append(f"stair.design.{key} must be a number >= 0")
    ids = [t.get("stair_id") for t in stair["types"]]
    if any(i not in STAIR_TYPES for i in ids):
        problems.append(f"stair.types: stair_id must be one of {STAIR_TYPES}")
    if not stair["type_order"] or any(i not in ids for i in stair["type_order"]):
        problems.append("stair.type_order must list declared stair types")
    if not isinstance(stair["placement"].get("search_step_ft"), (int, float)) or stair["placement"]["search_step_ft"] <= 0:
        problems.append("stair.placement.search_step_ft must be > 0")
    uf = data["upper_floor"]
    orders = [uf.get("placements", [])] + list(uf.get("scheme_order", {}).values())
    if not uf.get("placements") or any(p not in PLACEMENTS for order in orders for p in order):
        problems.append(f"upper_floor placements must be drawn from {PLACEMENTS}")
    g = data["garage"]
    if g.get("side") not in ("left", "right"):
        problems.append("garage.side must be 'left' or 'right'")
    for key in ("single_width_ft", "double_width_ft", "double_from_sqft", "max_width_fraction"):
        if not isinstance(g.get(key), (int, float)) or g[key] <= 0:
            problems.append(f"garage.{key} must be a number > 0")
    ro = data["roof_orientation"]
    if not ro.get("order") or any(s not in ROOF_STEPS for s in ro["order"]):
        problems.append(f"roof_orientation.order must be drawn from {ROOF_STEPS}")
    roof_ids = {r.get("roof_id") for r in data["roofs"].get("types", [])}
    if ro.get("flat_roof") not in roof_ids:
        problems.append("roof_orientation.flat_roof is not a declared roof")
    for key in ("area_tolerance_sqft", "round_ft", "bisection_rounds"):
        if not isinstance(data["geometry"].get(key), (int, float)) or data["geometry"][key] <= 0:
            problems.append(f"geometry.{key} must be a number > 0")
    return problems


def check_stacking_catalog(data: dict[str, Any]) -> list[str]:
    """Structural problems of a stacking catalog (empty list = valid)."""
    problems = []
    for key in ("catalog_id", "catalog_version", "selection", "levels", "roofs", "stair", "below_grade"):
        if key not in data:
            problems.append(f"missing block {key!r}")
    if problems:
        return problems
    sel = data["selection"]
    if sel.get("default_mode") not in sel.get("modes", {}):
        problems.append("selection.default_mode is not one of selection.modes")
    if any(m not in sel.get("modes", {}) for m in sel.get("stage_default_modes", {}).values()):
        problems.append("selection.stage_default_modes values must be selection modes")
    for k in sel.get("modes", {}).values():
        if k is not None and (not isinstance(k, int) or k < 1):
            problems.append("selection.modes values must be integers >= 1 or null")
    for key in ("floor_to_floor_ft", "ground_floor_above_grade_ft", "top_floor_plate_ft"):
        value = data["levels"].get(key)
        if not isinstance(value, (int, float)) or value < 0:
            problems.append(f"levels.{key} must be a number >= 0")
    if data["levels"].get("floor_to_floor_ft", 0) <= 0:
        problems.append("levels.floor_to_floor_ft must be > 0")
    if "source" not in data["levels"]:
        problems.append("levels.source is missing")
    ids = [r.get("roof_id") for r in data["roofs"].get("types", [])]
    if len(ids) != len(set(ids)) or not ids:
        problems.append("roofs.types must have unique roof_id values")
    if data["roofs"].get("default_roof") not in ids:
        problems.append("roofs.default_roof is not a declared roof")
    for roof in data["roofs"].get("types", []):
        if roof.get("kind") not in ROOF_KINDS:
            problems.append(f"roof {roof.get('roof_id')!r}: kind must be one of {ROOF_KINDS}")
        elif roof["kind"] == "flat" and not isinstance(roof.get("parapet_ft"), (int, float)):
            problems.append(f"roof {roof['roof_id']!r}: flat roof needs parapet_ft")
        elif roof["kind"] == "pitched" and not isinstance(roof.get("pitch_rise_per_run"), (int, float)):
            problems.append(f"roof {roof['roof_id']!r}: pitched roof needs pitch_rise_per_run")
    if not data["below_grade"].get("probe_exposures_ft"):
        problems.append("below_grade.probe_exposures_ft is empty")
    return problems + _check_s1(data)


def load_stacking_catalog(path: str | Path | None = None) -> StackingCatalog:
    data = load_json(path) if path else load_resource_json("spaceplan", *STACKING_CATALOG)
    problems = check_stacking_catalog(data)
    if problems:
        raise StackingCatalogError("invalid stacking catalog:\n  - " + "\n  - ".join(problems))
    return StackingCatalog(data=data, sha256=sha256_of(data))


__all__ = ["PLACEMENTS", "ROOF_STEPS", "STACKING_CATALOG", "STAIR_TYPES", "StackingCatalog", "StackingCatalogError",
           "check_stacking_catalog", "load_stacking_catalog"]
