"""Balanced split between floors (step 9a, 2026-10-10): the ground floor of a two-floor house must fit the
design footprint (FOS x base, client variable D01).

The vertical schemes of step 6.6 send fixed groups upstairs (bedrooms, guest, work). When the ground floor
still exceeds the design footprint, the catalog rule `vertical_schemes.ground_balance` moves more spaces up,
one at a time and in its order (family room first: it is the stair arrival room of S1.1), until the ground
floor fits. Hard rules are kept: a space with a floor preference (mobility, garage) never moves, hosted
spaces move with their host, the zones and types in `never_move` stay down, and the upper floor never
becomes larger than the ground floor. Every move is recorded as an exception of the split.

When no balanced split fits, the maximum is trimmed: the largest step of the expansion curve that fits
(`maximum_fits`, used by the profiles layer). Areas only, no geometry.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from spaceplan.core.lib.catalog import Catalog
from spaceplan.modules.areas.lib.vertical_split import (
    ENTRY_FLOOR,
    FloorSplit,
    applicable_schemes,
    build_split,
    has_empty_upper,
    program_group_facts,
    space_matches,
    split_program,
)

TOL = 1e-6
DESIGN_FOOTPRINT_GROUND = "design_footprint_ground"
BALANCE_KIND = "ground_balance"


def _blocked(rule: dict, space: dict) -> bool:
    never = rule.get("never_move") or {}
    return any(space.get(k) in v for k, v in never.items())


def balance_split(catalog: Catalog, program: dict, split: FloorSplit, footprint_sqft: float | None) -> FloorSplit:
    """The split itself when its ground floor fits (or it has one floor); otherwise the split after moving
    spaces up in the order of the catalog rule until it fits (or the movable spaces run out)."""
    if split.floors < 2 or footprint_sqft is None or split.ground <= footprint_sqft + TOL:
        return split
    rule = catalog.data["vertical_schemes"]["ground_balance"]
    spaces = {s["space_id"]: s for s in program["spaces"]}
    upper = split.floors - 1
    floor_of = dict(split.floor_of)
    exceptions = list(split.exceptions)
    current = split
    for step in rule["order"]:
        movable = [sid for sid, s in spaces.items()
                   if floor_of.get(sid) == ENTRY_FLOOR and not s.get("host_space_id")
                   and s.get("floor_preference") is None and not _blocked(rule, s)
                   and space_matches(step["match"], s)]
        for sid in sorted(movable, key=lambda m: (-float(spaces[m]["target_area_sqft"]), m)):
            moved = [sid] + sorted(h for h, s in spaces.items() if s.get("host_space_id") == sid)
            trial = {**floor_of, **{m: upper for m in moved}}
            candidate = build_split(catalog, program, split.scheme_id, split.floors, trial, split.group_of,
                                    exceptions)
            if candidate.upper > candidate.ground + TOL:
                continue
            exceptions.append({"kind": BALANCE_KIND, "rule_id": rule["rule_id"], "space_id": sid, "group": split.group_of[sid], "to_floor": upper, "moved": moved,
                               "reason": f"{rule['rule_id']}: ground floor {current.ground:.0f} sq ft over the "
                                         f"design footprint {footprint_sqft:.0f} sq ft ({step['step']} goes up)"})
            floor_of = trial
            current = build_split(catalog, program, split.scheme_id, split.floors, floor_of, split.group_of,
                                  exceptions)
            if current.ground <= footprint_sqft + TOL:
                return current
    return current


def balanced(split: FloorSplit) -> list[str]:
    """Spaces the balance rule moved up (empty when the scheme fitted as it was)."""
    return [e["space_id"] for e in split.exceptions if e.get("kind") == BALANCE_KIND]


def fits_ground(split: FloorSplit, footprint_sqft: float) -> bool:
    return split.ground <= footprint_sqft + TOL and (split.floors == 1 or split.upper <= split.ground + TOL)


def two_floor_fits(catalog: Catalog, facts: dict[str, Any], footprint_sqft: float) -> Callable[[dict], bool]:
    """Predicate over a program: some applicable two-floor scheme, balanced, keeps the ground floor inside the
    design footprint without degenerating (something worth climbing for stays upstairs)."""
    vs = catalog.data["vertical_schemes"]

    def fits(program: dict) -> bool:
        f = {**facts, **program_group_facts(vs, program)}
        for scheme in applicable_schemes(vs, f):
            if scheme["floors"] < 2:
                continue
            sp = balance_split(catalog, program, split_program(catalog, program, scheme, f), footprint_sqft)
            if fits_ground(sp, footprint_sqft) and not has_empty_upper(catalog, sp):
                return True
        return False

    return fits


NEUTRAL_LOT_FACTS = {"steep_hillside_fraction": 0.0, "view_side": "none"}


def min_ground(catalog: Catalog, program: dict, facts: dict[str, Any]) -> float | None:
    """Smallest ground floor any applicable two-floor scheme reaches once every movable space is up (balance
    against a zero footprint), without degenerating; None when the program has no two-floor scheme. Lot-free
    when `facts` carries no lot facts (NEUTRAL_LOT_FACTS): used by the normative sensitivity."""
    vs = catalog.data["vertical_schemes"]
    f = {**NEUTRAL_LOT_FACTS, **facts, **program_group_facts(vs, program)}
    grounds = []
    for scheme in applicable_schemes(vs, f):
        if scheme["floors"] < 2:
            continue
        sp = balance_split(catalog, program, split_program(catalog, program, scheme, f), 0.0)
        if not has_empty_upper(catalog, sp) and sp.upper <= sp.ground + TOL:
            grounds.append(sp.ground)
    return round(min(grounds), 1) if grounds else None


def one_floor_fits(catalog: Catalog, footprint_sqft: float) -> Callable[[dict], bool]:
    """Predicate over a program: on one floor its gross area fits the design footprint."""
    vs = catalog.data["vertical_schemes"]
    one = next(s for s in vs["schemes"] if s["floors"] == 1)

    def fits(program: dict) -> bool:
        return fits_ground(split_program(catalog, program, one, {}), footprint_sqft)

    return fits


__all__ = ["BALANCE_KIND", "DESIGN_FOOTPRINT_GROUND", "NEUTRAL_LOT_FACTS", "balance_split", "balanced", "fits_ground", "min_ground", "one_floor_fits",
           "two_floor_fits"]
