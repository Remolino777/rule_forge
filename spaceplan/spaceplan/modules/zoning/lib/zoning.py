"""Layer 1c - zoning of one floor, for houses and apartments (spaceplan v1.1 sections 3, 8; revision 2026-10).

Exhaustive enumeration of zone topologies realized by an interchangeable strategy. The access side
of the footprint is always the front band (street for houses, corridor for apartments). What each
facade is (main street, garden, side yard, exterior, access, party wall) comes from the context;
what each dwelling type requires comes from a catalog zoning profile; what this client requires
comes from the brief's typed relations. Nothing about houses or apartments is hard-coded here.

Hard constraints
  brief      zone-zone mandatory / forbidden adjacency, k-of-n groups, zone-site mandatory facades
  profile    entry zone on the entry interval; anchors (e.g. living room on the main street, bedrooms
             on an exterior facade); entry sequence (apartment kitchen reached through the foyer and
             never on the entrance itself)
  catalog    minimum width per zone or zone part, garage vehicle depth
Soft score   desired relations + soft anchors, orientation on exterior facades, cell shape.
"""

from __future__ import annotations

import itertools
from collections import Counter, defaultdict
from dataclasses import dataclass, field, replace

from spaceplan.core.lib.catalog import Catalog, site_parameters
from spaceplan.core.lib.enums import RelationType, SiteZone, Zone
from spaceplan.core.lib_aux.allocation import fit_lengths
from spaceplan.modules.zoning.lib.band_enumeration import (  # noqa: F401  (private names re-exported)
    BandGeometry,
    _column_ok,
    _compositions,
    _set_partitions,
    band_arrangements,
)
from spaceplan.modules.zoning.lib.realization import (
    SHOULDER_FACADES,
    FootprintDomain,
    RealizationStrategy,
    RealizedZones,
    Rect,
    StrategyB,
    ZoneTopology,
    polygonal_cuts,
)

ZONES = {z.value for z in Zone}
SITE_ZONES = {s.value for s in SiteZone}
FACADES = ("front", "rear", "left", "right", *SHOULDER_FACADES)


# --------------------------------------------------------------------------- brief constraints


@dataclass
class ZoningConstraints:
    adjacency_required: list[tuple[str, str, str]] = field(default_factory=list)
    adjacency_forbidden: list[tuple[str, str, str]] = field(default_factory=list)
    no_door: list[tuple[str, str, str]] = field(default_factory=list)
    groups: list[dict] = field(default_factory=list)
    facade_required: list[tuple[str, str, str]] = field(default_factory=list)  # (zone, site zone, relation)
    desired: list[tuple[str, str, float, str]] = field(default_factory=list)
    facade_desired: list[tuple[str, str, float, str]] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)


def constraints_from_brief(brief: dict, zones: set[str], merges: dict[str, str] | None = None) -> ZoningConstraints:
    """Zone-level constraints. A zone merged into a host (laundry inside the garage) is represented by the host
    for mandatory, group and desired relations; its forbidden adjacencies are left to the space level."""
    c = ZoningConstraints()
    merges = merges or {}
    for rel in brief["relations"]:
        a, b, rid, kind = rel["a"], rel["b"], rel["relation_id"], rel["type"]
        if kind == RelationType.FORBIDDEN and (a in merges or b in merges):
            c.skipped.append(rid)
            continue
        a, b = merges.get(a, a), merges.get(b, b)
        if a in SITE_ZONES and b in zones:
            a, b = b, a
        weight = rel.get("weight", 1.0)
        if a in zones and b in zones:
            if kind == RelationType.MANDATORY:
                c.adjacency_required.append((a, b, rid))
            elif kind == RelationType.FORBIDDEN:
                scope = rel.get("applies_to", "adjacency")
                (c.adjacency_forbidden if scope == "adjacency" else c.no_door).append((a, b, rid))
            elif kind == RelationType.DESIRED:
                c.desired.append((a, b, weight, rid))
            else:
                c.skipped.append(rid)
        elif a in zones and b in SITE_ZONES:
            if kind == RelationType.MANDATORY:
                c.facade_required.append((a, b, rid))
            elif kind in (RelationType.DESIRED, RelationType.VISUAL):
                c.facade_desired.append((a, b, weight, rid))
            else:
                c.skipped.append(rid)
        else:
            c.skipped.append(rid)
    for group in brief["relation_groups"]:
        mapped = [(merges.get(m["a"], m["a"]), merges.get(m["b"], m["b"])) for m in group["members"]]
        members = [(a, b) for a, b in mapped if a in zones and b in zones]
        if members:
            c.groups.append({"group_id": group["group_id"], "k": group["k"], "members": members})
        else:
            c.skipped.append(group["group_id"])
    return c


# --------------------------------------------------------------------------- dwelling profile


@dataclass(frozen=True)
class Anchor:
    anchor_id: str
    space_types: frozenset[str]
    facade_role: str
    kind: str
    min_contact: float
    weight: float
    fallback_role: str | None = None   # accepted instead of facade_role (e.g. a street-facing shoulder) ...
    fallback_penalty: float = 0.0      # ... at this soft-score cost


@dataclass(frozen=True)
class Profile:
    dwelling_type: str
    entry_zone: str
    entry_interval: str
    entry_min_overlap: float
    anchors: tuple[Anchor, ...]
    entry_sequence: dict | None


def load_profile(catalog: Catalog, dwelling_type: str, overrides: dict[str, str] | None = None) -> Profile:
    """Catalog profile with the brief's overrides applied (an anchor can become soft, hard or off)."""
    p = catalog.data["zoning_profiles"][dwelling_type]
    overrides = overrides or {}
    unknown = set(overrides) - {a["anchor_id"] for a in p["anchors"]} - (
        {p["entry_sequence"]["anchor_id"]} if p["entry_sequence"] else set())
    if unknown:
        raise ValueError(f"zoning_overrides: unknown anchors {sorted(unknown)} for {dwelling_type}")
    anchors = tuple(
        Anchor(a["anchor_id"], frozenset(a["space_types"]), a["facade_role"], overrides.get(a["anchor_id"], a["kind"]),
               a["min_contact_ft"], a["weight"], a.get("fallback_role"), a.get("fallback_penalty", 0.0))
        for a in p["anchors"] if overrides.get(a["anchor_id"]) != "off"
    )
    sequence = p["entry_sequence"]
    if sequence and sequence["anchor_id"] in overrides:
        kind = overrides[sequence["anchor_id"]]
        sequence = None if kind == "off" else {**sequence, "kind": kind}
    return Profile(dwelling_type, p["entry"]["zone"], p["entry"]["interval"], p["entry"]["min_overlap_ft"],
                   anchors, sequence)


# --------------------------------------------------------------------------- cells (zones or zone parts)


@dataclass(frozen=True)
class CellModel:
    areas: dict[str, float]
    parts: dict[str, tuple[str, ...]]          # split zone -> its cell ids
    spaces: dict[str, frozenset[str]]          # cell -> space types it holds (satellites included)
    min_width: dict[str, float]
    split: tuple[str, ...]                     # zones split in this variant
    space_cell: dict[str, str] = field(default_factory=dict)      # real space -> cell
    satellite_cell: dict[str, str] = field(default_factory=dict)  # satellite -> cell of its host
    derived: tuple[str, ...] = ()                                  # circulation spaces replaced by the network
    merged: tuple[tuple[str, str], ...] = ()                       # small zone -> host zone cell

    def parent_zone(self, cell: str) -> str:
        for zone, cells in self.parts.items():
            if cell in cells:
                return zone
        return cell.split("_")[0] if cell not in ZONES else cell  # merged/unsplit cells are named after their zone


def _scheme(catalog: Catalog, zone: str, scheme_id: str) -> dict:
    return next(s for s in catalog.data["zone_parts"][zone]["schemes"] if s["scheme_id"] == scheme_id)


