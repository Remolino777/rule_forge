"""Workflow of the stacking module (step 6.7a): levels, height budget and drawn floors of the 6.6 winners.

    area_matrix (6.6) + lot_capacity of each lot
      -> select the ranked cells (best / top2 / all; per-stage default)
      -> per lot: height envelope (131.0444), floors the height allows, below-grade probe (113.0234, 113.0261)
      -> S0 per cell: levels relative to grade, height check per roof type, status, next stage
      -> S1 per two-floor cell marked next_stage = "S1" (stage S1.2: the stair from the main door): ground floor from
         the strategy's footprint, garage on the driveway side of the site plan
         garage, upper-floor placement, stair at the joint (CRC R311.7), allowed polygon per level, roof of the
         drawn upper floor against the plane (default, ridge turned, flat), room over the garage (R302.6)
      -> S2 per cell drawn by S1 (next_stage = "S2"): zoning of both floors around the stair core (zone units from
         the area matrix's space split), receiving space at the top (K01), A/B/C start portfolio (K02), half bath
         under the stair or relocated (K03, K04), relation matrix with K05 over the base; when the upper floor
         is chosen among the S1 candidates in three levels (hard rules, route tolerance, client preferences)
      -> result {meta, lots, cells} (contract stack_plan)

The workflow only reads contracts: no lotcap, site or areas code runs here.
"""

from __future__ import annotations

import csv
from dataclasses import replace
from collections import Counter

from shapely.geometry import shape
from pathlib import Path
from typing import Any

from spaceplan.core.lib.catalog import load_catalog
from spaceplan.core.lib.rules import load_ruleset
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
from spaceplan.modules.stacking.lib.program_adjust import adjust_program
from spaceplan.modules.stacking.lib.space_cell import NO_VALID_LAYOUT, NOT_EVALUATED_S21, SPACED, S21Context, space_cell
from spaceplan.core.lib_aux.hashing import sha256_of
from spaceplan.modules.design.lib.design_registry import load_registry
from spaceplan.modules.stacking.lib.space_rules import (
    design_view,
    load_crc_ruleset,
    load_openings_ruleset,
    space_rules,
)
from spaceplan.modules.stacking.lib.stacking_catalog import load_stacking_catalog
from spaceplan.modules.stacking.lib.stair_access import load_client_ruleset, relations
from spaceplan.modules.stacking.lib.stair_rules import load_stair_ruleset, stair_limits
from spaceplan.modules.stacking.lib.access_cell import access_context, stage_s1, stage_s2
from spaceplan.modules.stacking.lib.zone_cell import S2_STATUSES, ZONED, s2_context
from spaceplan.modules.stacking.lib.zone_relations import build_matrix
from spaceplan.modules.stacking.lib.vertical_rules import (
    garage_counts_in_gfa,
    load_vertical_ruleset,
)

STEP, STAGE = "6.7a", "S0"
STAGES = ("S0", "S1", "S2", "S2.1")
DRAWING_STAGES = ("S1", "S2", "S2.1")
ZONING_STAGES = ("S2", "S2.1")
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


def _s2_summary(cells: list[dict[str, Any]]) -> dict[str, Any]:
    zoned = [c["s2"] for c in cells if c.get("s2") and c["s2"]["status"] == ZONED]
    return {"cells": sum(1 for c in cells if c.get("s2")),
            "status_counts": dict(sorted(Counter(c["s2"]["status"] for c in cells if c.get("s2")).items())),
            "arrival_counts": dict(sorted(Counter(z["arrival"]["receiving"] for z in zoned).items())),
            "chosen_option_counts": dict(sorted(Counter(z["chosen_option"] for z in zoned).items())),
            "feasible_option_counts": {o: sum(1 for z in zoned if o in z["feasible_options"]) for o in "ABC"},
            "half_bath_counts": dict(sorted(Counter(str(z["options"][z["chosen_option"]].get("half_bath"))
                                                    for z in zoned).items())),
            "strategy_counts": dict(sorted(Counter((c["s2"].get("stair_choice") or {}).get("chosen", {}).get("strategy")
                                                   for c in cells if c.get("s2") and c["s2"]["status"] == ZONED
                                                   and (c["s2"].get("stair_choice") or {}).get("chosen")).items())),
            "light_counts": dict(sorted(Counter(((c["s2"].get("stair_choice") or {}).get("chosen") or {}).get("light")
                                                for c in cells if c.get("s2") and c["s2"]["status"] == ZONED).items(),
                                        key=lambda kv: str(kv[0]))),
            "stair_type_counts": dict(sorted(Counter(c["s1"]["stair"]["stair_id"] for c in cells
                                                     if c.get("s2") and c["s2"]["status"] == ZONED).items())),
            "upper_placement_counts": dict(sorted(Counter(c["s1"]["upper_placement"] for c in cells
                                                          if c.get("s2") and c["s2"]["status"] == ZONED).items())),
            "to_s2_1": sum(1 for c in cells if c.get("s2") and c["s2"]["next_stage"])}


