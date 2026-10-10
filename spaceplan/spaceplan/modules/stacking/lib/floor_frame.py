"""What stage S2 zones on each drawn floor (step 6.7a S2): free plan, fixed objects, anchors and zone units.

Read from the S1 block of a cell (world coordinates, turned back to the lot's local frame) and from the space split
the area matrix exports (step 9a balanced or trimmed program):

  * ground floor: polygon minus the garage, the stair footprint and, when the space under the stair holds the half
    bath, the half bath and its vestibule; anchors = front facade (entry), rear facade (garden), the bottom arrival
    zone of the stair, the vestibule of the half bath;
  * upper floor: polygon minus the stair opening; anchor = the top arrival zone;
  * zone units: the spaces of each floor grouped by zone (the private zone split into the parts of a zone_parts
    scheme upstairs), halls prorated to each floor's net area as in the area matrix, a small service zone merged into
    a neighbouring zone, targets scaled to the free area of the floor.

The receiving space at the top (client rule K01) is the first of the catalog's arrival order the upper floor allows:
the family room when it is upstairs, a vestibule in a small house, else a hall.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from spaceplan.modules.stacking.lib.lot_plan import LotPlan
from spaceplan.modules.stacking.lib.stair_access import upper_rooms
from spaceplan.modules.stacking.lib_aux.zone_grid import Grid, cells_of, rasterize

GROUND, UPPER = 0, 1
CIRCULATION = "circulation"
GARAGE_ZONE = "garage"
HALF_BATH_USE, STORAGE_USE = "half_bath", "storage"
FIXED_GARAGE, FIXED_STAIR, FIXED_HALF_BATH, FIXED_VESTIBULE = "garage", "stair", "half_bath", "vestibule"
FIXED_ENTRY, FIXED_VOID = "entry_vestibule", "void"
FAMILY_ROOM, VESTIBULE, HALL = "family_room", "upper_vestibule", "hall"


@dataclass(frozen=True)
class ZoneUnit:
    """A zone (or a zone part) to place on a floor: its spaces, target area and least width."""

    unit_id: str
    zone: str
    space_ids: tuple[str, ...]
    space_types: frozenset[str]
    target_sqft: float
    min_width_ft: float

    def hosts(self, types) -> bool:
        return bool(self.space_types & set(types))


@dataclass
class FloorFrame:
    """One floor ready to be zoned: its grid, units (targets in cells) and anchors."""

    level: int
    polygon: BaseGeometry                       # local frame
    free_polygon: BaseGeometry                  # polygon minus the fixed objects
    fixed: dict[str, BaseGeometry]
    grid: Grid
    units: tuple[ZoneUnit, ...]
    targets: tuple[int, ...]                    # cells per unit, sum = free cells of the grid
    landing: tuple[Any, Any]                    # cells (rows, cols) of the arrival zone of the stair on this floor
    variant: str                                # ground: under-stair use; upper: "upper"
    scale: float                                # free area / sum of program targets
    notes: list[str] = field(default_factory=list)
    landing_in_entry: bool = False              # S1.2: the stair starts inside the vestibule of the main door
    arrival_order: tuple = ()                   # upper floor: receiving kinds by preference (K01)

    def unit_index(self, unit_id: str) -> int:
        return next(k for k, u in enumerate(self.units) if u.unit_id == unit_id)


@dataclass(frozen=True)
class CellFloors:
    """The geometry of a drawn S1 cell in the local frame."""

    ground: BaseGeometry
    upper: BaseGeometry
    garage: BaseGeometry | None
    stair: BaseGeometry
    bottom_zone: BaseGeometry
    top_zone: BaseGeometry
    half_bath: BaseGeometry | None
    vestibule: BaseGeometry | None
    entry_vestibule: BaseGeometry | None = None   # stage S1.2: vestibule behind the main door (fixed object)
    void: BaseGeometry | None = None              # stage S1.2: interior void of strategy C (no floor upstairs)
    door_area: BaseGeometry | None = None         # vestibule polygon, fixed or not (routes start there)


def _local(plan: LotPlan, geo: dict | None) -> BaseGeometry | None:
    return None if geo is None else plan.frame.to_local(shape(geo))


def cell_floors(s1: dict[str, Any], plan: LotPlan) -> CellFloors:
    """`s1["access_core"]` (stage S1.2) adds the vestibule behind the main door (fixed unless `fixed` is false:
    then it only marks where the routes start) and the interior void."""
    ac = s1.get("access_core") or {}
    core = s1["stair_core"]
    us = core["under_stair"]
    return CellFloors(
        ground=_local(plan, s1["levels"][0]["polygon"]), upper=_local(plan, s1["levels"][1]["polygon"]),
        garage=_local(plan, s1["ground"].get("garage_polygon")), stair=_local(plan, core["footprint"]),
        bottom_zone=_local(plan, core["bottom_end"]["zone"]), top_zone=_local(plan, core["top_end"]["zone"]),
        half_bath=_local(plan, us.get("half_bath")), vestibule=_local(plan, us.get("vestibule")),
        entry_vestibule=_local(plan, ac.get("vestibule")) if ac.get("fixed", True) else None,
        void=_local(plan, ac.get("void")), door_area=_local(plan, ac.get("vestibule")))


# ------------------------------------------------------------------ program per floor


def arrival_kind(order: list[str], upper_types: set[str], rooms: int, small_max: int) -> str:
    """Receiving space at the top of the stair (K01) by the catalog's arrival order."""
    allowed = {FAMILY_ROOM: FAMILY_ROOM in upper_types, VESTIBULE: rooms <= small_max, HALL: True}
    return next(k for k in order if allowed[k])


