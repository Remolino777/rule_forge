"""Workflow of the stacking module (step 6.7a, stage S0): levels and height budget of the 6.6 winners.

    area_matrix (6.6) + lot_capacity of each lot
      -> select the ranked cells (best / top2 / all)
      -> per lot: height envelope (131.0444), floors the height allows, below-grade probe (113.0234, 113.0261)
      -> per cell: levels relative to grade, height check per roof type, status, next stage
      -> result {meta, lots, cells} (contract stack_plan)

Stage S1 (stair, plane-limited polygon per level, upper-floor containment) and S2 (upper-floor zoning) read the
cells marked next_stage = "S1". The workflow only reads contracts: no lotcap, site or areas code runs here.
"""

from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path
from typing import Any

from spaceplan.core.lib.catalog import load_catalog
from spaceplan.core.lib.contracts import read_contract
from spaceplan.modules.stacking.lib.cell_selection import (
    select_cells,
    selection_counts,
    selection_label,
)
from spaceplan.modules.stacking.lib.height_check import (
    EXCEEDS_HEIGHT,
    best_status,
    check_height,
    worst_status,
)
from spaceplan.modules.stacking.lib.levels import build_levels
from spaceplan.modules.stacking.lib.lot_vertical import lot_envelope, lot_vertical_facts
from spaceplan.modules.stacking.lib.stacking_catalog import load_stacking_catalog
from spaceplan.modules.stacking.lib.vertical_rules import (
    garage_counts_in_gfa,
    load_vertical_ruleset,
)

STEP, STAGE = "6.7a", "S0"
CELL_KEYS = ("lot_id", "household_id", "archetype_id", "culture", "profile", "scheme_id", "floors", "rank",
             "strategy_used")


def _strategy_width(lot: dict[str, Any], strategy_id: str | None) -> float | None:
    for s in lot["budget"]["strategies"]:
        if s["strategy_id"] == strategy_id:
            return s.get("front_width_ft")
    return None


def stack_cell(cell: dict[str, Any], lot: dict[str, Any], lot_capacity: dict[str, Any], rs, scat,
               stair_sqft: float) -> dict[str, Any]:
    """Stage S0 of one cell: levels, height per roof type and the status of the default roof."""
    levels, warnings = build_levels(cell, scat.levels, rs, stair_sqft, scat.stair_tolerance_sqft)
    width = _strategy_width(lot, cell.get("strategy_used"))
    if not width:
        width = levels[0]["gross_sqft"] ** 0.5
        warnings.append("strategy width missing: footprint taken as a square")
    envelope = lot_envelope(rs, lot_capacity)
    slope = (lot_capacity.get("terrain") or {}).get("mean_slope")
    height = [check_height(levels, width, roof, scat.levels["top_floor_plate_ft"], envelope, rs, slope)
              for roof in scat.roofs]
    default = next(h for h in height if h["roof_id"] == scat.default_roof)
    status = default["status"]
    return {
        **{k: cell.get(k) for k in CELL_KEYS},
        "selection": selection_label(cell),
        "area_status": cell["status"],
        "upper_spaces": list((cell.get("split") or {}).get("upper_spaces") or []),
        "levels": levels,
        "height": height,
        "default_roof": scat.default_roof,
        "status": status,
        "status_best_roof": best_status([h["status"] for h in height]),
        "status_worst_roof": worst_status([h["status"] for h in height]),
        "governing": ("131.0444 angled plane" if status == "plane_governs"
                      else "height limit" if status == EXCEEDS_HEIGHT else None),
        "next_stage": "S1" if cell["floors"] > 1 and status != EXCEEDS_HEIGHT else None,
        "warnings": warnings,
    }


def _lot_summary(cells: list[dict[str, Any]]) -> dict[str, Any]:
    return {"cells": len(cells),
            "by_floors": dict(sorted(Counter(str(c["floors"]) for c in cells).items())),
            "status_counts": dict(sorted(Counter(c["status"] for c in cells).items())),
            "to_s1": sum(1 for c in cells if c["next_stage"] == "S1"),
            "max_side_inset_ft": max((h["side_inset_ft"] for c in cells for h in c["height"]
                                      if h["roof_id"] == c["default_roof"]), default=0.0)}