def _s21_summary(cells: list[dict[str, Any]]) -> dict[str, Any]:
    blocks = [c["s21"] for c in cells if c.get("s21")]
    spaced = [b for b in blocks if b["status"] == SPACED]
    return {"cells": len(blocks),
            "status_counts": dict(sorted(Counter(b["status"] for b in blocks).items())),
            "stair_rank_counts": dict(sorted(Counter(str(b.get("stair_rank")) for b in spaced).items())),
            "first_violation_counts": dict(Counter(b.get("first_violation") for b in blocks
                                                   if b["status"] == NO_VALID_LAYOUT).most_common(12)),
            "failed_floor_counts": dict(sorted(Counter(b.get("failed_floor") for b in blocks
                                                       if b["status"] == NO_VALID_LAYOUT).items())),
            "doors": sum(len(b[f]["doors"]) for b in spaced for f in ("ground", "upper")),
            "closets_from_leftovers": sum(1 for b in spaced for f in ("ground", "upper") for sp in b[f]["spaces"]
                                          if sp["synthetic"] and sp["space_type"] == "closet")}


def _lot_summary(cells: list[dict[str, Any]]) -> dict[str, Any]:
    return {"cells": len(cells),
            "by_floors": dict(sorted(Counter(str(c["floors"]) for c in cells).items())),
            "status_counts": dict(sorted(Counter(c["status"] for c in cells).items())),
            "to_s1": sum(1 for c in cells if c["next_stage"] == "S1" or "s1" in c),
            "max_side_inset_ft": max((h["side_inset_ft"] for c in cells for h in c["height"]
                                      if h["roof_id"] == c["default_roof"]), default=0.0)}