def _halls_by_floor(rows: list[dict], hall_types: set[str], floors: int) -> list[float]:
    """Hall area prorated to the net area of each floor (same convention as the area matrix's build_split)."""
    halls = sum(r["area_sqft"] for r in rows if r["space_type"] in hall_types)
    net = [0.0] * floors
    for r in rows:
        if r["zone"] != CIRCULATION:
            net[r["floor"]] += r["area_sqft"]
    base = sum(net) or 1.0
    return [halls * n / base for n in net]


def _part_of(catalog, scheme: tuple[str, str] | None, space_type: str) -> str | None:
    if scheme is None:
        return None
    zone, scheme_id = scheme
    for s in catalog.data["zone_parts"][zone]["schemes"]:
        if s["scheme_id"] == scheme_id:
            for p in s["parts"]:
                if space_type in p["space_types"]:
                    return p["part"]
    return None


def _unit_width(catalog, s2: dict[str, Any], zone: str, members: list[dict], hall_types: set[str]) -> float:
    if s2["unit_min_width"]["rule"] == "space_sides":
        if not members:
            return max(float(catalog.space_type(t).get("min_side_ft", 0.0)) for t in sorted(hall_types))
        return max(float(catalog.space_type(r["space_type"]).get("min_side_ft", 0.0)) for r in members)
    return float(catalog.zone(zone).get("min_width_ft", 0.0))


def _habitable(catalog, members: list[dict]) -> bool:
    return any(catalog.space_type(r["space_type"]).get("habitable") for r in members)


def split_members(catalog, s2: dict[str, Any], zone: str, members: list[dict], floor: str) -> list[list[dict]] | None:
    """Two groups of a zone's spaces that can sit on both sides of the stair hall: the parts of the catalog's
    zone_parts scheme for the zone, else rooms balanced by area; hosted spaces follow their host. None when a group
    would hold no habitable room."""
    hosted = {r["space_id"]: r for r in members if r.get("host_space_id")}
    heads = [r for r in members if r["space_id"] not in hosted]
    scheme_id = s2["zone_parts"].get(floor, {}).get(zone)
    groups: list[list[dict]] = [[], []]
    if scheme_id:
        part_names = [p["part"] for s in catalog.data["zone_parts"][zone]["schemes"] if s["scheme_id"] == scheme_id
                      for p in s["parts"]][:2]
        rest = []
        for r in heads:
            part = _part_of(catalog, (zone, scheme_id), r["space_type"])
            (groups[part_names.index(part)] if part in part_names else rest).append(r)
    else:
        rest = heads
    for r in sorted(rest, key=lambda r: (-r["area_sqft"], r["space_id"])):
        light = min((0, 1), key=lambda k: (sum(x["area_sqft"] for x in groups[k]), k))
        groups[light].append(r)
    for h in hosted.values():
        home = next((k for k in (0, 1) if any(x["space_id"] == h["host_space_id"] for x in groups[k])), None)
        groups[home if home is not None else 0].append(h)
    if not all(groups) or not all(_habitable(catalog, g) for g in groups):
        return None
    return groups


