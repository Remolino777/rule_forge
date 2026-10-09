"""Workflow of the stacking module (step 6.7a): levels, height budget and drawn floors of the 6.6 winners.

    area_matrix (6.6) + lot_capacity of each lot
      -> select the ranked cells (best / top2 / all; per-stage default)
      -> per lot: height envelope (131.0444), floors the height allows, below-grade probe (113.0234, 113.0261)
      -> S0 per cell: levels relative to grade, height check per roof type, status, next stage
      -> S1 per two-floor cell marked next_stage = "S1": ground floor from the strategy's footprint, stand-in
         garage, upper-floor placement, stair at the joint (CRC R311.7), allowed polygon per level, roof of the
         drawn upper floor against the plane (default, ridge turned, flat), room over the garage (R302.6)
      -> result {meta, lots, cells} (contract stack_plan)

Stage S2 (upper-floor zoning) reads the cells marked next_stage = "S2". The workflow only reads contracts: no
lotcap, site or areas code runs here.
"""

from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path
from typing import Any

from spaceplan.core.lib.catalog import load_catalog
from spaceplan.core.lib.contracts import read_contract
from spaceplan.modules.stacking.lib.cell_geometry import DRAWN, S1_STATUSES, draw_cell
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
from spaceplan.modules.stacking.lib.lot_plan import lot_plan, strategy_key
from spaceplan.modules.stacking.lib.lot_vertical import lot_envelope, lot_vertical_facts
from spaceplan.modules.stacking.lib.stacking_catalog import load_stacking_catalog
from spaceplan.modules.stacking.lib.stair_rules import load_stair_ruleset, stair_limits
from spaceplan.modules.stacking.lib.vertical_rules import (
    garage_counts_in_gfa,
    load_vertical_ruleset,
)

STEP, STAGE = "6.7a", "S0"
STAGES = ("S0", "S1")
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


def _s1_summary(cells: list[dict[str, Any]]) -> dict[str, Any]:
    drawn = [c["s1"] for c in cells if c.get("s1") and c["s1"]["status"] == DRAWN]
    return {"cells": sum(1 for c in cells if c.get("s1")),
            "status_counts": dict(sorted(Counter(c["s1"]["status"] for c in cells if c.get("s1")).items())),
            "upper_placement_counts": dict(sorted(Counter(d["upper_placement"] for d in drawn).items())),
            "stair_type_counts": dict(sorted(Counter(d["stair"]["stair_id"] for d in drawn).items())),
            "roof_default_counts": dict(sorted(Counter(d["roof"]["default"] for d in drawn).items())),
            "roof_kept_counts": dict(sorted(Counter(str(d["roof"]["kept"]) for d in drawn).items())),
            "room_over_garage": sum(1 for d in drawn if d["containment"]["room_over_garage"]),
            "to_s2": sum(1 for c in cells if c.get("s1") and c["s1"]["next_stage"] == "S2")}


def _lot_summary(cells: list[dict[str, Any]]) -> dict[str, Any]:
    return {"cells": len(cells),
            "by_floors": dict(sorted(Counter(str(c["floors"]) for c in cells).items())),
            "status_counts": dict(sorted(Counter(c["status"] for c in cells).items())),
            "to_s1": sum(1 for c in cells if c["next_stage"] == "S1" or "s1" in c),
            "max_side_inset_ft": max((h["side_inset_ft"] for c in cells for h in c["height"]
                                      if h["roof_id"] == c["default_roof"]), default=0.0)}