def cell_model(catalog: Catalog, program: dict, footprint_area: float, split: dict[str, str] | tuple = (),
               merges: dict[str, str] | None = None) -> CellModel:
    """Zone (or zone-part) areas scaled to the footprint.

    Satellites count in their host's cell. Derived circulation spaces (halls) are removed from the
    program: circulation is produced by the network and taken from the cells it serves.
    """
    spaces = {s["space_id"]: s for s in program["spaces"]}
    support = {s["space_id"] for s in program["spaces"]
               if catalog.scale(s["scale"])["topology"] == "satellite" and s.get("host_space_id") in spaces}
    derived_types = set(catalog.data["circulation"]["derived_space_types"])
    zones_with_rooms = {s["zone"] for sid, s in spaces.items()
                        if sid not in support and s.get("space_type") not in derived_types}
    derived = {sid for sid, s in spaces.items() if sid not in support and s.get("space_type") in derived_types
               and s["zone"] in zones_with_rooms}

    def host_of(space_id: str) -> str:
        seen = set()
        while space_id in support and space_id not in seen:
            seen.add(space_id)
            space_id = spaces[space_id]["host_space_id"]
        return space_id

    split = dict(split) if not isinstance(split, tuple) else {z: catalog.data["zone_parts"][z]["schemes"][0]["scheme_id"]
                                                              for z in split}
    split_zones = tuple(sorted(split))
    zone_min = {z["zone"]: z["min_width_ft"] for z in catalog.data["zones"]}
    cell_of: dict[str, str] = {}
    merges = merges or {}
    for sid, s in spaces.items():
        if sid in support:
            continue
        zone = merges.get(s["zone"], s["zone"])
        if zone in split:
            parts = _scheme(catalog, zone, split[zone])["parts"]
            part = next((p["part"] for p in parts if s.get("space_type") in p["space_types"]), parts[-1]["part"])
            cell_of[sid] = f"{zone}_{part}"
        else:
            cell_of[sid] = zone
    for sid in support:
        cell_of[sid] = cell_of[host_of(sid)]
    net: Counter = Counter()
    types: dict[str, set[str]] = defaultdict(set)
    for sid, cell in cell_of.items():
        if sid in derived:
            continue
        net[cell] += spaces[sid]["target_area_sqft"]
        if spaces[sid].get("space_type"):
            types[cell].add(spaces[sid]["space_type"])
    total = sum(net.values())
    areas = {c: footprint_area * a / total for c, a in net.items() if a > 0}
    parts: dict[str, tuple[str, ...]] = {}
    min_width: dict[str, float] = {}
    for cell in areas:
        zone = next((z for z in split_zones if cell.startswith(f"{z}_")), None)
        if zone:
            parts.setdefault(zone, ())
            parts[zone] += (cell,)
            part = cell[len(zone) + 1:]
            min_width[cell] = next(p["min_width_ft"] for p in _scheme(catalog, zone, split[zone])["parts"]
                                   if p["part"] == part)
        else:
            min_width[cell] = zone_min[cell]
    parts = {z: c for z, c in parts.items() if len(c) > 1}
    space_cell = {sid: c for sid, c in cell_of.items() if sid not in support and sid not in derived and c in areas}
    satellite_cell = {sid: c for sid, c in cell_of.items() if sid in support and c in areas}
    split_label = tuple(f"{z}:{split[z]}" for z in sorted(parts))
    return CellModel(areas, parts, {c: frozenset(types[c]) for c in areas}, min_width, split_label,
                     space_cell, satellite_cell, tuple(sorted(derived)), tuple(sorted(merges.items())))


def merge_options(catalog: Catalog, program: dict) -> list[dict[str, str]]:
    """No merge, plus each allowed host for small zones (e.g. laundry inside the kitchen or the garage cell)."""
    present = Counter()
    for s in program["spaces"]:
        present[s["zone"]] += s["target_area_sqft"]
    out: list[dict[str, str]] = [{}]
    for zone, rule in catalog.data["zoning"]["merge_options"].items():
        if 0 < present.get(zone, 0) <= rule["max_area_sqft"]:
            out += [{zone: host} for host in rule["into"] if present.get(host, 0) > 0]
    return out


def split_options(catalog: Catalog, program: dict, dwelling_type: str | None = None) -> list[dict[str, str]]:
    """Every combination of (unsplit | one partition scheme) per zone; a scheme counts when >= 2 parts are non-empty."""
    per_zone = []
    for zone, rule in sorted(catalog.data["zone_parts"].items()):
        choices = [None]
        for scheme in rule["schemes"]:
            if dwelling_type and dwelling_type not in scheme["dwelling_types"]:
                continue
            found = {p["part"] for s in program["spaces"] if s["zone"] == zone
                     for p in scheme["parts"] if s.get("space_type") in p["space_types"]}
            if len(found) >= 2:
                choices.append(scheme["scheme_id"])
        per_zone.append([(zone, c) for c in choices])
    return [{z: c for z, c in combo if c} for combo in itertools.product(*per_zone)]


# --------------------------------------------------------------------------- context


@dataclass(frozen=True)
class ZoningContext:
    footprint: Rect
    footprint_variant: str
    cells: CellModel
    constraints: ZoningConstraints
    profile: Profile
    facade_roles: dict[str, frozenset[str]]
    affinity: dict[str, dict[str, float]]
    intervals: dict[str, tuple[float, float] | None]
    garage_min_depth: float
    min_contact: float
    max_aspect: float
    max_per_column: int
    weights: dict[str, float]
    site_facades: dict[str, list[str]]
    matrix: object = None  # RelationMatrix
    spine_width: float = 0.0  # > 0: a corridor runs between the bands; zone areas already exclude it
    max_through: int = 0      # zones allowed in a full-depth through column
    passable_types: frozenset = frozenset()  # open space types (a D pair between two of them needs a shared wall)
    domain: FootprintDomain | None = None    # strategy B: envelope profile and front line
    band_model: StrategyB | None = None      # strategy B instance (band geometry for the pruning filters)
    width_floor: dict = field(default_factory=dict)  # B stepped: minimum column width per cell (zone min, driveway)
    max_area_shift: float | None = None      # B stepped: largest area fraction a zone may trade inside its band
    joint: str | None = None                 # B stepped: joint corridor side ("left" / "right"), no spine
    joint_width: float = 0.0

    @property
    def realize_input(self):
        return self.domain if self.domain is not None else self.footprint

    @property
    def areas(self) -> dict[str, float]:
        return self.cells.areas

    def cells_of(self, zone: str) -> tuple[str, ...]:
        return self.cells.parts.get(zone, (zone,))

    def parent(self, cell: str) -> str:
        for zone, cells in self.cells.parts.items():
            if cell in cells:
                return zone
        return cell

    def facades_with(self, role: str) -> list[str]:
        return [f for f in FACADES if role in self.facade_roles.get(f, frozenset())]

    def anchor_cells(self, anchor: Anchor) -> list[str]:
        return [c for c, types in self.cells.spaces.items() if types & anchor.space_types]


# --------------------------------------------------------------------------- enumeration


def enumerate_with_through(zones: list[str], max_per_column: int, must_front: set[str], must_rear: set[str],
                           max_through: int, filters_for, through_ok):
    """Topologies without a through column, then with one (left or right) of up to max_through zones."""
    band_ok, column_check = filters_for(tuple(sorted(zones)))
    yield from enumerate_topologies(zones, max_per_column, must_front, must_rear, band_ok, column_check)
    for size in range(1, max_through + 1):
        for column in itertools.permutations(sorted(zones), size):
            if any(z in must_front and column.index(z) != 0 for z in column):
                continue
            if any(z in must_rear and column.index(z) != len(column) - 1 for z in column):
                continue
            if not through_ok(column):
                continue
            rest = [z for z in zones if z not in column]
            if not rest:
                for side in ("left", "right"):
                    yield ZoneTopology((), (), column, side)
                continue
            r_band_ok, r_column = filters_for(tuple(sorted(rest)))
            for topo in enumerate_topologies(rest, max_per_column, must_front - set(column), must_rear - set(column),
                                             r_band_ok, r_column):
                if not topo.front or not topo.rear:
                    continue  # through column + a single band is the same as a single band of columns
                for side in ("left", "right"):
                    yield ZoneTopology(topo.front, topo.rear, column, side)


def _positional_args(fn) -> int:
    import inspect

    try:
        params = inspect.signature(fn).parameters.values()
    except (TypeError, ValueError):
        return 3
    return sum(p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD) for p in params)


def enumerate_topologies(zones: list[str], max_per_column: int = 1, must_front: set[str] = frozenset(),
                         must_rear: set[str] = frozenset(), band_ok=None, column_check=None):
    """Exhaustive enumeration with early pruning.

    band_ok(front, rear) rejects whole band splits; column_check(column, band_cells, is_front) rejects a
    column whose cells cannot meet their minimum dimensions in that band, before any ordering.
    """
    zones = sorted(zones)
    for mask in itertools.product((0, 1), repeat=len(zones)):
        front = [z for z, m in zip(zones, mask) if m == 0]
        rear = [z for z, m in zip(zones, mask) if m == 1]
        if set(front) & set(must_rear) or set(rear) & set(must_front):
            continue
        if band_ok is not None and not band_ok(front, rear):
            continue
        if column_check is not None and _positional_args(column_check) < 3:  # legacy (column, band) checks
            f_ok = lambda col, band=tuple(front): column_check(col, band)  # noqa: E731
            r_ok = lambda col, band=tuple(rear): column_check(col, band)  # noqa: E731
        else:
            f_ok = (lambda col, band=tuple(front): column_check(col, band, True)) if column_check else None
            r_ok = (lambda col, band=tuple(rear): column_check(col, band, False)) if column_check else None
        cols_ok = getattr(column_check, "columns_ok", None)
        f_cols = (lambda cols, band=tuple(front): cols_ok(cols, band, True)) if cols_ok else None
        r_cols = (lambda cols, band=tuple(rear): cols_ok(cols, band, False)) if cols_ok else None
        rear_options = list(band_arrangements(rear, max_per_column, set(), set(must_rear), r_ok, r_cols))
        if rear and not rear_options:
            continue
        for f in band_arrangements(front, max_per_column, set(must_front), set(), f_ok, f_cols):
            for r in rear_options:
                yield ZoneTopology(f, r)