def floor_units(catalog, s2: dict[str, Any], rows: list[dict], level: int, floors: int, stair_type: str,
                under_stair_half_bath: bool, arrival: str | None) -> list[tuple[str, list[ZoneUnit], list[str]]]:
    """Unit sets of one floor (unscaled targets, sq ft): the zones whole, and, for each zone the catalog lets split
    on this floor, the same set with that zone in two units. Each set comes with its notes."""
    hall_types = set(catalog.data["circulation"]["derived_space_types"])
    halls = _halls_by_floor(rows, hall_types, floors)
    notes: list[str] = []
    groups: dict[str, list[dict]] = {}
    floor = "upper" if level > GROUND else "ground"
    hb_left = under_stair_half_bath and level == GROUND
    for r in rows:
        st = r["space_type"]
        if r["zone"] == GARAGE_ZONE or st == stair_type or st in hall_types or r["floor"] != level:
            continue
        if hb_left and st == HALF_BATH_USE:
            hb_left = False            # this half bath is the one under the stair (fixed object)
            continue
        groups.setdefault(r["zone"], []).append(r)
    circ = halls[level]
    if level > GROUND and arrival is not None:
        least = float(s2["circulation_min_sqft"][VESTIBULE if arrival == VESTIBULE else HALL])
        if circ < least:
            notes.append(f"upper circulation raised from {circ:.0f} to {least:.0f} sq ft ({arrival} arrival)")
            circ = least
    if circ > 0.0 or CIRCULATION in groups:
        groups.setdefault(CIRCULATION, [])
    # small service zone merged into a neighbour
    merge = s2["merge_small"]
    small_max = float(catalog.data["zoning"]["merge_options"][merge["zone"]]["max_area_sqft"])
    if merge["zone"] in groups:
        area = sum(r["area_sqft"] for r in groups[merge["zone"]])
        into = next((z for z in merge["into"][floor] if z in groups), None)
        if area <= small_max and into is not None:
            groups[into] = groups[into] + groups.pop(merge["zone"])
            notes.append(f"{merge['zone']} ({area:.0f} sq ft) merged into {into}")
    # circulation holds at least the catalog's share of the floor (the gross allowance of the program
    # includes it; prorated halls alone leave no corridor once the stair takes its column)
    share = float(catalog.data["circulation"]["target_fraction"])
    others = sum(r["area_sqft"] for k, g in groups.items() if k != CIRCULATION for r in g)
    own = sum(r["area_sqft"] for r in groups.get(CIRCULATION, [])) + circ
    least = share * others / (1.0 - share)
    if CIRCULATION in groups and own < least:
        notes.append(f"circulation raised from {own:.0f} to {least:.0f} sq ft (target fraction {share:.2f})")
        circ += least - own

    def unit(uid: str, zone: str, members: list[dict]) -> ZoneUnit:
        target = sum(r["area_sqft"] for r in members) + (circ if zone == CIRCULATION else 0.0)
        return ZoneUnit(uid, zone, tuple(r["space_id"] for r in members),
                        frozenset(r["space_type"] for r in members), target,
                        _unit_width(catalog, s2, zone, members, hall_types))

    whole = [unit(z, z, groups[z]) for z in sorted(groups)]
    whole = [u for u in whole if u.target_sqft > 0.0]
    sets = [("whole", whole, list(notes))]
    for zone in s2.get("split_zones", {}).get(floor, []):
        if zone not in groups:
            continue
        parts = split_members(catalog, s2, zone, groups[zone], floor)
        if parts is None:
            continue
        units = [u for u in whole if u.zone != zone] + [unit(f"{zone}:{k + 1}", zone, g) for k, g in enumerate(parts)]
        sets.append((f"split:{zone}", sorted(units, key=lambda u: u.unit_id),
                     notes + [f"{zone} in two units: " + " | ".join(",".join(r["space_id"] for r in g) for g in parts)]))
    return sets


def _scaled(units: list[ZoneUnit], free_cells: int) -> tuple[tuple[int, ...], float]:
    total = sum(u.target_sqft for u in units) or 1.0
    raw = [u.target_sqft / total * free_cells for u in units]
    cells = [int(round(x)) for x in raw]
    if cells:
        cells[-1] += free_cells - sum(cells)
    return tuple(cells), total