def run_stacking(area_matrix: dict, lot_capacities: dict[str, dict] | list[dict], mode: str | None = None,
                 catalog_path=None, rules_path=None, stacking_catalog_path=None) -> dict[str, Any]:
    """Stage S0 over an area_matrix contract and the lot_capacity contracts of its lots (by brief_id)."""
    am = read_contract(area_matrix, "area_matrix")
    if isinstance(lot_capacities, list):
        lot_capacities = {c["brief_id"]: c for c in lot_capacities}
    lcs = {lot_id: read_contract(c, "lot_capacity") for lot_id, c in lot_capacities.items()}
    rs = load_vertical_ruleset(rules_path)
    scat = load_stacking_catalog(stacking_catalog_path)
    catalog = load_catalog(catalog_path)
    stair_sqft = float(catalog.space_type(scat.stair_space_type)["area"]["target"])
    mode = mode or scat.default_mode
    selected = select_cells(am["cells"], scat.selection_k(mode))

    lots_out, cells_out, missing = [], [], []
    for lot in am["lots"]:
        lot_id = lot["budget"]["lot_id"]
        lc = lcs.get(lot_id)
        if lc is None:
            missing.append(lot_id)
            continue
        lot_cells = [stack_cell(c, lot, lc, rs, scat, stair_sqft) for c in selected if c["lot_id"] == lot_id]
        cells_out += lot_cells
        lots_out.append({**lot_vertical_facts(rs, scat, lc), "summary": _lot_summary(lot_cells)})
    if missing:
        raise ValueError(f"stacking: no lot_capacity contract for lot(s) {', '.join(missing)}")
    return {
        "meta": {
            "step": STEP,
            "stage": STAGE,
            "selection_mode": mode,
            "selection": selection_counts(am["cells"], selected),
            "area_matrix_step": am["meta"]["step"],
            "vertical_ruleset": rs.ruleset_id,
            "vertical_ruleset_version": rs.version,
            "vertical_ruleset_sha256": rs.sha256,
            "stacking_catalog_version": scat.version,
            "stacking_catalog_sha256": scat.sha256,
            "catalog": catalog.data["catalog_version"],
            "stair_sqft_per_level": stair_sqft,
            "garage_counts_in_gfa": garage_counts_in_gfa(rs),
            "households": list(am["meta"]["households"]),
            "lots": [lot["lot_id"] for lot in lots_out],
            "note": ("Stage S0: arithmetic on levels and heights; footprints approximated by rectangles of the "
                     "floor area with the strategy's street-facing width. All design values provisional; the "
                     "24 ft plane start of 131.0444 is read from Diagram 131-04L (provisional)."),
        },
        "lots": lots_out,
        "cells": cells_out,
    }


TABLE_FIELDS = ("lot_id", "household_id", "profile", "scheme_id", "floors", "rank", "selection", "strategy_used",
                "status", "governing", "next_stage", "ground_sqft", "upper_sqft", "plate_ft", "top_ft",
                "side_wall", "side_inset_ft", "front_plane_required", "headroom_ft")


def table_rows(result: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for c in result["cells"]:
        h = next(x for x in c["height"] if x["roof_id"] == c["default_roof"])
        levels = c["levels"]
        rows.append({**{k: c.get(k) for k in TABLE_FIELDS if k in c},
                     "ground_sqft": levels[0]["gross_sqft"],
                     "upper_sqft": levels[1]["gross_sqft"] if len(levels) > 1 else 0.0,
                     **{k: h[k] for k in ("plate_ft", "top_ft", "side_wall", "side_inset_ft",
                                          "front_plane_required", "headroom_ft")}})
    return rows


def write_tables(result: dict[str, Any], out_dir: str | Path) -> list[Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / "stack_plan_cells.csv"
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=TABLE_FIELDS)
        writer.writeheader()
        writer.writerows(table_rows(result))
    return [path]


__all__ = ["STAGE", "STEP", "TABLE_FIELDS", "run_stacking", "stack_cell", "table_rows", "write_tables"]