def required_bands(ctx: ZoningContext) -> tuple[set[str], set[str]]:
    """Cells that must touch only-front or only-rear facades (from brief relations and hard anchors)."""
    front, rear = set(), set()

    def place(cells, facades):
        if facades == ["front"]:
            front.update(cells)
        elif facades == ["rear"]:
            rear.update(cells)

    for zone, site, _ in ctx.constraints.facade_required:
        if zone in ctx.cells.parts:
            continue
        place([zone], ctx.site_facades.get(site, []))
    entry = ctx.profile.entry_zone
    if entry not in ctx.cells.parts:
        front.add(entry)
    for anchor in ctx.profile.anchors:
        if anchor.kind == "hard":
            facades = ctx.facades_with(anchor.facade_role)
            if anchor.fallback_role:
                facades = facades + [f for f in ctx.facades_with(anchor.fallback_role) if f not in facades]
            place(ctx.anchor_cells(anchor), facades)
    present = set(ctx.areas)
    return front & present, rear & present


def _b_bands(ctx: ZoningContext, front_area: float, rear_area: float, cache: dict):
    """Strategy B band geometry (front, rear) as BandGeometry pairs, or None if the bands do not fit."""
    key = (round(front_area, 6), round(rear_area, 6))
    if key not in cache:
        layout = ctx.band_model.band_layout(ctx.domain, front_area, rear_area, ctx.spine_width)
        out = None
        if layout is not None:
            geoms, it = [], iter(layout)
            for area in (front_area, rear_area):
                if area <= 0:
                    geoms.append(None)
                    continue
                y0, y1, x0, x1 = next(it)
                width = (x1 - x0) if ctx.band_model.mode == "rectangle" else area / (y1 - y0)
                geoms.append(BandGeometry(width, y1 - y0, area))
            out = tuple(geoms)
        cache[key] = out
    return cache[key]


def column_filter(ctx: ZoningContext, subset: tuple[str, ...] | None = None):
    """Column check bound to the band region (footprint minus any through column)."""
    if ctx.band_model is not None:
        total_b = sum(ctx.areas[c] for c in subset) if subset else sum(ctx.areas.values())
        vehicle_b = set(ctx.cells_of(Zone.GARAGE.value))
        cache_b: dict = {}

        def check_b(column, band_cells, is_front=True):
            area = sum(ctx.areas[c] for c in band_cells)
            front, rear = (area, total_b - area) if is_front else (total_b - area, area)
            bands = _b_bands(ctx, front, rear, cache_b)
            if bands is None:
                return False
            band = bands[0 if is_front else 1]
            if ctx.width_floor:
                # widths are fitted at realization: a column may grow by max_area_shift at most
                grow = 1.0 + (ctx.max_area_shift if ctx.max_area_shift is not None else float("inf"))
                band = BandGeometry(band.width * grow, band.depth, band.area)
                return _column_ok(column, ctx.areas, ctx.width_floor, band, vehicle_b, ctx.garage_min_depth)
            return _column_ok(column, ctx.areas, ctx.cells.min_width, band, vehicle_b, ctx.garage_min_depth)

        if ctx.width_floor:
            def band_columns_ok(columns, band_cells, is_front=True):
                """Order-independent: the column minimums of the band fit its width."""
                area = sum(ctx.areas[c] for c in band_cells)
                front, rear = (area, total_b - area) if is_front else (total_b - area, area)
                bands = _b_bands(ctx, front, rear, cache_b)
                if bands is None:
                    return False
                band = bands[0 if is_front else 1]
                if band is None:
                    return not columns
                need = sum(max(ctx.width_floor[z] for z in col) for col in columns)
                return need <= band.width + 1e-9

            check_b.columns_ok = band_columns_ok

        return check_b
    x0, y0, x1, y1 = ctx.footprint
    all_total = sum(ctx.areas.values())
    total = sum(ctx.areas[c] for c in subset) if subset else all_total
    x1 = x0 + (x1 - x0) * total / all_total
    vehicle = set(ctx.cells_of(Zone.GARAGE.value))
    cache: dict[tuple[str, ...], BandGeometry] = {}

    def check(column, band_cells, is_front=True):
        band = cache.get(band_cells)
        if band is None:
            area = sum(ctx.areas[c] for c in band_cells)
            band = BandGeometry(x1 - x0, (y1 - y0 - ctx.spine_width) * area / total, area)
            cache[band_cells] = band
        return _column_ok(column, ctx.areas, ctx.cells.min_width, band, vehicle, ctx.garage_min_depth)

    return check


def band_depth_filter(ctx: ZoningContext, subset: tuple[str, ...] | None = None):
    """Reject band splits whose depth cannot host the cells' minimum dimensions or the garage."""
    if ctx.band_model is not None:
        garage_b = set(ctx.cells_of(Zone.GARAGE.value))
        cache_b: dict = {}

        def ok_b(front, rear):
            if ctx.spine_width > 0 and (not front or not rear):
                return False
            fa, ra = sum(ctx.areas[c] for c in front), sum(ctx.areas[c] for c in rear)
            bands = _b_bands(ctx, fa, ra, cache_b)
            if bands is None:
                return False
            for cells, band in ((front, bands[0]), (rear, bands[1])):
                if not cells:
                    continue
                if any(band.depth < ctx.cells.min_width[c] - 1e-9 for c in cells):
                    return False
                if garage_b & set(cells) and band.depth < ctx.garage_min_depth - 1e-9:
                    return False
            return True

        return ok_b
    _, y0, _, y1 = ctx.footprint
    total = sum(ctx.areas[c] for c in subset) if subset else sum(ctx.areas.values())
    garage = set(ctx.cells_of(Zone.GARAGE.value))
    avail = (y1 - y0) - ctx.spine_width

    def ok(front, rear):
        if ctx.spine_width > 0 and (not front or not rear):
            return False
        for band in (front, rear):
            if not band:
                continue
            depth = avail * sum(ctx.areas[c] for c in band) / total
            if any(depth < ctx.cells.min_width[c] - 1e-9 for c in band):
                return False
            if garage & set(band) and depth < ctx.garage_min_depth - 1e-9:
                return False
        return True

    return ok


# --------------------------------------------------------------------------- checks


def _overlap(cell: Rect, interval: tuple[float, float]) -> float:
    return max(0.0, min(cell[2], interval[1]) - max(cell[0], interval[0]))


def _pair_contact(r: RealizedZones, pa: str, pb: str, min_contact: float) -> float:
    """Shared wall, or connection through the circulation spine when both cells open onto it."""
    direct = r.contact(pa, pb)
    if r.spine is not None:
        via = min(r.spine_contact(pa), r.spine_contact(pb))
        if via >= min_contact - 1e-9:
            return max(direct, min_contact)
    return direct


def _any_contact(ctx, r: RealizedZones, a: str, b: str) -> float:
    return max((_pair_contact(r, pa, pb, ctx.min_contact) for pa in ctx.cells_of(a) for pb in ctx.cells_of(b)
                if pa in r.cells and pb in r.cells and pa != pb), default=0.0)


def _present(ctx, r: RealizedZones, zone: str) -> bool:
    return any(c in r.cells for c in ctx.cells_of(zone))


def _role_contact(ctx, r: RealizedZones, cell: str, role: str) -> float:
    contacts = r.facade_contacts(cell)
    return max((contacts.get(f, 0.0) for f in ctx.facades_with(role)), default=0.0)


def _touches_interval(r: RealizedZones, cell: str, interval: tuple[float, float]) -> float:
    span = r.front_span(cell)
    return max(0.0, min(span[1], interval[1]) - max(span[0], interval[0])) if span else 0.0