def run_stacking(area_matrix: dict, lot_capacities: dict[str, dict] | list[dict], mode: str | None = None,
                 catalog_path=None, rules_path=None, stacking_catalog_path=None, stage: str = STAGE,
                 stair_rules_path=None) -> dict[str, Any]:
    """Stage S0 (and S1 when `stage` is "S1") over an area_matrix contract and the lot_capacity contracts of its
    lots (by brief_id)."""
    if stage not in STAGES:
        raise ValueError(f"stacking: unknown stage {stage!r}; expected one of {', '.join(STAGES)}")
    am = read_contract(area_matrix, "area_matrix")
    if isinstance(lot_capacities, list):
        lot_capacities = {c["brief_id"]: c for c in lot_capacities}
    lcs = {lot_id: read_contract(c, "lot_capacity") for lot_id, c in lot_capacities.items()}
    rs = load_vertical_ruleset(rules_path)
    scat = load_stacking_catalog(stacking_catalog_path)
    catalog = load_catalog(catalog_path)
    stair_sqft = float(catalog.space_type(scat.stair_space_type)["area"]["target"])
    mode = mode or scat.stage_default_mode(stage)
    selected = select_cells(am["cells"], scat.selection_k(mode))
    srs = load_stair_ruleset(stair_rules_path) if stage == "S1" else None
    limits = stair_limits(srs) if srs is not None else None

    lots_out, cells_out, missing = [], [], []
    for lot in am["lots"]:
        lot_id = lot["budget"]["lot_id"]
        lc = lcs.get(lot_id)
        if lc is None:
            missing.append(lot_id)
            continue
        lot_cells = []
        plan = lot_plan(lc) if stage == "S1" else None
        for c in selected:
            if c["lot_id"] != lot_id:
                continue
            out = stack_cell(c, lot, lc, rs, scat, stair_sqft)
            if plan is not None and out["next_stage"] == "S1":
                s1 = draw_cell(c, out, plan, strategy_key(lot["budget"], c.get("strategy_used")), scat, limits, srs,
                               rs, lot_envelope(rs, lc), (lc.get("terrain") or {}).get("mean_slope"), stair_sqft)
                out["s1"] = s1
                out["next_stage"] = s1["next_stage"]
            lot_cells.append(out)
        cells_out += lot_cells
        summary = _lot_summary(lot_cells)
        facts = lot_vertical_facts(rs, scat, lc)
        if stage == "S1":
            summary["s1"] = _s1_summary(lot_cells)
            facts["plan"] = {"lot_polygon": lc["lot"]["polygon"], "envelope_polygon": lc["capacity"]["envelope"]["polygon"]}
        lots_out.append({**facts, "summary": summary})
    if missing:
        raise ValueError(f"stacking: no lot_capacity contract for lot(s) {', '.join(missing)}")
    meta_s1 = {} if srs is None else {
        "stair_ruleset": srs.ruleset_id, "stair_ruleset_version": srs.version, "stair_ruleset_sha256": srs.sha256,
        "stair_limits": limits.to_dict(), "s1": _s1_summary(cells_out),
        "note_s1": ("Stage S1: ground floor = front band of the strategy's realizable footprint holding the ground "
                    "gross area; stand-in garage on the front line (area from the area matrix); upper floor = rear "
                    "or front band of the ground floor or a garage-anchored rectangle; stair at the joint, same "
                    "rectangle on both levels; roof of the drawn upper floor checked against 131.0444. All design "
                    "values provisional; CRC stair rules unverified.")}
    return {
        "meta": {
            "step": STEP,
            "stage": stage,
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
            **meta_s1,
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


S1_TABLE_FIELDS = ("lot_id", "household_id", "profile", "scheme_id", "rank", "strategy", "s1_status", "next_stage",
                   "upper_placement", "ground_sqft", "ground_width_ft", "ground_depth_ft", "upper_sqft",
                   "garage_sqft", "over_garage_sqft", "stair_id", "stair_area_sqft", "stair_area_delta_sqft",
                   "risers", "riser_in", "s0_status", "roof_default", "roof_kept", "inset_needed_ft")


def s1_table_rows(result: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for c in result["cells"]:
        s1 = c.get("s1")
        if not s1:
            continue
        drawn = s1["status"] == DRAWN
        g = s1.get("ground") or {}
        rows.append({
            "lot_id": c["lot_id"], "household_id": c["household_id"], "profile": c["profile"],
            "scheme_id": c["scheme_id"], "rank": c["rank"], "strategy": s1.get("strategy"),
            "s1_status": s1["status"], "next_stage": c["next_stage"],
            "upper_placement": s1.get("upper_placement"), "ground_sqft": g.get("area_sqft"),
            "ground_width_ft": g.get("width_ft"), "ground_depth_ft": g.get("depth_ft"),
            "upper_sqft": s1["levels"][1]["area_sqft"] if drawn else None, "garage_sqft": g.get("garage_sqft"),
            "over_garage_sqft": s1["containment"]["over_garage_sqft"] if drawn else None,
            "stair_id": s1["stair"]["stair_id"] if drawn else None,
            "stair_area_sqft": s1["stair"]["area_sqft"] if drawn else None,
            "stair_area_delta_sqft": s1["stair"]["area_delta_sqft"] if drawn else None,
            "risers": s1["stair"]["risers"] if drawn else None, "riser_in": s1["stair"]["riser_in"] if drawn else None,
            "s0_status": c["status"], "roof_default": s1["roof"]["default"] if drawn else None,
            "roof_kept": s1["roof"]["kept"] if drawn else None,
            "inset_needed_ft": s1["roof"]["inset_needed_ft"] if drawn else None})
    return rows


def write_tables(result: dict[str, Any], out_dir: str | Path) -> list[Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / "stack_plan_cells.csv"
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=TABLE_FIELDS)
        writer.writeheader()
        writer.writerows(table_rows(result))
    paths = [path]
    rows = s1_table_rows(result)
    if rows:
        path = out / "stack_plan_s1.csv"
        with path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=S1_TABLE_FIELDS)
            writer.writeheader()
            writer.writerows(rows)
        paths.append(path)
    return paths


__all__ = ["S1_STATUSES", "S1_TABLE_FIELDS", "STAGE", "STAGES", "STEP", "TABLE_FIELDS", "run_stacking", "s1_table_rows",
           "stack_cell", "table_rows", "write_tables"]
