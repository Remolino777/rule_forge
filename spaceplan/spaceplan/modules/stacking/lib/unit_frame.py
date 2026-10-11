"""What stage S2.1 subdivides on each floor (step 6.7a S2.1): the S2 zone units on the grid, their spaces and the
fixed objects that become nodes of the door graph.

Read only from the stack_plan blocks of a cell (S1 geometry, the S2 floor blocks of the chosen option) and the
area matrix's space split; the floor is rasterized on the S2 grid with the same fixed objects as S2:

  * ground: garage, stair, half bath under the stair and its vestibule (half-bath variant), main-door vestibule;
  * upper: stair opening, interior void (strategy C; not a node, not a facade).

Each free cell belongs to the zone unit whose S2 polygon holds its centre (slivers take a neighbour's unit). The
spaces of a unit come from the unit's space ids; a circulation unit without a foyer or hall gets a synthetic hall
that takes what its other spaces leave.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
from shapely.geometry import shape

from spaceplan.modules.stacking.lib.floor_frame import (
    FIXED_ENTRY,
    FIXED_GARAGE,
    FIXED_HALF_BATH,
    FIXED_STAIR,
    FIXED_VESTIBULE,
    FIXED_VOID,
    GROUND,
    HALF_BATH_USE,
    CellFloors,
    ground_fixed,
    upper_fixed,
)
from spaceplan.modules.stacking.lib.lot_plan import LotPlan
from spaceplan.modules.stacking.lib.space_rules import ACCESSIBLE_PROFILE, SpaceRules
from spaceplan.modules.stacking.lib.zone_relations import ENTRY, STAIR_BOTTOM, STAIR_TOP, ZoneMatrix
from spaceplan.modules.stacking.lib_aux.space_grid import fill_unassigned, mask_bounds
from spaceplan.modules.stacking.lib_aux.zone_grid import OUTSIDE, Grid, cells_of, rasterize

OUT, UNASSIGNED, VOID = -1, -2, -3                 # negative codes of the node-label grid
CIRCULATION_TYPES = ("foyer", "hall")
ENTRY_TYPE, VESTIBULE_TYPE, STAIR_TYPE = "entry_vestibule", "vestibule", "stair"
UNDER_STAIR = "@under_stair"
FIXED_KINDS = {FIXED_ENTRY: ENTRY_TYPE, FIXED_VESTIBULE: VESTIBULE_TYPE, FIXED_STAIR: STAIR_TYPE}


@dataclass(frozen=True)
class SpaceSpec:
    """One space to place inside a unit (or a fixed node of the floor)."""

    space_id: str
    space_type: str
    zone: str
    unit_id: str | None
    target_sqft: float
    min_sqft: float
    min_side_ft: float
    habitable: bool
    passable: bool
    circulation: bool
    roles: frozenset[str]
    host: str | None = None
    fixed: bool = False
    synthetic: bool = False


@dataclass
class UnitFrame:
    index: int
    unit_id: str
    zone: str
    mask: np.ndarray                     # free cells of the unit (whole-floor shape)
    box: tuple[int, int, int, int]
    specs: list[SpaceSpec]

    @property
    def cells(self) -> int:
        return int(self.mask.sum())


@dataclass
class SpaceFloor:
    """One floor of a zoned cell, ready for stage S2.1."""

    level: int
    grid: Grid
    base: np.ndarray                     # node labels of the fixed nodes; OUT / VOID / UNASSIGNED elsewhere
    fixed: list[SpaceSpec]               # fixed nodes, index = label in `base`
    units: list[UnitFrame]
    landing: np.ndarray                  # cells of the stair end zone on this floor
    stair: np.ndarray                    # cells of the stair footprint
    receiving: tuple[str, ...]           # space types allowed to receive the stair end (K01 / K02)
    accessible: bool
    variant: str
    notes: list[str] = field(default_factory=list)
    links: dict[str, set] = field(default_factory=dict)      # S2 door links between zone units

    @property
    def res(self) -> float:
        return self.grid.res

    @property
    def outside(self) -> np.ndarray:
        return self.base == OUT


# ------------------------------------------------------------------ specs


def d_pair(matrix: ZoneMatrix, a: SpaceSpec, b: SpaceSpec) -> bool:
    """Do the two spaces hold the roles of a D pair of the matrix?"""
    for p in matrix.pairs:
        if p.type == "D" and ((p.a in a.roles and p.b in b.roles) or (p.a in b.roles and p.b in a.roles)):
            return True
    return False


def roles_of(matrix: ZoneMatrix, space_type: str) -> frozenset[str]:
    return frozenset(r for r, types in matrix.roles.items() if space_type in types)


def spec_of(catalog, rules: SpaceRules, matrix: ZoneMatrix, row: dict[str, Any], unit_id: str | None,
            target: float | None = None, fixed: bool = False) -> SpaceSpec:
    st = row["space_type"]
    t = catalog.space_type(st) if catalog.has_space_type(st) else {}
    habitable = bool(t.get("habitable"))
    tol = float(rules.s21["layout"]["target_tolerance_fraction"])
    side_tol = float(rules.s21["layout"]["side_tolerance_fraction"])
    min_side = float(t.get("min_side_ft", rules.closet_min_side_ft)) * (1.0 - side_tol)
    min_sqft = float(t.get("area", {}).get("min", 0.0)) * (1.0 - tol)
    if habitable and st not in rules.habitable_exempt:
        min_side = max(min_side, rules.habitable_min_side_ft)
        min_sqft = max(min_sqft, rules.habitable_min_sqft)
    if st in CIRCULATION_TYPES:
        min_side = max(min_side, rules.hall_min_ft)
    return SpaceSpec(row["space_id"], st, row.get("zone") or t.get("zone", ""), unit_id,
                     float(row["area_sqft"] if target is None else target), min_sqft, min_side, habitable,
                     bool(t.get("passable")), st in CIRCULATION_TYPES, roles_of(matrix, st),
                     row.get("host_space_id"), fixed)


def _fixed_spec(name: str, space_id: str, space_type: str, matrix: ZoneMatrix, extra_roles=()) -> SpaceSpec:
    circ = space_type in (ENTRY_TYPE, VESTIBULE_TYPE, STAIR_TYPE)
    return SpaceSpec(space_id, space_type, "circulation" if circ else "fixed", None, 0.0, 0.0, 0.0, False, circ,
                     circ, roles_of(matrix, space_type) | frozenset(extra_roles), None, True)


# ------------------------------------------------------------------ one floor


def space_floor(level: int, floors: CellFloors, floor_block: dict[str, Any], rows: list[dict[str, Any]],
                plan: LotPlan, catalog, rules: SpaceRules, matrix: ZoneMatrix, res: float, profile: str | None,
                receiving: tuple[str, ...], variant: str) -> SpaceFloor:
    """The grid, fixed nodes and zone units of one floor of an S2 cell (`floor_block` = s2 upper, or the ground
    block of the chosen option)."""
    if level == GROUND:
        fixed_objs = ground_fixed(floors, variant)
        polygon = floors.ground
    else:
        fixed_objs = upper_fixed(floors)
        polygon = floors.upper
    grid = rasterize(polygon, fixed_objs, res)
    base = np.full(grid.labels.shape, UNASSIGNED, dtype=np.int32)
    base[grid.labels == OUTSIDE] = OUT
    by_id = {r["space_id"]: r for r in rows}
    fixed: list[SpaceSpec] = []
    notes: list[str] = []
    for name, geom in fixed_objs:
        if geom is None or geom.is_empty or name not in grid.label_ids:
            continue
        cells = grid.mask_of(name)
        if not cells.any():
            continue
        if name == FIXED_VOID:
            base[cells] = VOID
            continue
        spec = _fixed_node(name, level, rows, matrix, variant)
        if spec is None:
            base[cells] = VOID
            continue
        base[cells] = len(fixed)
        fixed.append(spec)

    # zone units from their S2 polygons
    owner = np.full(base.shape, UNASSIGNED, dtype=np.int32)
    owner[base != UNASSIGNED] = OUT
    units_json = floor_block["units"]
    for k, u in enumerate(units_json):
        rr, cc = cells_of(grid, plan.frame.to_local(shape(u["polygon"])))
        free = owner[rr, cc] == UNASSIGNED
        owner[rr[free], cc[free]] = k
    free_mask = base == UNASSIGNED
    owner = fill_unassigned(owner, free_mask, UNASSIGNED)
    if (free_mask & (owner == UNASSIGNED)).any():
        notes.append(f"{int((free_mask & (owner == UNASSIGNED)).sum())} free cells outside every unit")
    accessible = profile == ACCESSIBLE_PROFILE
    units: list[UnitFrame] = []
    for k, u in enumerate(units_json):
        mask = free_mask & (owner == k)
        box = mask_bounds(mask)
        if box is None:
            notes.append(f"unit {u['unit_id']} has no cells on the grid")
            continue
        specs = _unit_specs(catalog, rules, matrix, u, by_id, level, mask.sum() * grid.cell_area)
        units.append(UnitFrame(k, u["unit_id"], u["zone"], mask, box, specs))
    landing_zone = floors.bottom_zone if level == GROUND else floors.top_zone
    landing = np.zeros(base.shape, dtype=bool)
    rr, cc = cells_of(grid, landing_zone)
    landing[rr, cc] = True
    stair = grid.mask_of(FIXED_STAIR) if FIXED_STAIR in grid.label_ids else np.zeros(base.shape, dtype=bool)
    links: dict[str, set] = {}
    for a, b in floor_block.get("links", []):
        links.setdefault(a, set()).add(b)
        links.setdefault(b, set()).add(a)
    return SpaceFloor(level, grid, base, fixed, units, landing, stair, tuple(receiving), accessible, variant, notes,
                      links)


def _fixed_node(name: str, level: int, rows: list[dict], matrix: ZoneMatrix, variant: str) -> SpaceSpec | None:
    if name == FIXED_STAIR:
        anchor = STAIR_BOTTOM if level == GROUND else STAIR_TOP
        return _fixed_spec(name, f"stair_{'ground' if level == GROUND else 'upper'}", STAIR_TYPE, matrix, (anchor,))
    if name == FIXED_ENTRY:
        return _fixed_spec(name, "entry_vestibule", ENTRY_TYPE, matrix, (ENTRY,))
    if name == FIXED_VESTIBULE:
        return _fixed_spec(name, "half_bath_vestibule", VESTIBULE_TYPE, matrix)
    if name == FIXED_HALF_BATH:
        row = next((r for r in rows if r["space_type"] == HALF_BATH_USE and r["floor"] == GROUND), None)
        sid = row["space_id"] if row else "half_bath_under_stair"
        spec = _fixed_spec(name, sid, HALF_BATH_USE, matrix, (UNDER_STAIR,))
        return spec
    if name == FIXED_GARAGE:
        row = next((r for r in rows if r["zone"] == "garage"), None)
        st = row["space_type"] if row else "garage"
        return _fixed_spec(name, row["space_id"] if row else "garage", st, matrix)
    return None


def _unit_specs(catalog, rules: SpaceRules, matrix: ZoneMatrix, unit: dict[str, Any], by_id: dict[str, dict],
                level: int, unit_sqft: float) -> list[SpaceSpec]:
    rows = [by_id[s] for s in unit["space_ids"] if s in by_id]
    if unit["zone"] != "circulation":
        return [spec_of(catalog, rules, matrix, r, unit["unit_id"]) for r in rows]
    circ = [r for r in rows if r["space_type"] in CIRCULATION_TYPES]
    others = [r for r in rows if r["space_type"] not in CIRCULATION_TYPES]
    specs = [spec_of(catalog, rules, matrix, r, unit["unit_id"]) for r in others]
    rest = max(unit_sqft - sum(s.target_sqft for s in specs), 0.0)
    if not circ:
        hall_id = f"hall_{'ground' if level == GROUND else 'upper'}"
        circ = [{"space_id": hall_id, "space_type": "hall", "zone": "circulation", "area_sqft": rest}]
        synthetic = True
    else:
        synthetic = False
    total = sum(float(r["area_sqft"]) for r in circ) or 1.0
    for r in circ:
        share = rest * float(r["area_sqft"]) / total if not synthetic else rest
        s = spec_of(catalog, rules, matrix, r, unit["unit_id"], target=share)
        specs.append(SpaceSpec(**{**s.__dict__, "synthetic": synthetic}))
    return specs


__all__ = [
    "CIRCULATION_TYPES",
    "ENTRY_TYPE",
    "OUT",
    "STAIR_TYPE",
    "UNASSIGNED",
    "UNDER_STAIR",
    "VESTIBULE_TYPE",
    "VOID",
    "SpaceFloor",
    "SpaceSpec",
    "UnitFrame",
    "d_pair",
    "roles_of",
    "space_floor",
    "spec_of",
]