def anchor_results(ctx: ZoningContext, r: RealizedZones) -> list[dict]:
    out = []
    for a in ctx.profile.anchors:
        cells = [c for c in ctx.anchor_cells(a) if c in r.cells]
        if not cells:
            out.append({"anchor_id": a.anchor_id, "kind": a.kind, "applicable": False, "satisfied": True, "cells": []})
            continue
        ok = all(_role_contact(ctx, r, c, a.facade_role) >= a.min_contact - 1e-9 for c in cells)
        via = a.facade_role
        if not ok and a.fallback_role:
            ok = all(max(_role_contact(ctx, r, c, a.facade_role), _role_contact(ctx, r, c, a.fallback_role))
                     >= a.min_contact - 1e-9 for c in cells)
            via = a.fallback_role if ok else None
        out.append({"anchor_id": a.anchor_id, "kind": a.kind, "applicable": True, "satisfied": ok, "cells": cells,
                    "via_role": via if ok else None})
    return out


def entry_sequence_result(ctx: ZoningContext, r: RealizedZones) -> dict | None:
    seq = ctx.profile.entry_sequence
    if not seq:
        return None
    targets = [c for c in ctx.cells_of(seq["target_zone"]) if c in r.cells]
    if not targets:
        return {"anchor_id": seq["anchor_id"], "kind": seq["kind"], "applicable": False, "satisfied": True}
    via = _any_contact(ctx, r, seq["target_zone"], seq["via_zone"]) >= ctx.min_contact - 1e-9
    entrance = ctx.intervals.get(ctx.profile.entry_interval)
    on_entrance = bool(entrance) and any(_touches_interval(r, c, entrance) > 1e-6 for c in targets)
    ok = via and not (seq["forbid_entrance_contact"] and on_entrance)
    return {"anchor_id": seq["anchor_id"], "kind": seq["kind"], "applicable": True, "satisfied": ok,
            "via_contact": via, "on_entrance": on_entrance}


def _near(r: RealizedZones, a: str, b: str, min_contact: float) -> bool:
    """Cells touch, open onto the spine, or share a neighbour through which a foyer or hall can connect them."""
    if _pair_contact(r, a, b, min_contact) >= min_contact - 1e-9:
        return True
    return any(r.contact(a, c) >= min_contact - 1e-9 and r.contact(b, c) >= min_contact - 1e-9
               for c in r.cells if c not in (a, b))


_ROLE_CACHE: dict[int, dict[str, set[str]]] = {}


def _role_cells(ctx: ZoningContext) -> dict[str, set[str]]:
    """Cells holding each matrix role (cached per context: it does not depend on the topology)."""
    key = id(ctx)
    cached = _ROLE_CACHE.get(key)
    if cached is not None and cached.get("__ctx__") is ctx:
        return cached["roles"]
    roles: dict[str, set[str]] = defaultdict(set)
    for cell, types in ctx.cells.spaces.items():
        for t in types:
            for role in ctx.matrix.roles_of(t):
                roles[role].add(cell)
    _ROLE_CACHE[key] = {"__ctx__": ctx, "roles": roles}
    return roles


def matrix_zone_violations(ctx: ZoningContext, r: RealizedZones) -> list[str]:
    """Necessary conditions of the hard D pairs at cell level (prunes before the space level)."""
    if ctx.matrix is None:
        return []
    role_cells = _role_cells(ctx)
    out = []
    for p in ctx.matrix.pairs:
        if p.kind != "hard" or p.type != "D":
            continue
        if "patio" in (p.a, p.b):
            other = p.b if p.a == "patio" else p.a
            for cell in role_cells.get(other, ()):
                if cell in r.cells and _role_contact(ctx, r, cell, "garden") < ctx.min_contact - 1e-9:
                    out.append(f"matrix:{p.pair_id}")
            continue
        if "access" in (p.a, p.b):
            other = p.b if p.a == "access" else p.a
            entry_cells = [c for c in ctx.cells_of(ctx.profile.entry_zone) if c in r.cells]
            interval = ctx.intervals.get(ctx.profile.entry_interval)
            for cell in role_cells.get(other, ()):
                if cell not in r.cells or cell in entry_cells:
                    continue
                on_door = bool(interval) and _touches_interval(r, cell, interval) >= ctx.profile.entry_min_overlap - 1e-6
                if not on_door and not any(_pair_contact(r, cell, e, ctx.min_contact) >= ctx.min_contact - 1e-9
                                           for e in entry_cells):
                    out.append(f"matrix:{p.pair_id}")
            continue
        cells_a, cells_b = role_cells.get(p.a, set()), role_cells.get(p.b, set())
        open_pair = all(ctx.matrix.roles[x] <= ctx.passable_types for x in (p.a, p.b) if x in ctx.matrix.roles)
        for a in cells_a:
            if a in cells_b or not cells_b:
                continue
            if open_pair:
                ok = any(r.contact(a, b) >= ctx.min_contact - 1e-9 for b in cells_b)
            else:
                ok = any(_near(r, a, b, ctx.min_contact) for b in cells_b)
            if not ok:
                out.append(f"matrix:{p.pair_id}")
    pairs = {p.pair_id: p for p in ctx.matrix.pairs}
    for grp in ctx.matrix.groups:
        met = 0
        for pid in grp.pair_ids:
            p = pairs.get(pid)
            if p is None or "patio" not in (p.a, p.b):
                met += 1  # only patio members are checked at cell level
                continue
            other = p.b if p.a == "patio" else p.a
            if any(cell in r.cells and _role_contact(ctx, r, cell, "garden") >= ctx.min_contact - 1e-9
                   for cell in role_cells.get(other, ())):
                met += 1
        if met < grp.k:
            out.append(f"matrix:group:{grp.group_id}")
    return out


def iter_violations(ctx: ZoningContext, r: RealizedZones):
    """Hard violations, cheapest checks first; callers that only need one stop at the first."""
    cells = r.cells
    for cell, (x0, y0, x1, y1) in cells.items():
        if x1 - x0 < ctx.cells.min_width[cell] - 1e-9:
            yield (f"width:{cell}")
        if y1 - y0 < ctx.cells.min_width[cell] - 1e-9:
            yield (f"depth:{cell}")
    for cell in ctx.cells_of(Zone.GARAGE.value):
        if cell in cells and cells[cell][3] - cells[cell][1] < ctx.garage_min_depth - 1e-9:
            yield ("depth:garage_vehicle")
    entry = ctx.intervals.get(ctx.profile.entry_interval)
    if entry and _present(ctx, r, ctx.profile.entry_zone):
        if max((_touches_interval(r, c, entry) for c in ctx.cells_of(ctx.profile.entry_zone) if c in cells),
               default=0.0) < ctx.profile.entry_min_overlap - 1e-6:
            yield ("profile:entry")
    for res in anchor_results(ctx, r):
        if res["kind"] == "hard" and not res["satisfied"]:
            yield (f"anchor:{res['anchor_id']}")
    seq = entry_sequence_result(ctx, r)
    if seq and seq["kind"] == "hard" and not seq["satisfied"]:
        yield (f"anchor:{seq['anchor_id']}")
    for a, b, rid in ctx.constraints.adjacency_required:
        if _present(ctx, r, a) and _present(ctx, r, b) and _any_contact(ctx, r, a, b) < ctx.min_contact - 1e-9:
            yield (f"mandatory:{rid}")
    for a, b, rid in ctx.constraints.adjacency_forbidden:
        if any(r.contact(pa, pb) > 1e-9 for pa in ctx.cells_of(a) for pb in ctx.cells_of(b)
               if pa in cells and pb in cells):
            yield (f"forbidden:{rid}")
    for g in ctx.constraints.groups:
        if sum(a == b or _any_contact(ctx, r, a, b) >= ctx.min_contact - 1e-9 for a, b in g["members"]) < g["k"]:
            yield (f"group:{g['group_id']}")
    for zone, site, rid in ctx.constraints.facade_required:
        if not _present(ctx, r, zone):
            continue
        interval = ctx.intervals.get(site) if site in (SiteZone.ENTRY_DECK, SiteZone.DRIVEWAY) else None
        zone_cells = [c for c in ctx.cells_of(zone) if c in cells]
        if interval is not None:
            need = (interval[1] - interval[0]) if site == SiteZone.DRIVEWAY else ctx.min_contact
            ok = any(_touches_interval(r, c, interval) >= need - 1e-6 for c in zone_cells)
        else:
            facades = ctx.site_facades.get(site, [])
            ok = any(r.facade_contacts(c).get(f, 0.0) >= ctx.min_contact - 1e-9 for c in zone_cells for f in facades)
        if not ok:
            yield (f"facade:{rid}")
    yield from matrix_zone_violations(ctx, r)


