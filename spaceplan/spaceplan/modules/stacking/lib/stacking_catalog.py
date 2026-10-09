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
    return problems


def load_stacking_catalog(path: str | Path | None = None) -> StackingCatalog:
    data = load_json(path) if path else load_resource_json("spaceplan", *STACKING_CATALOG)
    problems = check_stacking_catalog(data)
    if problems:
        raise StackingCatalogError("invalid stacking catalog:\n  - " + "\n  - ".join(problems))
    return StackingCatalog(data=data, sha256=sha256_of(data))


__all__ = ["STACKING_CATALOG", "StackingCatalog", "StackingCatalogError", "check_stacking_catalog",
           "load_stacking_catalog"]