def run_stacking(area_matrix: dict, lot_capacities: dict[str, dict] | list[dict], mode: str | None = None,
                 catalog_path=None, rules_path=None, stacking_catalog_path=None, stage: str = STAGE,
                 stair_rules_path=None, client_rules_path=None,
                 site_plans: dict[str, dict] | list[dict] | None = None,
                 design_profile: dict[str, Any] | None = None) -> dict[str, Any]:
    """Stage S0 (and S1, S2 by `stage`) over an area_matrix contract and the lot_capacity contracts of its lots (by
    brief_id). S1 and S2 place the stair from the main door (stage S1.2): the site_plan contract of each lot gives
    the entry deck and the driveway side; without it the door is centred on the free front (flagged)."""
    if stage not in STAGES:
        raise ValueError(f"stacking: unknown stage {stage!r}; expected one of {', '.join(STAGES)}")
    am = read_contract(area_matrix, "area_matrix")
    if isinstance(lot_capacities, list):
        lot_capacities = {c["brief_id"]: c for c in lot_capacities}
    lcs = {lot_id: read_contract(c, "lot_capacity") for lot_id, c in lot_capacities.items()}
    if isinstance(site_plans, list):
        site_plans = {c["brief_id"]: c for c in site_plans}
    sites = {lot_id: read_contract(c, "site_plan") for lot_id, c in (site_plans or {}).items()}
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
             if stage in ZONING_STAGES else None)
    s21ctx = None
    if stage == "S2.1":
        s2ctx = replace(s2ctx, alternatives=int(scat.s21["search"]["s2_alternatives"]))
        crc, openings = load_crc_ruleset(), load_openings_ruleset()
        s21ctx = S21Context(scat, catalog, s2ctx.matrix,
                            space_rules(scat, catalog, crc, openings, srs, crs, design_view(design_profile)), crc,
                            openings, srs, crs, load_ruleset())
    actx = access_context(scat, limits, crs) if drawing else None

    lots_out, cells_out, missing = [], [], []
    for lot in am["lots"]:
        lot_id = lot["budget"]["lot_id"]
        lc = lcs.get(lot_id)
        if lc is None:
            missing.append(lot_id)
            continue
        lot_cells = []
        plan = lot_plan(lc) if drawing else None
        lot_local = plan.frame.to_local(shape(lc["lot"]["polygon"])) if drawing else None
        site = sites.get(lot_id)
        for c in selected:
            if c["lot_id"] != lot_id:
                continue
            adjustment = None
            if s21ctx is not None:               # stage S2.1: corridor allowance and baths per bedroom (K10)
                c, adjustment = adjust_program(c, lot["budget"].get("far_gross_max_sqft"), catalog, scat, crs)
            out = stack_cell(c, lot, lc, rs, scat, stair_sqft)
            if adjustment is not None and adjustment.get("applied"):
                out["program_adjustment"] = adjustment
            if plan is not None and out["next_stage"] == "S1":
                cant = scat.data["upper_floor"].get("cantilever") or {}
                ctx = S1Context(scat, limits, srs, rs, crs, catalog, lot_envelope(rs, lc),
                                (lc.get("terrain") or {}).get("mean_slope"), stair_sqft,
                                float(cant.get("depth_ft", 0.0)) if stage in cant.get("stages", []) else 0.0)
                strategy = strategy_key(lot["budget"], c.get("strategy_used"))
                s0 = dict(out)
                s1, pool = stage_s1(c, s0, plan, strategy, ctx, actx, site, lot_local)
                if site is None and s1.get("access_core") is not None:
                    s1["warnings"] = s1.get("warnings", []) + ["no site_plan: main door centred on the free front"]
                out["s1"] = s1
                out["next_stage"] = s1["next_stage"]
                if s2ctx is not None and s1["next_stage"] == "S2":
                    refine = None
                    if s21ctx is not None:
                        def refine(s1_block, s2_block, c=c, plan=plan, lot_local=lot_local, site=site):
                            return space_cell(c.get("space_split") or [], s1_block, s2_block, plan, c["profile"],
                                              s21ctx, lot_local, site, c.get("culture"))
                    stage_s2(c, s0, out, plan, strategy, ctx, s2ctx, actx, pool, refine,
                             int(scat.s21["fallback"]["max_candidates"]) if s21ctx is not None else None)
                    if s21ctx is not None and "s21" not in out:
                        out["s21"] = {"stage": "S2.1", "status": NOT_EVALUATED_S21, "warnings": [],
                                      "rule_traces": [], "reason": "no zoned stair candidate"}
            lot_cells.append(out)
        cells_out += lot_cells
        summary = _lot_summary(lot_cells)
        facts = lot_vertical_facts(rs, scat, lc)
        if drawing:
            summary["s1"] = _s1_summary(lot_cells)
            facts["plan"] = {"lot_polygon": lc["lot"]["polygon"], "envelope_polygon": lc["capacity"]["envelope"]["polygon"]}
        if s2ctx is not None:
            summary["s2"] = _s2_summary(lot_cells)
        if s21ctx is not None:
            summary["s21"] = _s21_summary(lot_cells)
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
    if s21ctx is not None:
        meta_s1.update({
            "s21": _s21_summary(cells_out),
            "openings_ruleset": s21ctx.openings.ruleset_id, "openings_ruleset_version": s21ctx.openings.version,
            "openings_ruleset_sha256": s21ctx.openings.sha256,
            "design_registry_version": load_registry().version,
            "design_profile_id": (design_profile or {}).get("profile_id", "baseline"),
            "design_profile_sha256": sha256_of(design_profile or {}),
            "note_s21": ("Stage S2.1: spaces of each S2 zone unit as guillotine rectangles on the S2 grid (halls along "
                         "a side, rooms in bands facing the corridor, closets from leftovers), doors with position, "
                         "width, swing and hinge; C01, C06, O01 (escape), O02 (garage openings), O03 (habitable rooms "
                         "on the facade), S08 and K01, K02, K04, K05 hard; the chosen stair candidate first, then the "
                         "next ranked ones. Design values provisional; CRC values unverified.")})
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
                   "strategy", "stair_id", "light", "route_ft", "occupied_sqft", "upper_units", "upper_topology", "upper_landing_unit", "ground_units", "ground_topology",
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
            "upper_placement": c["s1"]["upper_placement"],
            **{k: ((s2.get("stair_choice") or {}).get("chosen") or {}).get(k)
               for k in ("strategy", "stair_id", "light", "route_ft", "occupied_sqft")},
            "upper_units": len(u["units"]) if u else None, "upper_topology": _topology_label(u),
            "upper_landing_unit": u["landing_unit"] if u else None,
            "ground_units": len(g["units"]) if g else None, "ground_topology": _topology_label(g),
            "ground_landing_unit": g["landing_unit"] if g else None, "entry_unit": g["entry_unit"] if g else None,
            "score": s2.get("score"), "upper_score": u["score"] if u else None, "ground_score": g["score"] if g else None,
            "vertical_score": (s2.get("vertical") or {}).get("score"),
            "upper_first_violations": None if u else str((s2.get("upper_search") or {}).get("first_violations"))})
    return rows