def front_precheck(ctx: ZoningContext, topology: ZoneTopology) -> str | None:
    """Cheap test of the access-side intervals (entry, deck, driveway) from x-ranges only, before realizing.

    Exact for strategies A and B (stepped): front-facing cells are the first cell of each front column and
    the first cell of the through column, and their x-ranges depend only on areas (not on the spine).
    Skipped for the polygonal mode (column cuts follow the oblique lines; the full check runs after realizing).
    """
    areas = ctx.areas
    if ctx.band_model is not None and ctx.band_model.mode == "polygonal":
        return _polygonal_front_precheck(ctx, topology)
    if ctx.band_model is not None:
        if topology.through or not topology.front:
            return None
        fa = sum(areas[z] for col in topology.front for z in col)
        bands = ctx.band_model.band_layout(ctx.domain, fa, sum(areas.values()) - fa, ctx.spine_width)
        if bands is None:
            return "not_realizable"
        _, _, x0, x1 = bands[0]
    else:
        x0, _, x1, _ = ctx.footprint
    ranges: dict[str, tuple[float, float]] = {}
    if topology.through:
        total = sum(areas[z] for z in topology.zones())
        t_width = (x1 - x0) * sum(areas[z] for z in topology.through) / total
        if topology.through_side == "left":
            ranges[topology.through[0]] = (x0, x0 + t_width)
            x0 += t_width
        else:
            ranges[topology.through[0]] = (x1 - t_width, x1)
            x1 -= t_width
    band = sum(areas[z] for col in topology.front for z in col)
    widths = [(x1 - x0) * sum(areas[z] for z in col) / band for col in topology.front]
    if ctx.width_floor:
        fitted = fit_lengths(widths, [max(ctx.width_floor.get(z, 0.0) for z in col) for col in topology.front])
        if fitted is None or (ctx.max_area_shift is not None and any(
                abs(f - w) > ctx.max_area_shift * w + 1e-9 for f, w in zip(fitted, widths))):
            return "not_realizable"
        widths = fitted
    cursor = x0
    for col, width in zip(topology.front, widths):
        ranges[col[0]] = (cursor, cursor + width)
        cursor += width
    if not topology.front and not topology.through:
        return None

    def overlap(cells, interval):
        return max((min(ranges[c][1], interval[1]) - max(ranges[c][0], interval[0]) for c in cells if c in ranges),
                   default=0.0)

    entry = ctx.intervals.get(ctx.profile.entry_interval)
    entry_cells = [c for c in ctx.cells_of(ctx.profile.entry_zone) if c in areas]
    if entry and entry_cells and overlap(entry_cells, entry) < ctx.profile.entry_min_overlap - 1e-6:
        return "profile:entry"
    for zone, site, rid in ctx.constraints.facade_required:
        interval = ctx.intervals.get(site) if site in (SiteZone.ENTRY_DECK, SiteZone.DRIVEWAY) else None
        cells = [c for c in ctx.cells_of(zone) if c in areas]
        if interval is None or not cells:
            continue
        need = (interval[1] - interval[0]) if site == SiteZone.DRIVEWAY else ctx.min_contact
        if overlap(cells, interval) < need - 1e-6:
            return f"facade:{rid}"
    return None


def _polygonal_front_precheck(ctx: ZoningContext, topology: ZoneTopology) -> str | None:
    """Polygonal mode: front-line spans of the front columns from the area cuts of the front band only."""
    if topology.through or not topology.front:
        return None
    areas, prof = ctx.areas, ctx.domain.profile
    fa = sum(areas[z] for col in topology.front for z in col)
    bands = ctx.band_model.band_layout(ctx.domain, fa, sum(areas.values()) - fa, ctx.spine_width)
    if bands is None:
        return "not_realizable"
    y0, y1, _, _ = bands[0]
    xl, xr = prof.interval(ctx.domain.y_front)
    fit = polygonal_cuts(prof, y0, y1, topology.front, areas, ctx.width_floor or None, ctx.max_area_shift)
    if fit is None:
        return "not_realizable"
    cuts = fit[0]
    ranges = {col[0]: (max(cuts[i], xl), min(cuts[i + 1], xr)) for i, col in enumerate(topology.front)}

    def overlap(cells, interval):
        return max((min(ranges[c][1], interval[1]) - max(ranges[c][0], interval[0]) for c in cells if c in ranges),
                   default=0.0)

    entry = ctx.intervals.get(ctx.profile.entry_interval)
    entry_cells = [c for c in ctx.cells_of(ctx.profile.entry_zone) if c in areas]
    if entry and entry_cells and overlap(entry_cells, entry) < ctx.profile.entry_min_overlap - 1e-6:
        return "profile:entry"
    for zone, site, rid in ctx.constraints.facade_required:
        interval = ctx.intervals.get(site) if site in (SiteZone.ENTRY_DECK, SiteZone.DRIVEWAY) else None
        cells = [c for c in ctx.cells_of(zone) if c in areas]
        if interval is None or not cells:
            continue
        need = (interval[1] - interval[0]) if site == SiteZone.DRIVEWAY else ctx.min_contact
        if overlap(cells, interval) < need - 1e-6:
            return f"facade:{rid}"
    return None


def hard_violations(ctx: ZoningContext, r: RealizedZones) -> list[str]:
    return list(iter_violations(ctx, r))


def first_violation(ctx: ZoningContext, r: RealizedZones) -> str | None:
    return next(iter_violations(ctx, r), None)


def score(ctx: ZoningContext, r: RealizedZones) -> dict:
    satisfied, total_w, sat_w = [], 0.0, 0.0
    for a, b, w, rid in ctx.constraints.desired:
        total_w += w
        if _any_contact(ctx, r, a, b) >= ctx.min_contact - 1e-9:
            satisfied.append(rid)
            sat_w += w
    for zone, site, w, rid in ctx.constraints.facade_desired:
        total_w += w
        facades = ctx.site_facades.get(site, [])
        if any(r.facade_contacts(c).get(f, 0.0) >= ctx.min_contact - 1e-9
               for c in ctx.cells_of(zone) if c in r.cells for f in facades):
            satisfied.append(rid)
            sat_w += w
    soft = {a.anchor_id: a.weight for a in ctx.profile.anchors if a.kind == "soft"}
    fallback = {a.anchor_id: a for a in ctx.profile.anchors if a.fallback_role}
    for res in anchor_results(ctx, r):
        if res["anchor_id"] in soft and res["applicable"]:
            total_w += soft[res["anchor_id"]]
            if res["satisfied"]:
                satisfied.append(res["anchor_id"])
                sat_w += soft[res["anchor_id"]]
        a = fallback.get(res["anchor_id"])
        if a and res["applicable"] and res["satisfied"] and res.get("via_role") == a.fallback_role:
            total_w += a.fallback_penalty  # met through the fallback facade: counts as a missed soft relation
    relations = sat_w / total_w if total_w else 1.0
    raw, length = 0.0, 0.0
    exterior = set(ctx.facades_with("exterior"))
    for cell in r.cells:
        for facade, contact in r.facade_contacts(cell).items():
            if facade in exterior:
                raw += ctx.affinity[ctx.parent(cell)].get(facade, 0.0) * contact
                length += contact
    orientation = raw / length if length else 0.0
    shapes = []
    for x0, y0, x1, y1 in r.cells.values():
        w, d = x1 - x0, y1 - y0
        shapes.append(min(1.0, ctx.max_aspect / (max(w, d) / min(w, d))) if min(w, d) > 1e-9 else 0.0)
    shape = sum(shapes) / len(shapes)
    wt = ctx.weights
    total = (wt["relations"] * relations + wt["orientation"] * orientation + wt["shape"] * shape) / sum(wt.values())
    return {"total": total, "relations": relations, "orientation": orientation, "orientation_raw": raw,
            "shape": shape, "satisfied_relations": satisfied}


# --------------------------------------------------------------------------- search


def zone_scheme(ctx: ZoningContext, topology: ZoneTopology, r: RealizedZones, scores: dict) -> dict:
    cells = list(r.cells)
    adjacency = [{"a": a, "b": b, "contact_ft": r.contact(a, b)}
                 for a, b in itertools.combinations(cells, 2) if r.contact(a, b) > 1e-9]
    no_door = {frozenset((a, b)) for a, b, _ in ctx.constraints.no_door}
    for e in adjacency:
        e["door_allowed"] = frozenset((ctx.parent(e["a"]), ctx.parent(e["b"]))) not in no_door
    return {
        "footprint_variant": ctx.footprint_variant + (f"/joint_{ctx.joint}" if ctx.joint else ""),
        "footprint_local": list(r.footprint),
        "topology": {"front": [list(c) for c in topology.front], "rear": [list(c) for c in topology.rear],
                     "through": list(topology.through), "through_side": topology.through_side if topology.through else None,
                     "key": topology.key},
        "front_depth_ft": r.front_depth,
        "rear_depth_ft": r.rear_depth,
        "spine_local": list(r.spine) if r.spine else None,
        "cells": {c: {"zone": ctx.parent(c), "spaces": sorted(ctx.cells.spaces[c]), "rect_local": list(rect),
                      "area_sqft": r.areas.get(c, (rect[2] - rect[0]) * (rect[3] - rect[1])),
                      "facades": r.facade_contacts(c)}
                  for c, rect in r.cells.items()},
        "realization": realization_summary(ctx, r),
        "adjacency": adjacency,
        "split_zones": {z: list(c) for z, c in ctx.cells.parts.items()},
        "anchors": anchor_results(ctx, r),
        "entry_sequence": entry_sequence_result(ctx, r),
        "scores": scores,
    }


