"""Workflow of the stacking module (step 6.7a): levels, height budget and drawn floors of the 6.6 winners.

    area_matrix (6.6) + lot_capacity of each lot
      -> select the ranked cells (best / top2 / all; per-stage default)
      -> per lot: height envelope (131.0444), floors the height allows, below-grade probe (113.0234, 113.0261)
      -> S0 per cell: levels relative to grade, height check per roof type, status, next stage
      -> S1 per two-floor cell marked next_stage = "S1": ground floor from the strategy's footprint, stand-in
         garage, upper-floor placement, stair at the joint (CRC R311.7), allowed polygon per level, roof of the
         drawn upper floor against the plane (default, ridge turned, flat), room over the garage (R302.6)
      -> S2 per cell drawn by S1 (next_stage = "S2"): zoning of both floors around the stair core (zone units from
         the area matrix's space split), receiving space at the top (K01), A/B/C start portfolio (K02), half bath
         under the stair or relocated (K03, K04), relation matrix with K05 over the base; when the upper floor
         cannot be zoned, S1 is redrawn with the next upper-floor placement that held the stair (backtrack)
      -> result {meta, lots, cells} (contract stack_plan)

The workflow only reads contracts: no lotcap, site or areas code runs here.
"""

from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path
from typing import Any

from spaceplan.core.lib.catalog import load_catalog
from spaceplan.core.lib.contracts import read_contract
from spaceplan.modules.stacking.lib.cell_geometry import DRAWN, S1_STATUSES, S1Context, draw_cell
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
from spaceplan.modules.stacking.lib.stair_access import load_client_ruleset, relations
from spaceplan.modules.stacking.lib.stair_rules import load_stair_ruleset, stair_limits
from spaceplan.modules.stacking.lib.zone_cell import S2_STATUSES, ZONED, s2_context, zone_cell
from spaceplan.modules.stacking.lib.zone_relations import build_matrix
from spaceplan.modules.stacking.lib.vertical_rules import (
    garage_counts_in_gfa,
    load_vertical_ruleset,
)

STEP, STAGE = "6.7a", "S0"
STAGES = ("S0", "S1", "S2")
DRAWING_STAGES = ("S1", "S2")
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


def backtrack_order(s1: dict[str, Any], stair_ids: list[str]) -> list[tuple[str, str]]:
    """Redraws stage S2 asks S1 for when it cannot zone a cell: every upper placement that held the stair (the drawn
    one first) times every enabled stair configuration (the drawn one first, then the catalog order), minus the
    drawn pair. A configuration that does not fit a placement is reported by S1 and skipped."""
    placements = [s1["upper_placement"]] + [c["placement"] for c in s1.get("upper_candidates", [])
                                            if c["stair_fits"] and c["placement"] != s1["upper_placement"]]
    stairs = [s1["stair"]["stair_id"]] + [sid for sid in stair_ids if sid != s1["stair"]["stair_id"]]
    pairs = [(p, sid) for p in placements for sid in stairs]
    return pairs[1:]


def stage_s2(c: dict[str, Any], out: dict[str, Any], plan, strategy, ctx: S1Context, s2ctx) -> None:
    """Zone a drawn cell; when it does not zone, redraw S1 with the next upper placement or stair configuration
    (backtrack across stages: S2 is the first stage that knows the widths of the rooms)."""
    s1 = out["s1"]
    s2 = zone_cell(c, s1, plan, s2ctx)
    tried = []
    if s2["status"] not in (ZONED, "no_space_split"):
        for placement, stair_id in backtrack_order(s1, [t["stair_id"] for t in ctx.scat.stair_types]):
            redraw = draw_cell(c, out, plan, strategy, ctx, placements=[placement], stair_ids=[stair_id])
            if redraw["status"] != DRAWN:
                tried.append({"placement": placement, "stair_id": stair_id, "s1_status": redraw["status"]})
                continue
            alt = zone_cell(c, redraw, plan, s2ctx)
            tried.append({"placement": placement, "stair_id": stair_id, "s2_status": alt["status"]})
            if alt["status"] == ZONED:
                redraw["upper_candidates"] = s1["upper_candidates"]
                redraw["redrawn_by_s2"] = {"from_placement": s1["upper_placement"], "to_placement": placement,
                                           "from_stair": s1["stair"]["stair_id"], "to_stair": stair_id,
                                           "reason": f"{s2['status']} with the {s1['upper_placement']} placement and "
                                                     f"the {s1['stair']['stair_id']} stair"}
                out["s1"], s2 = redraw, alt
                break
    s2["backtrack"] = {"tried": tried, "placement": out["s1"]["upper_placement"],
                       "stair_id": out["s1"]["stair"]["stair_id"], "redrawn": "redrawn_by_s2" in out["s1"]}
    out["s2"] = s2
    out["next_stage"] = s2["next_stage"]


