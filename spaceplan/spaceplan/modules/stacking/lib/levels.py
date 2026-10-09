"""Levels of a cell (step 6.7, stage S0): one entry per level relative to grade, with rule-derived properties.

A level is the unit of the vertical layer: level 0 is the ground floor, +1 the upper floor, -1 a basement
(step 6.7b). Each level says where its finish floor sits over grade and whether it counts in the gross floor
area (FAR), as a story and in the occupancy index (IO), so a basement is one more level and not a special case.
"""

from __future__ import annotations

from typing import Any

from spaceplan.core.lib.rules import RuleSet
from spaceplan.modules.stacking.lib.vertical_rules import first_story_ok

GROUND, UPPER = "ground", "upper"


def cell_gross_by_floor(cell: dict[str, Any]) -> list[float]:
    """Gross area of each floor as step 6.6 split it (stair included on every floor of a two-floor scheme)."""
    split = cell.get("split") or {}
    gross = split.get("gross_by_floor_sqft")
    if gross:
        return [float(g) for g in gross]
    return [float(cell["ground_sqft"])] + ([float(cell["upper_sqft"])] if cell["floors"] > 1 else [])


def build_levels(cell: dict[str, Any], levels_cfg: dict[str, Any], rs: RuleSet,
                 stair_sqft_catalog: float, stair_tolerance_sqft: float) -> tuple[list[dict[str, Any]], list[str]]:
    """Levels above grade of an area-matrix cell, and warnings (first story, stair area consistency)."""
    gross = cell_gross_by_floor(cell)
    split = cell.get("split") or {}
    f2f = levels_cfg["floor_to_floor_ft"]
    ground_ff = levels_cfg["ground_floor_above_grade_ft"]
    stair = float(split.get("stair_sqft_per_floor") or 0.0) if len(gross) > 1 else 0.0
    warnings = []
    if not first_story_ok(rs, ground_ff):
        warnings.append(f"ground floor {ground_ff:g} ft over grade is above the first-story limit (113.0261(a))")
    if len(gross) > 1 and abs(stair - stair_sqft_catalog) > stair_tolerance_sqft:
        warnings.append(f"stair area per floor {stair:g} sq ft in the area matrix differs from the catalog "
                        f"target {stair_sqft_catalog:g} sq ft")
    levels = []
    for k, area in enumerate(gross):
        levels.append({
            "level": k,
            "kind": GROUND if k == 0 else UPPER,
            "finish_floor_ft": round(ground_ff + k * f2f, 4),
            "gross_sqft": round(area, 4),
            "stair_sqft": round(stair, 4),
            "spaces": None if k == 0 else list(split.get("upper_spaces") or []),
            "counts_in_gfa": True,
            "is_story": True,
            "counts_in_io": k == 0,
        })
    return levels, warnings


__all__ = ["GROUND", "UPPER", "build_levels", "cell_gross_by_floor"]