def realization_summary(ctx: ZoningContext, r: RealizedZones) -> dict:
    """Footprint actually realized: steps or slabs, shoulders, polygonal reserve and envelope use."""
    out = {"mode": r.mode, "joint": r.joint, "footprint_area_sqft": r.footprint_area, "footprint_bbox_local": list(r.footprint),
           "steps_local": [list(s) for s in r.steps], "shoulders": {}, "wedges": [], "wedge_area_sqft": 0.0,
           "y_front": ctx.domain.y_front if ctx.domain else ctx.footprint[1], "envelope_use": None}
    for cell in r.cells:
        for fid in SHOULDER_FACADES:
            length = r.facade_contacts(cell).get(fid, 0.0)
            if length > 1e-6:
                out["shoulders"].setdefault(fid, {})[cell] = length
    for w in r.wedges:
        out["wedges"].append({"band": w["band"], "side": w["side"], "y_range": list(w["y_range"]),
                              "area_sqft": w["area"], "adjacent_cells": list(w["adjacent_cells"])})
    out["wedge_area_sqft"] = sum(w["area"] for w in r.wedges)
    out["area_shift"] = {c: a / ctx.areas[c] - 1.0 for c, a in r.areas.items()
                         if c in ctx.areas and abs(a / ctx.areas[c] - 1.0) > 1e-6}
    if ctx.domain is not None and ctx.domain.profile is not None:
        prof = ctx.domain.profile
        held = prof.strip_area(r.footprint[1], r.footprint[3])
        out["envelope_use"] = r.footprint_area / held if held > 0 else None
    return out


def zone_floor(contexts: list[ZoningContext], strategy: RealizationStrategy, top_k: int) -> dict:
    failures: Counter = Counter()
    valid = []
    count = 0
    for ctx in contexts:
        must_front, must_rear = required_bands(ctx)
        x0, y0, x1, y1 = ctx.footprint
        total = sum(ctx.areas.values())
        vehicle = set(ctx.cells_of(Zone.GARAGE.value))

        def through_ok(column, ctx=ctx, total=total, x0=x0, y0=y0, x1=x1, y1=y1, vehicle=vehicle):
            return _column_ok(column, ctx.areas, ctx.cells.min_width,
                              BandGeometry(x1 - x0, y1 - y0, total), vehicle, ctx.garage_min_depth)

        topologies = enumerate_with_through(
            list(ctx.areas), ctx.max_per_column, must_front, must_rear, ctx.max_through,
            lambda subset, ctx=ctx: (band_depth_filter(ctx, subset), column_filter(ctx, subset)), through_ok)
        for topology in topologies:
            count += 1
            quick = front_precheck(ctx, topology)
            if quick:
                failures[quick.split(":")[0]] += 1
                continue
            if ctx.width_floor:
                joint = ((ctx.joint, ctx.joint_width, ctx.cells_of(Zone.CIRCULATION.value), ctx.min_contact)
                         if ctx.joint else None)
                r = strategy.realize(ctx.realize_input, topology, ctx.areas, ctx.spine_width, ctx.width_floor,
                                     ctx.max_area_shift, joint)
            else:
                r = strategy.realize(ctx.realize_input, topology, ctx.areas, ctx.spine_width)
            if r is None:
                failures["not_realizable"] += 1
                continue
            violation = first_violation(ctx, r)
            if violation:
                failures[violation.split(":")[0]] += 1
                continue
            valid.append((score(ctx, r), topology, r, ctx))
    valid.sort(key=lambda v: (-v[0]["total"], v[3].footprint_variant, v[1].key))
    schemes, seen = [], set()
    for scores, topology, r, ctx in valid:
        front = frozenset(ctx.parent(c) for col in topology.front for c in col)
        first = ctx.parent(topology.front[0][0]) if topology.front else None
        concept = (front, first, ctx.cells.split)
        if concept in seen:
            continue
        seen.add(concept)
        schemes.append(zone_scheme(ctx, topology, r, scores))
        if len(schemes) == top_k:
            break
    for rank, scheme in enumerate(schemes, start=1):
        scheme["rank"] = rank
    return {"strategy": strategy.name, "variants_searched": len(contexts), "enumerated": count,
            "valid": len(valid), "failures_by_first_violation": dict(sorted(failures.items())), "schemes": schemes,
            "diagnostics": [] if schemes else [front_width_diagnostic(ctx) for ctx in contexts], "_valid": valid}


def front_width_diagnostic(ctx: ZoningContext) -> dict:
    """Minimum frontage the cells forced onto the access side need, against the footprint width."""
    must_front, _ = required_bands(ctx)
    driveway = ctx.intervals.get(SiteZone.DRIVEWAY.value)
    demand = {}
    for cell in sorted(must_front):
        need = ctx.cells.min_width[cell]
        if ctx.parent(cell) == Zone.GARAGE and driveway:
            need = max(need, driveway[1] - driveway[0])
        demand[cell] = need
    width = ctx.domain.profile.width(ctx.domain.y_front) if ctx.domain else ctx.footprint[2] - ctx.footprint[0]
    return {"footprint_variant": ctx.footprint_variant, "split": list(ctx.cells.split),
            "front_width_ft": width, "front_min_demand_ft": sum(demand.values()), "demand_by_cell": demand,
            "front_fits": sum(demand.values()) <= width + 1e-9}


def make_contexts(
    catalog: Catalog,
    brief: dict,
    footprint_area: float,
    candidates: list[dict],
    facade_roles: dict[str, frozenset[str]],
    affinity: dict[str, dict[str, float]],
    strategy: RealizationStrategy | None = None,
    profile_b=None,
) -> list[ZoningContext]:
    """One context per footprint candidate x zone-split variant.

    With strategy B the candidate's front line and the envelope profile define the footprint domain;
    through columns are disabled (a full-depth column cannot follow two band widths).
    """
    zoning = catalog.data["zoning"]
    band_model = strategy if isinstance(strategy, StrategyB) else None
    garage_depth = site_parameters(catalog, "driveway")["depth_ft"] * garage_depth_factor(catalog, brief["program"])
    from spaceplan.modules.zoning.lib.relation_matrix import load_matrix

    profile = load_profile(catalog, brief["dwelling_type"], brief.get("zoning_overrides", {}).get("anchors"))
    matrix = load_matrix(catalog, brief["dwelling_type"], brief.get("relation_overrides"))
    out = []
    spine = catalog.data["circulation"]["design_width_ft"]
    circulations = [(0.0, None), (spine, None)]
    if band_model is not None and band_model.mode == "rectangle" and zoning.get("joint_articulation", True):
        circulations += [(0.0, "left"), (0.0, "right")]
    for split, merges, cand, (spine_w, joint) in itertools.product(
            split_options(catalog, brief["program"], brief["dwelling_type"]),
            merge_options(catalog, brief["program"]), candidates, circulations):
        x0, y0, x1, y1 = cand["rect_local"]
        domain = None
        if band_model is not None:
            domain = FootprintDomain(tuple(cand["rect_local"]), profile_b, cand["realization"]["y_front"])
        cells = cell_model(catalog, brief["program"], footprint_area - spine_w * (x1 - x0), split, merges)
        constraints = constraints_from_brief(brief, {catalog_zone for catalog_zone in ZONES
                                                     if any(c == catalog_zone or c.startswith(catalog_zone + "_")
                                                            for c in cells.areas)}, merges)
        if True:
            out.append(ZoningContext(
                footprint=tuple(cand["rect_local"]),
                footprint_variant=cand["footprint_variant"],
                cells=cells,
                constraints=constraints,
                profile=profile,
                facade_roles=facade_roles,
                affinity=affinity,
                intervals={k: (tuple(v) if v else None) for k, v in cand["intervals"].items()},
                garage_min_depth=garage_depth,
                min_contact=zoning["min_contact_ft"],
                max_aspect=zoning["max_aspect_ratio"],
                max_per_column=zoning["max_zones_per_column"],
                weights=zoning["weights"],
                site_facades=zoning["site_facades"],
                matrix=matrix,
                spine_width=spine_w,
                max_through=0 if band_model is not None else zoning["max_through_column"],
                passable_types=frozenset(t["space_type"] for t in catalog.data["space_types"] if t["passable"]),
                domain=domain,
                band_model=band_model,
                width_floor=_width_floor(cells, cand, zoning) if band_model is not None else {},
                max_area_shift=zoning.get("max_area_shift"),
                joint=joint,
                joint_width=spine if joint else 0.0,
            ))
    return out