def _s2_summary(cells: list[dict[str, Any]]) -> dict[str, Any]:
    zoned = [c["s2"] for c in cells if c.get("s2") and c["s2"]["status"] == ZONED]
    return {"cells": sum(1 for c in cells if c.get("s2")),
            "status_counts": dict(sorted(Counter(c["s2"]["status"] for c in cells if c.get("s2")).items())),
            "arrival_counts": dict(sorted(Counter(z["arrival"]["receiving"] for z in zoned).items())),
            "chosen_option_counts": dict(sorted(Counter(z["chosen_option"] for z in zoned).items())),
            "feasible_option_counts": {o: sum(1 for z in zoned if o in z["feasible_options"]) for o in "ABC"},
            "half_bath_counts": dict(sorted(Counter(str(z["options"][z["chosen_option"]].get("half_bath"))
                                                    for z in zoned).items())),
            "redrawn_by_s2": sum(1 for c in cells if c.get("s2") and c["s2"]["backtrack"]["redrawn"]),
            "redrawn_stair_changed": sum(1 for c in cells if c.get("s2") and c["s2"]["backtrack"]["redrawn"]
                                         and c["s1"]["redrawn_by_s2"]["from_stair"] != c["s1"]["redrawn_by_s2"]["to_stair"]),
            "stair_type_counts": dict(sorted(Counter(c["s1"]["stair"]["stair_id"] for c in cells
                                                     if c.get("s2") and c["s2"]["status"] == ZONED).items())),
            "upper_placement_counts": dict(sorted(Counter(c["s1"]["upper_placement"] for c in cells
                                                          if c.get("s2") and c["s2"]["status"] == ZONED).items())),
            "to_s2_1": sum(1 for c in cells if c.get("s2") and c["s2"]["next_stage"])}


def _lot_summary(cells: list[dict[str, Any]]) -> dict[str, Any]:
    return {"cells": len(cells),
            "by_floors": dict(sorted(Counter(str(c["floors"]) for c in cells).items())),
            "status_counts": dict(sorted(Counter(c["status"] for c in cells).items())),
            "to_s1": sum(1 for c in cells if c["next_stage"] == "S1" or "s1" in c),
            "max_side_inset_ft": max((h["side_inset_ft"] for c in cells for h in c["height"]
                                      if h["roof_id"] == c["default_roof"]), default=0.0)}


def run_stacking(area_matrix: dict, lot_capacities: dict[str, dict] | list[dict], mode: str | None = None,
                 catalog_path=None, rules_path=None, stacking_catalog_path=None, stage: str = STAGE,
                 stair_rules_path=None, client_rules_path=None) -> dict[str, Any]:
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
    drawing = stage in DRAWING_STAGES
    srs = load_stair_ruleset(stair_rules_path) if drawing else None
    limits = stair_limits(srs) if srs is not None else None
    crs = load_client_ruleset(client_rules_path) if drawing else None
    s2ctx = (s2_context(scat, catalog, crs, build_matrix(catalog, relations(crs), scat.s2["pair_default_weights"]))
             if stage == "S2" else None)

    lots_out, cells_out, missing = [], [], []
    for lot in am["lots"]:
        lot_id = lot["budget"]["lot_id"]
        lc = lcs.get(lot_id)
        if lc is None:
            missing.append(lot_id)
            continue
        lot_cells = []
        plan = lot_plan(lc) if drawing else None
        for c in selected:
            if c["lot_id"] != lot_id:
                continue
            out = stack_cell(c, lot, lc, rs, scat, stair_sqft)
            if plan is not None and out["next_stage"] == "S1":
                ctx = S1Context(scat, limits, srs, rs, crs, catalog, lot_envelope(rs, lc),
                                (lc.get("terrain") or {}).get("mean_slope"), stair_sqft)
                strategy = strategy_key(lot["budget"], c.get("strategy_used"))
                s1 = draw_cell(c, out, plan, strategy, ctx)
                out["s1"] = s1
                out["next_stage"] = s1["next_stage"]
                if s2ctx is not None and s1["next_stage"] == "S2":
                    stage_s2(c, out, plan, strategy, ctx, s2ctx)
            lot_cells.append(out)
        cells_out += lot_cells
        summary = _lot_summary(lot_cells)
        facts = lot_vertical_facts(rs, scat, lc)
        if drawing:
            summary["s1"] = _s1_summary(lot_cells)
            facts["plan"] = {"lot_polygon": lc["lot"]["polygon"], "envelope_polygon": lc["capacity"]["envelope"]["polygon"]}
        if s2ctx is not None:
            summary["s2"] = _s2_summary(lot_cells)
        lots_out.append({**facts, "summary": summary})
    if missing:
        raise ValueError(f"stacking: no lot_capacity contract for lot(s) {', '.join(missing)}")
    meta_s1 = {} if srs is None else {
        "stair_ruleset": srs.ruleset_id, "stair_ruleset_version": srs.version, "stair_ruleset_sha256": srs.sha256,
        "client_ruleset": crs.ruleset_id, "client_ruleset_version": crs.version, "client_ruleset_sha256": crs.sha256,
        "stair_limits": limits.to_dict(), "s1": _s1_summary(cells_out),
        "note_s1": ("Stage S1: ground floor = front band of the strategy's realizable footprint holding the ground "
                    "gross area; stand-in garage on the front line (area from the area matrix); upper floor = rear "
                    "or front band of the ground floor or a garage-anchored rectangle; stair at the joint, same "
                    "rectangle on both levels; roof of the drawn upper floor checked against 131.0444. All design "
                    "values provisional; CRC stair rules unverified.")}
    if s2ctx is not None:
        meta_s1.update({
            "s2": _s2_summary(cells_out),
            "relation_overrides": list(s2ctx.matrix.overrides),
            "note_s2": ("Stage S2: zone units of each floor from the area matrix's space split, placed by a band/column "
                        "enumerator around the stair core (grid cuts by area, the receiving unit pinned on the stair's "
                        "arrival zone); zone-level doors, entry, K01 arrival, K04 vestibule, house anchors and hard "
                        "matrix pairs (K05 over the base) are hard; relations, shape, anchors and stair access are "
                        "scored. Start options A/B/C kept as a portfolio. Design values provisional.")})
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