def ground_frame(floors: CellFloors, units: list[ZoneUnit], res: float, use: str, notes: list[str]) -> FloorFrame:
    """Ground floor for one use of the space under the stair (half bath: fixed with its vestibule; storage: the
    footprint only)."""
    fixed = [(FIXED_GARAGE, floors.garage), (FIXED_STAIR, floors.stair)]
    if use == HALF_BATH_USE and floors.half_bath is not None:
        fixed += [(FIXED_HALF_BATH, floors.half_bath), (FIXED_VESTIBULE, floors.vestibule)]
    if floors.entry_vestibule is not None:
        fixed.append((FIXED_ENTRY, floors.entry_vestibule))
    grid = rasterize(floors.ground, fixed, res)
    taken = unary_union([g for _, g in fixed if g is not None])
    targets, total = _scaled(units, grid.free_cells)
    landing = cells_of(grid, floors.bottom_zone)
    in_entry = (floors.entry_vestibule is not None
                and floors.bottom_zone.intersection(floors.entry_vestibule).area >= 0.5 * floors.bottom_zone.area)
    return FloorFrame(GROUND, floors.ground, floors.ground.difference(taken), dict(fixed), grid, tuple(units),
                      targets, landing, use, grid.free_cells * grid.cell_area / total, list(notes), in_entry)


def upper_frame(floors: CellFloors, units: list[ZoneUnit], res: float, notes: list[str]) -> FloorFrame:
    fixed = [(FIXED_STAIR, floors.stair)] + ([(FIXED_VOID, floors.void)] if floors.void is not None else [])
    grid = rasterize(floors.upper, fixed, res)
    targets, total = _scaled(units, grid.free_cells)
    taken = unary_union([g for _, g in fixed if g is not None])
    return FloorFrame(UPPER, floors.upper, floors.upper.difference(taken), dict(fixed), grid, tuple(units),
                      targets, cells_of(grid, floors.top_zone), "upper", grid.free_cells * grid.cell_area / total,
                      list(notes))


def upper_arrival(catalog, s2: dict[str, Any], access: dict[str, Any], rows: list[dict],
                  k01: dict[str, Any] | None = None) -> dict[str, Any]:
    """Receiving spaces allowed at the top of the stair and the client's order of preference (K01, 2026-10-10:
    a preference, scored): vestibule first in a small house, else hall; the family room last, and only when it is
    upstairs. `receiving` is the most preferred one (the circulation kind S1 sized the arrival zone for)."""
    upper = [r for r in rows if r["floor"] > GROUND]
    types = {r["space_type"] for r in upper}
    rooms = upper_rooms([r["space_id"] for r in upper], catalog, access)
    small = rooms <= access["small_house_upper_rooms_max"]
    pref = (k01 or {}).get("as_preference")
    if pref:
        order = list(pref["order_small_house"] if small else pref["order_default"])
    else:
        order = [arrival_kind(s2["arrival_order"], types, rooms, access["small_house_upper_rooms_max"])]
    order = [k for k in order if k != FAMILY_ROOM or FAMILY_ROOM in types]
    return {"receiving": order[0], "order": order, "small_house": small, "upper_rooms": rooms,
            "family_room_upstairs": FAMILY_ROOM in types}


def arrival_of(unit: ZoneUnit, order: list[str]) -> str | None:
    """Which receiving kind a unit is: the family room's zone, or circulation (vestibule or hall, whichever the
    order ranks first); None when the unit may not receive the stair."""
    if FAMILY_ROOM in order and unit.hosts({FAMILY_ROOM}):
        return FAMILY_ROOM
    if unit.zone == CIRCULATION:
        return next((k for k in order if k in (VESTIBULE, HALL)), None)
    return None


__all__ = ["CIRCULATION", "FAMILY_ROOM", "FIXED_ENTRY", "FIXED_GARAGE", "FIXED_VOID", "FIXED_HALF_BATH", "FIXED_STAIR", "FIXED_VESTIBULE", "GROUND",
           "HALF_BATH_USE", "HALL", "STORAGE_USE", "UPPER", "VESTIBULE", "CellFloors", "FloorFrame", "ZoneUnit",
           "arrival_kind", "arrival_of", "cell_floors", "floor_units", "ground_frame", "upper_arrival", "upper_frame"]