def _width_floor(cells: CellModel, cand: dict, zoning: dict) -> dict[str, float]:
    """Minimum column width of every cell: its zone minimum, and the driveway width for the garage."""
    floor = dict(cells.min_width)
    driveway = cand["intervals"].get(SiteZone.DRIVEWAY.value)
    if driveway:
        for c in floor:
            if c == Zone.GARAGE.value or c.startswith(Zone.GARAGE.value + "_"):
                floor[c] = max(floor[c], driveway[1] - driveway[0])
    return floor


def frontage_diagnostics(catalog: Catalog, brief: dict, footprint_area: float, with_shoulders: bool,
                         driveway_width: float) -> list[dict]:
    """Frontage the cells forced onto the access side need, independent of any lot (one row per zone-split
    variant). with_shoulders: street-facing shoulders exist (strategy B), so an anchor with a shoulder
    fallback no longer forces its cells onto the front line."""
    facades = [{"facade_id": f, "faces": faces} for f, faces in
               (("front", "front_yard"), ("rear", "garden"), ("left", "side_yard"), ("right", "side_yard"))]
    if with_shoulders:
        facades += [{"facade_id": f, "faces": f} for f in SHOULDER_FACADES]
    roles = house_facade_roles({"facades": facades}, catalog)
    affinity = {z: {f["facade_id"]: 0.0 for f in facades} for z in ZONES}
    width = 1000.0
    candidate = {"footprint_variant": "frontage_probe", "rect_local": [0.0, 0.0, width, footprint_area / width],
                 "intervals": {"entry_deck": [0.0, 1.0], "driveway": [1.0, 1.0 + driveway_width] if driveway_width else None}}
    contexts = make_contexts(catalog, brief, footprint_area, [candidate], roles, affinity)
    seen, out = set(), []
    for ctx in contexts:
        d = front_width_diagnostic(ctx)
        key = (tuple(sorted(d["demand_by_cell"].items())))
        if key not in seen:
            seen.add(key)
            out.append(d)
    return out


def garage_depth_factor(catalog: Catalog, program: dict) -> float:
    """Vehicles parked one behind the other per lane (2 for a tandem garage, 1 otherwise)."""
    for s in program["spaces"]:
        if s["zone"] == Zone.GARAGE.value and catalog.has_space_type(s.get("space_type")):
            t = catalog.space_type(s["space_type"])
            if t.get("vehicles") and t.get("lanes"):
                return t["vehicles"] / t["lanes"]
    return 1.0


def constraint_summary(c: ZoningConstraints, profile: Profile) -> dict:
    return {
        "adjacency_required": [rid for *_, rid in c.adjacency_required],
        "adjacency_forbidden": [rid for *_, rid in c.adjacency_forbidden],
        "no_door": [rid for *_, rid in c.no_door],
        "groups": [g["group_id"] for g in c.groups],
        "facade_required": [rid for *_, rid in c.facade_required],
        "desired": [rid for *_, rid in c.desired] + [rid for *_, rid in c.facade_desired],
        "profile_anchors": [f"{a.anchor_id}:{a.kind}" for a in profile.anchors]
        + ([f"{profile.entry_sequence['anchor_id']}:{profile.entry_sequence['kind']}"] if profile.entry_sequence else []),
        "skipped": c.skipped,
    }


# --------------------------------------------------------------------------- drivers


HOUSE_FACE_ROLES = {
    "front_yard": ("main_street", "street", "access", "exterior"),
    "garden": ("garden", "exterior"),
    "side_yard": ("side_yard", "exterior"),
    "street_side_yard": ("street", "exterior"),
}


def house_facade_roles(option: dict, catalog: Catalog | None = None) -> dict[str, frozenset[str]]:
    """Roles of every facade; shoulder facades (strategy B) take their roles from the catalog."""
    shoulders = catalog.data["zoning"].get("shoulder_facades", {}) if catalog else {}
    out = {}
    for f in option["facades"]:
        if f["faces"] in shoulders:
            out[f["facade_id"]] = frozenset(shoulders[f["faces"]]["roles"])
        else:
            out[f["facade_id"]] = frozenset(HOUSE_FACE_ROLES[f["faces"]])
    return out


def _space_level(catalog: Catalog, brief: dict, result: dict, frame, search: dict | None = None) -> dict:
    """Level 2 on the zone candidates; replaces result['schemes'] by space-level schemes.

    search: optional override of the space-level search caps (catalog circulation.search_retry).
    """
    from shapely.geometry import box

    from spaceplan.core.lib.rules import CRC_RULESET, load_ruleset_resource
    from spaceplan.modules.zoning.lib.circulation import DoorRules
    from spaceplan.modules.zoning.lib.space_layout import (
        LayoutContext,
        layout_candidates,
        layout_params,
        space_scheme,
        space_specs,
    )

    crc = load_ruleset_resource(*CRC_RULESET)
    params = layout_params(catalog, crc)
    if search:
        from dataclasses import replace

        params = replace(params, zone_schemes=search["zone_schemes"], per_hall_side=search["options_per_hall_side"],
                         without_hall=search["options_without_hall"],
                         max_combinations=search["max_combinations_per_scheme"])
    garage_zones = frozenset(z for g in brief["relation_groups"] for m in g["members"]
                             for z in (m["a"], m["b"]) if Zone.GARAGE.value in (m["a"], m["b"]) and z in ZONES) \
        - {Zone.GARAGE.value}

    def build_lc(zctx: ZoningContext, realized) -> LayoutContext:
        specs, hosts = space_specs(catalog, crc, brief["program"], zctx.cells, zctx.matrix)
        rules = DoorRules(
            door_contact=params.door_contact, matrix=zctx.matrix,
            no_door_zones=frozenset(frozenset((a, b)) for a, b, _ in zctx.constraints.no_door),
            garage_zones=garage_zones, entry_zone=zctx.profile.entry_zone,
            entry_interval=zctx.intervals.get(zctx.profile.entry_interval),
            entry_min_overlap=zctx.profile.entry_min_overlap, footprint=realized.footprint,
            patio_facades=tuple(zctx.facades_with("garden")),
            private_roles=frozenset(catalog.data["circulation"]["private_roles"]))
        footprint_area = realized.footprint_area
        forbidden = tuple((r["a"], r["b"]) for r in brief["relations"]
                          if r["type"] == "forbidden" and r.get("applies_to", "adjacency") == "adjacency"
                          and r["a"] in ZONES and r["b"] in ZONES)
        return LayoutContext(params, zctx.matrix, rules, specs, hosts, footprint_area, realized.spine, forbidden)

    valid = result.pop("_valid")
    zone_schemes = result.pop("schemes")
    level = layout_candidates(valid, build_lc, frame, catalog.data["zoning"]["top_k"], params)
    schemes = []
    for rank, (total, zscores, topology, realized, zctx, lc, combo, res) in enumerate(level.pop("chosen"), start=1):
        scheme = zone_scheme(zctx, topology, realized, zscores)
        polygons = cell_polygons(zctx, realized)
        for cid, cell in scheme["cells"].items():
            cell["polygon"] = frame.to_world(polygons[cid])
            if realized.mode == "polygonal":
                cell["polygon_local"] = [list(p) for p in polygons[cid].exterior.coords]
        scheme.update(space_scheme(lc, combo, res, frame))
        if realized.mode == "polygonal":
            from spaceplan.modules.zoning.lib.polygonal import policy_from_catalog

            extend_scheme_spaces(scheme, polygons, frame, policy_from_catalog(catalog.data))
        add_wedge_polygons(scheme, zctx, realized, frame)
        scheme["scores"] = {**zscores, "zone_total": zscores["total"], "total": total}
        scheme["rank"] = rank
        schemes.append(scheme)
    result["zone_level_best"] = [s["topology"]["key"] for s in zone_schemes]
    result["space_level"] = level
    result["schemes"] = schemes
    return result


def cell_polygons(ctx: ZoningContext, r: RealizedZones) -> dict:
    """Shapely polygon of every cell in the local frame (BP: envelope clipped to the cell's extent)."""
    from shapely.geometry import Polygon, box

    if r.mode != "polygonal" or r.extents is None:
        return {c: box(*rect) for c, rect in r.cells.items()}
    env = Polygon(ctx.domain.profile.vertices)
    bx0, _, bx1, _ = env.bounds
    out = {}
    for c, (c0, ya, c1, yb) in r.extents.items():
        out[c] = env.intersection(box(max(c0, bx0 - 1.0), ya, min(c1, bx1 + 1.0), yb))
    return out


