"""Normative sensitivity (2026-10-09): how the design FOS and the FOT move each lot between one and two floors.

Arithmetic on lot budgets (no geometry runs): for a grid of FOS values and of FOT sources (the SDMC table and fixed
values), every lot gets its effective footprint, its effective maximum and the limit that governs each, and every
household demand (gross area of a program) is classified:

    one_floor   demand <= effective footprint
    two_floors  footprint < demand <= effective maximum (FOT, or floors allowed by height x footprint)
    split_fails the area fits two floors, but no balanced split keeps the ground floor inside the footprint
                (step 9a: the smallest ground floor of the program, every movable space upstairs, is larger)
    exceeds     demand > effective maximum: no two-floor house holds it (basement, third floor or less program)

Demands are household programs that do not depend on the lot (the household minimum and the complete program of its
expansion curve), so a change of the FOS or the FOT is the only thing that moves a household between classes.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import replace
from statistics import median
from typing import Any

from spaceplan.core.lib.design_variables import FIXED, SDMC, DesignVariables, design_limits

ONE, TWO, SPLIT, EXCEEDS = "one_floor", "two_floors", "split_fails", "exceeds"
CLASSES = (ONE, TWO, SPLIT, EXCEEDS)


def classify(demand_sqft: float, footprint_sqft: float, maximum_sqft: float, stair_two_floors_sqft: float,
             ground_min_sqft: float | None = None) -> str:
    """One floor, two floors (the stair counts on both), two floors whose ground floor cannot fit the footprint
    (`ground_min_sqft`, step 9a) or beyond the effective maximum."""
    if demand_sqft <= footprint_sqft + 1e-6:
        return ONE
    if demand_sqft + stair_two_floors_sqft <= maximum_sqft + 1e-6:
        if ground_min_sqft is not None and ground_min_sqft > footprint_sqft + 1e-6:
            return SPLIT
        return TWO
    return EXCEEDS


def lot_limits(dv: DesignVariables, lot: dict[str, Any]) -> dict[str, Any]:
    """Design limits of one lot from its area-matrix budget (`lot['budget']['design']` holds the legal inputs)."""
    d = lot["budget"]["design"]
    return design_limits(dv, d["lot_area_sqft"], d["envelope_sqft"], d["legal_footprint_sqft"],
                         d["legal_far_area_sqft"], d["far_base_sqft"], int(d["floors_by_height"]))


def grid_point(dv: DesignVariables, lot: dict[str, Any], demands: dict[str, dict[str, float]],
               stair_two_floors_sqft: float) -> dict[str, Any]:
    lim = lot_limits(dv, lot)
    row = {"lot_id": lot["budget"]["lot_id"], "fos": dv.fos, "fos_base": dv.fos_base, "fot_source": dv.fot_source,
           "fot": lim["fot"], "footprint_sqft": lim["footprint_sqft"], "footprint_governing": lim["footprint_governing"],
           "maximum_sqft": lim["maximum_sqft"], "maximum_governing": lim["maximum_governing"],
           "normative": lim["normative"], "exceeds_legal_far": lim["exceeds_legal_far"]}
    for level in ("minimum", "complete"):
        counts = Counter(classify(d[level], lim["footprint_sqft"], lim["maximum_sqft"], stair_two_floors_sqft,
                                  d.get(f"{level}_ground_min"))
                         for d in demands.values())
        n = max(1, len(demands))
        for cls in CLASSES:
            row[f"{level}_{cls}_share"] = round(counts.get(cls, 0) / n, 4)
    return row


def sweep(dv: DesignVariables, lots: list[dict[str, Any]], demands: dict[str, dict[str, float]],
          fos_grid: list[float], fot_grid: list[float], stair_two_floors_sqft: float) -> list[dict[str, Any]]:
    """FOS sweep at the SDMC FOT, and FOT sweep (fixed values) at the base FOS, for every lot."""
    rows = []
    for lot in lots:
        for fos in fos_grid:
            rows.append({"sweep": "fos", **grid_point(replace(dv, fos=fos, fot_source=SDMC), lot, demands,
                                                       stair_two_floors_sqft)})
        for fot in fot_grid:
            rows.append({"sweep": "fot", **grid_point(replace(dv, fot_source=FIXED, fot_fixed=fot), lot, demands,
                                                       stair_two_floors_sqft)})
    return rows


def thresholds(rows: list[dict[str, Any]], demands: dict[str, dict[str, float]]) -> list[dict[str, Any]]:
    """Per lot: the smallest FOS at which the median complete program fits one floor (SDMC FOT), the smallest FOS
    at which every complete program that needs two floors has a balanced split (step 9a), and the smallest fixed FOT
    at which every complete program fits within the effective maximum (at the base FOS)."""
    med = median(d["complete"] for d in demands.values()) if demands else None
    out = []
    for lot_id in sorted({r["lot_id"] for r in rows}):
        fos_rows = sorted((r for r in rows if r["lot_id"] == lot_id and r["sweep"] == "fos"), key=lambda r: r["fos"])
        fot_rows = sorted((r for r in rows if r["lot_id"] == lot_id and r["sweep"] == "fot"), key=lambda r: r["fot"])
        fos_one = next((r["fos"] for r in fos_rows if med is not None and med <= r["footprint_sqft"] + 1e-6), None)
        fot_all = next((r["fot"] for r in fot_rows if r["complete_exceeds_share"] == 0.0), None)
        cap = next((r["maximum_governing"] for r in reversed(fot_rows)), None)
        fos_split = next((r["fos"] for r in fos_rows if r.get("complete_split_fails_share", 0.0) == 0.0), None)
        out.append({"lot_id": lot_id, "median_complete_sqft": None if med is None else round(med, 1),
                    "fos_for_median_one_floor": fos_one, "fot_for_all_complete": fot_all,
                    "fos_for_every_split": fos_split,
                    "governing_at_high_fot": cap})
    return out


__all__ = ["CLASSES", "EXCEEDS", "ONE", "SPLIT", "TWO", "classify", "grid_point", "lot_limits", "sweep", "thresholds"]