S21_TABLE_FIELDS = ("lot_id", "household_id", "profile", "scheme_id", "rank", "s21_status", "stair_rank", "tries",
                    "failed_floor", "first_violation", "s2_alternative_ground", "s2_alternative_upper", "score",
                    "ground_spaces", "upper_spaces", "doors", "closets_from_leftovers", "closets_in_rooms",
                    "suite_depth_from_entry", "circulation_fraction_ground", "circulation_fraction_upper")


def s21_table_rows(result: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for c in result["cells"]:
        b = c.get("s21")
        if not b:
            continue
        ok = b["status"] == SPACED
        floors = [b[f] for f in ("ground", "upper")] if ok else []
        alt = b.get("s2_alternative") or {}
        rows.append({
            "lot_id": c["lot_id"], "household_id": c["household_id"], "profile": c["profile"],
            "scheme_id": c["scheme_id"], "rank": c["rank"], "s21_status": b["status"],
            "stair_rank": b.get("stair_rank"), "tries": len(b.get("attempts", [])),
            "failed_floor": b.get("failed_floor"), "first_violation": b.get("first_violation"),
            "s2_alternative_ground": alt.get("ground"), "s2_alternative_upper": alt.get("upper"),
            "score": b.get("score"),
            "ground_spaces": len(b["ground"]["spaces"]) if ok else None,
            "upper_spaces": len(b["upper"]["spaces"]) if ok else None,
            "doors": sum(len(f["doors"]) for f in floors) if ok else None,
            "closets_from_leftovers": sum(1 for f in floors for sp in f["spaces"]
                                          if sp["synthetic"] and sp["space_type"] == "closet") if ok else None,
            "closets_in_rooms": sum(len(f.get("closets_in_rooms", [])) for f in floors) if ok else None,
            "suite_depth_from_entry": (b.get("depth") or {}).get("primary_suite_from_entry"),
            "circulation_fraction_ground": (b.get("score_parts") or {}).get("ground", {}).get("circulation_fraction"),
            "circulation_fraction_upper": (b.get("score_parts") or {}).get("upper", {}).get("circulation_fraction")})
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
    rows = s21_table_rows(result)
    if rows:
        path = out / "stack_plan_s21.csv"
        with path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=S21_TABLE_FIELDS)
            writer.writeheader()
            writer.writerows(rows)
        paths.append(path)
    return paths


__all__ = ["S1_STATUSES", "S1_TABLE_FIELDS", "S21_TABLE_FIELDS", "S2_STATUSES", "S2_TABLE_FIELDS", "s21_table_rows",
           "s2_table_rows", "STAGE", "STAGES", "STEP", "TABLE_FIELDS", "run_stacking", "s1_table_rows",
           "stack_cell", "table_rows", "write_tables"]