S2_TABLE_FIELDS = ("lot_id", "household_id", "profile", "scheme_id", "rank", "s2_status", "next_stage", "arrival",
                   "upper_rooms", "chosen_option", "feasible_options", "A", "B", "C", "half_bath", "upper_placement",
                   "redrawn", "upper_units", "upper_topology", "upper_landing_unit", "ground_units", "ground_topology",
                   "ground_landing_unit", "entry_unit", "score", "upper_score", "ground_score", "vertical_score",
                   "upper_first_violations")


def _topology_label(block: dict[str, Any] | None) -> str | None:
    if not block:
        return None
    t = block["topology"]
    return t["axis"] + ":" + " / ".join("|".join(band) for band in t["bands"])


def s2_table_rows(result: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for c in result["cells"]:
        s2 = c.get("s2")
        if not s2:
            continue
        chosen = s2.get("chosen_option")
        g = s2["options"][chosen]["ground"] if chosen else None
        u = s2.get("upper")
        rows.append({
            "lot_id": c["lot_id"], "household_id": c["household_id"], "profile": c["profile"],
            "scheme_id": c["scheme_id"], "rank": c["rank"], "s2_status": s2["status"], "next_stage": c["next_stage"],
            "arrival": (s2.get("arrival") or {}).get("receiving"), "upper_rooms": (s2.get("arrival") or {}).get("upper_rooms"),
            "chosen_option": chosen, "feasible_options": ",".join(s2.get("feasible_options") or []),
            **{o: (s2.get("options", {}).get(o) or {}).get("feasible") for o in ("A", "B", "C")},
            "half_bath": s2["options"][chosen].get("half_bath") if chosen else None,
            "upper_placement": c["s1"]["upper_placement"], "redrawn": s2.get("backtrack", {}).get("redrawn"),
            "upper_units": len(u["units"]) if u else None, "upper_topology": _topology_label(u),
            "upper_landing_unit": u["landing_unit"] if u else None,
            "ground_units": len(g["units"]) if g else None, "ground_topology": _topology_label(g),
            "ground_landing_unit": g["landing_unit"] if g else None, "entry_unit": g["entry_unit"] if g else None,
            "score": s2.get("score"), "upper_score": u["score"] if u else None, "ground_score": g["score"] if g else None,
            "vertical_score": (s2.get("vertical") or {}).get("score"),
            "upper_first_violations": None if u else str((s2.get("upper_search") or {}).get("first_violations"))})
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
    rows = s2_table_rows(result)
    if rows:
        path = out / "stack_plan_s2.csv"
        with path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=S2_TABLE_FIELDS)
            writer.writeheader()
            writer.writerows(rows)
        paths.append(path)
    return paths


__all__ = ["S1_STATUSES", "S1_TABLE_FIELDS", "S2_STATUSES", "S2_TABLE_FIELDS", "backtrack_order", "s2_table_rows",
           "stage_s2", "STAGE", "STAGES", "STEP", "TABLE_FIELDS", "run_stacking", "s1_table_rows",
           "stack_cell", "table_rows", "write_tables"]