def extend_scheme_spaces(scheme: dict, cell_polys: dict, frame, policy) -> None:
    """Polygonal mode: hand the part of each cell outside its core to the spaces and halls touching it,
    following the habitability-aware policy (see lib/polygonal.py); record residual pieces and decisions."""
    from shapely.geometry import box

    from spaceplan.modules.zoning.lib.polygonal import Member, extend_members

    items = [(sid, sp["cell"], tuple(sp["rect_local"]), sp["space_type"]) for sid, sp in scheme["spaces"].items()]
    items += [(h["hall_id"], h["cell"], tuple(h["rect_local"]), "hall") for h in scheme["halls"] if h["cell"] != "spine"]
    report = {"residual": [], "decisions": [], "residual_area_sqft": 0.0, "trapezoid_spaces": []}
    for cid, cell in scheme["cells"].items():
        members = {nid: Member(rect, stype) for nid, c, rect, stype in items if c == cid}
        if not members:
            continue
        polys, residual, log = extend_members(cell_polys[cid], box(*cell["rect_local"]), members, policy)
        for row in log:
            report["decisions"].append({"cell": cid, **row})
        for res in residual:
            report["residual"].append({"cell": cid, "near": res["near"], "area_sqft": res["area_sqft"],
                                       "reason": res["reason"], "polygon": frame.to_world(res["geometry"])})
            report["residual_area_sqft"] += res["area_sqft"]
        for nid, poly in polys.items():
            extension = poly.area - box(*members[nid].rect).area
            if extension <= 1e-6:
                continue
            target = scheme["spaces"].get(nid) or next(h for h in scheme["halls"] if h["hall_id"] == nid)
            target["extension_sqft"] = extension
            target["polygon"] = frame.to_world(poly)
            target["polygon_local"] = [list(p) for p in poly.exterior.coords]
            if nid in scheme["spaces"]:
                target["core_area_sqft"] = target["area_sqft"]
                target["area_sqft"] = poly.area
                target["net_area_sqft"] = poly.area - target["through_strip_sqft"]
                report["trapezoid_spaces"].append(nid)
    scheme["realization"]["polygonal_extension"] = report


def add_wedge_polygons(scheme: dict, ctx: ZoningContext, r: RealizedZones, frame) -> None:
    """Stepped mode: polygons of the reserve between each step and the oblique lot lines."""
    if not r.wedges or ctx.domain is None:
        return
    from shapely.geometry import Polygon, box

    env = Polygon(ctx.domain.profile.vertices)
    bx0, _, bx1, _ = env.bounds
    for w, out in zip(r.wedges, scheme["realization"]["wedges"]):
        y0, y1 = w["y_range"]
        rect = box(bx0 - 1.0, y0, w["x_limit"], y1) if w["side"] == "left" else box(w["x_limit"], y0, bx1 + 1.0, y1)
        out["polygon"] = frame.to_world(env.intersection(rect))


def _status(result: dict) -> tuple[str, str | None]:
    if result["schemes"]:
        return "zoned", None
    if result["valid"]:
        return "no_valid_space_layout", "zone topologies exist but no space layout meets reachability and the hard D pairs"
    return "no_valid_scheme", "every topology violates a hard constraint"


def zone_site_options(catalog: Catalog, brief: dict, frame, site_partition: dict, strategy: RealizationStrategy,
                      envelope_profile=None, options: tuple[str, ...] | None = None, retry: bool = True) -> dict:
    """House: zone every one-floor site option over its compliant footprint candidates.

    Strategy B needs the envelope section profile in the local frame. options restricts the run to some
    option ids (the correction search zones n1 only). retry: when zone schemes exist but no space layout is
    found, search once more with the wider caps of catalog circulation.search_retry.
    """
    top_k = catalog.data["zoning"]["top_k"]
    profile = load_profile(catalog, "house", brief.get("zoning_overrides", {}).get("anchors"))
    results = []
    for option in site_partition["options"]:
        if options is not None and option["option_id"] not in options:
            continue
        entry = {"option_id": option["option_id"], "floors": option["floors"]}
        if "zones" not in option:
            results.append({**entry, "status": "not_feasible", "reason": "; ".join(option["reasons"])})
            continue
        if option["floors"] > 1:
            results.append({**entry, "status": "deferred_to_stacking", "reason": "multi-floor zoning is step 7"})
            continue
        if not any(c["normative_ok"] for c in option["footprint_candidates"]):
            failed = [c["check_id"] for c in option.get("checks", []) if c["kind"] == "normative" and not c["passes"]]
            results.append({**entry, "status": "not_feasible",
                            "reason": "no compliant footprint candidate (site checks: " + ", ".join(failed) + ")"})
            continue
        candidates = []
        for c in option["footprint_candidates"]:
            if not c["normative_ok"]:
                continue
            for a in c.get("access_options") or [None]:
                if a is None:
                    candidates.append(c)
                    continue
                candidates.append({**c, "footprint_variant": f"{c['footprint_variant']}/deck_{a['deck_position']}",
                                   "intervals": {"entry_deck": a["deck_interval_ft"], "driveway": a["driveway_interval_ft"]}})
        roles = house_facade_roles(option, catalog)
        contexts = make_contexts(catalog, brief, option["footprint_area_sqft"], candidates, roles,
                                 option["zone_facade_affinity"], strategy, envelope_profile)
        zoned = zone_floor(contexts, strategy, top_k)
        result = _space_level(catalog, brief, dict(zoned), frame)
        status, reason = _status(result)
        wider = catalog.data["circulation"].get("search_retry")
        if retry and wider and status == "no_valid_space_layout":
            second = _space_level(catalog, brief, dict(zoned), frame, wider)
            second["space_level"]["retry"] = {"applied": True, "first_run": result["space_level"]}
            result = second
            status, reason = _status(result)
        results.append({
            **entry,
            "status": status,
            "reason": reason,
            "profile": "house",
            "facade_roles": {f: sorted(r) for f, r in roles.items()},
            "footprint_candidates": [c["footprint_variant"] for c in candidates],
            "zone_areas_sqft": contexts[0].cells.areas if contexts else {},
            "constraints": constraint_summary(contexts[0].constraints, profile) if contexts else None,
            **result,
        })
    return {"strategy": strategy.name, "dwelling_type": "house", "options": results}


def zone_unit(catalog: Catalog, brief: dict, unit, strategy: RealizationStrategy) -> dict:
    """Apartment: zone the unit rectangle with the apartment profile."""
    from spaceplan.modules.site.lib.orientation import (
        exposure,
        facade_affinity,
        local_normal_azimuth,
    )

    model = catalog.data["orientation_model"]
    north, lat = brief["orientation"]["north_azimuth_deg"], brief["orientation"]["latitude_deg"]
    normals = {"front": (0.0, -1.0), "right": (1.0, 0.0), "rear": (0.0, 1.0), "left": (-1.0, 0.0)}
    facades = []
    for fid, (nx, ny) in normals.items():
        az = local_normal_azimuth(unit.frame, nx, ny, north)
        facades.append({"facade_id": fid, "azimuth_deg": az, **exposure(az, lat, model), "street_exposure": 0.0})
    affinity = facade_affinity(catalog, facades)
    candidate = {"footprint_variant": "unit_rectangle", "rect_local": list(unit.rect_local),
                 "intervals": {"entrance": list(unit.entrance_interval)}}
    contexts = make_contexts(catalog, brief, unit.rect_area, [candidate], unit.facade_roles, affinity)
    result = _space_level(catalog, brief, zone_floor(contexts, strategy, catalog.data["zoning"]["top_k"]), unit.frame)
    profile = load_profile(catalog, "apartment", brief.get("zoning_overrides", {}).get("anchors"))
    status, reason = _status(result)
    option = {
        "option_id": "unit", "floors": 1,
        "status": status,
        "reason": reason,
        "profile": "apartment",
        "facade_roles": {f: sorted(r) for f, r in unit.facade_roles.items()},
        "footprint_candidates": ["unit_rectangle"],
        "zone_areas_sqft": contexts[0].cells.areas,
        "constraints": constraint_summary(contexts[0].constraints, profile),
        **result,
    }
    return {"strategy": strategy.name, "dwelling_type": "apartment", "options": [option]}


__all__ = [
    "Anchor", "CellModel", "Profile", "ZoningConstraints", "ZoningContext", "band_arrangements", "cell_model",
    "constraint_summary", "constraints_from_brief", "enumerate_topologies", "load_profile", "make_contexts",
    "required_bands", "split_options", "zone_floor", "zone_site_options", "zone_unit", "house_facade_roles",
]
