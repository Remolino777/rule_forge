"""Spaces inside one zone unit (step 6.7a S2.1): guillotine rectangles on the S2 grid, halls, closets from leftovers.

For a unit with n spaces the options are the guillotine arrangements of its spaces (columns along x or y, up to
max_stack spaces per column), cut where the unit's free cells match each space's scaled target (client decision E2:
rectangles). A unit with hall_min_terminals or more rooms that open only onto circulation is also tried with a hall
strip of the design width along each side. Each space is its rectangle clipped to the unit (the stair, a vestibule or
the void may bite a corner).

Hard here: minimum area (catalog, C01 for habitable rooms), least side of the largest rectangle (catalog, C01, C06 for
halls), the exterior wall of habitable and sleeping rooms (O03 via C03, O01). The part of a space outside its largest
rectangle becomes a closet when it is big enough and its space may host one (E5); otherwise it stays in the space.

Step S2.2b (client decisions 2026-10-11) reads the design registry through SpaceRules:
  * one space, one piece: a part cut off its space joins the neighbour that shares the most wall with it (halls
    follow the S2 circulation zone until S2.2d);
  * small spaces are sized to their typical size (the rest goes to the habitable rooms) and the whole-wall types
    (closet, laundry closet, pantry) cover the whole wall they share with their room;
  * closets carved across a whole short wall: the bath closet takes the length of a long bath beyond its preferred
    ratio, a reach-in closet shortens a long bedroom, a linen closet closes the quieter end of the upper hall;
  * hard proportion and furniture for the types the profile marks hard (baths, dining room, kitchen by any allowed
    template; bedrooms with 36 in around the bed); least side without tolerance in habitable rooms;
  * score: shape per type (preferred and maximum ratio, longest side, worst space), furniture that fits, fit to
    target, circulation (rectangular halls of limited length) and light (daylit depth of N spaces, facade surplus,
    facade held by M spaces, cross ventilation).

Step S2.2c-d (client decisions 2026-10-12): the suite is ordered suite -> walk-in -> bath; the maximum profile weighs
shape more (`shape_weighted`); on the upper floor each unit is also tried with its spaces at their optimal areas and
the rest as open air on the facade (`_roof_spec`, `_roof_piece`): a lower roof, or a terrace at most the registry depth
along the whole wall of the room it serves (`_terraces`); open-air cells are outside for the facade checks and leave
the floor in `compose`.
"""

from __future__ import annotations

import itertools
import math
import random
import zlib
from dataclasses import dataclass

import numpy as np
from scipy.ndimage import distance_transform_edt

from spaceplan.modules.design.lib.area_criteria import drawn_cap
from spaceplan.modules.stacking.lib.space_rules import SpaceRules
from spaceplan.modules.stacking.lib.unit_frame import (
    SpaceFloor,
    SpaceSpec,
    UnitFrame,
    d_pair,
    spec_of,
)
from spaceplan.modules.stacking.lib_aux.space_grid import (
    Guillotine,
    components,
    exposed_sides,
    exterior_cells,
    exterior_run,
    fits_in_mask,
    largest_rect,
    mask_bounds,
    realize,
    shared_edge,
)
from spaceplan.modules.stacking.lib_aux.structure_grid import box_lines
from spaceplan.modules.zoning.lib.band_enumeration import band_arrangements

HALL_TYPE = "hall"
NO_HALL = "none"


@dataclass(frozen=True, eq=False)
class Piece:
    """A placed space (or a hall / closet the layout adds): its cells inside the unit box."""

    spec: SpaceSpec
    mask: np.ndarray                      # cells in the unit box
    rect: tuple[int, int, int, int]       # largest rectangle (whole-floor indices)

    @property
    def cells(self) -> int:
        return int(self.mask.sum())


@dataclass(frozen=True, eq=False)
class UnitOption:
    unit: int
    hall_side: str
    pieces: tuple[Piece, ...]
    score: float
    parts: dict


def _terminals(specs: list[SpaceSpec], rules: SpaceRules) -> int:
    """Rooms of the unit that open onto circulation (not passable, not hosted by another space of the unit)."""
    ids = {s.space_id for s in specs}
    return sum(1 for s in specs if not s.passable and not (s.host and s.host in ids)
               and s.space_type not in (rules.closet_type,))


def _hall_strip(unit: UnitFrame, side: str, cells: int) -> np.ndarray | None:
    i0, i1, j0, j1 = unit.box
    strip = np.zeros_like(unit.mask)
    if side == "low_x":
        strip[j0:j1, i0:i0 + cells] = True
    elif side == "high_x":
        strip[j0:j1, i1 - cells:i1] = True
    elif side == "low_y":
        strip[j0:j0 + cells, i0:i1] = True
    else:
        strip[j1 - cells:j1, i0:i1] = True
    strip &= unit.mask
    rest = unit.mask & ~strip
    if not strip.any() or not rest.any():
        return None
    return strip


def _arrangements(ids: list[str], max_stack: int, limit: int, axes=(True, False), column_ok=None):
    seen = 0
    for columns in band_arrangements(sorted(ids), max_stack, set(), set(), column_ok=column_ok):
        for along_x in axes:
            yield Guillotine(along_x, columns)
            seen += 1
            if seen >= limit:
                return


# a corridor on one side of the unit (a hall strip, or the circulation unit next to it): the rooms stand in bands
# perpendicular to it, each band a room that opens onto the corridor followed by the spaces that open onto that room
# (its closets, its en-suite bath); bands are ordered along the corridor
CORRIDOR_AXIS = {"low_x": (False, 0), "high_x": (False, -1), "low_y": (True, 0), "high_y": (True, -1)}


def suite_groups(specs: dict[str, SpaceSpec], rules: SpaceRules, matrix) -> list[list[list[str]]]:
    """Ways to group the unit's spaces into rooms that open onto the corridor, each followed by the spaces that open
    onto it (its closets, its en-suite bath; front first). A shared bathroom is its own group or, as a second way,
    joins a bedroom's group (it may open onto a bedroom when no hall reaches it)."""
    es = rules.s21["doors"]["en_suite"]
    to_roles, from_roles = set(es["to_roles"]), set(es["from_roles"])
    parent: dict[str, str] = {}
    for sid, sp in specs.items():
        if sp.host and sp.host in specs and sp.host != sid:
            parent[sid] = sp.host
    beds = sorted((sid for sid, sp in specs.items() if sp.roles & to_roles),
                  key=lambda s: (0 if "primary_bedroom" in specs[s].roles else 1, s))
    shared = []
    for sid, sp in specs.items():
        if sid in parent or not (sp.roles & from_roles):
            continue
        if sp.space_type in es["prefer_circulation"]:
            shared.append(sid)
            continue
        partner = next((b for b in beds if d_pair(matrix, sp, specs[b])), None)
        if partner is not None:
            parent[sid] = partner

    sandwich = {}                              # K10: bath shared by two bedrooms of the unit -> (b1, b2)
    for sid, sp in specs.items():
        if len(sp.between) == 2 and all(b in specs for b in sp.between):
            sandwich[sid] = tuple(sp.between)
            parent[sid] = sp.between[0]
            parent[sp.between[1]] = sp.between[0]

    def build(par: dict[str, str]) -> list[list[str]]:
        def root(sid: str) -> str:
            seen = set()
            while sid in par and sid not in seen:
                seen.add(sid)
                sid = par[sid]
            return sid
        groups: dict[str, list[str]] = {}
        for sid in sorted(specs):
            groups.setdefault(root(sid), [])
        for sid in sorted(specs):
            if sid != root(sid):
                groups[root(sid)].append(sid)
        out = []
        for r, d in sorted(groups.items()):
            bath = next((x for x in d if x in sandwich), None)
            if bath is None:
                through = bool(rules.policy("walk_through_closet"))    # S2.2c: suite -> walk-in -> bath
                out.append([r] + sorted(d, key=lambda x: (specs[x].space_type == rules.closet_type,
                                                          through and specs[x].space_type in BATH_TYPES, x)))
                continue
            b1, b2 = sandwich[bath]
            mine = {b: (b, *sorted(x for x in d if specs[x].host == b)) for b in (b1, b2)}
            out.append(["@shared", mine[b1], bath, mine[b2]])
        return out

    ways = [build(parent)]
    secondary = [b for b in beds if "primary_bedroom" not in specs[b].roles] or beds
    for sid in shared[:1]:
        for b in secondary[:2]:
            ways.append(build({**parent, sid: b}))
    return ways


def _band_forms(group: list[str], end: int) -> list[tuple]:
    """A group's band: front room at the corridor end, then its spaces one behind the other, or side by side."""
    front, deps = group[0], tuple(group[1:])
    forms = [(front,) + deps]
    if len(deps) > 1:
        forms.append((front, deps))
    return [f if end == 0 else tuple(reversed(f)) for f in forms]


def _group_blocks(g: list, end: int) -> list[tuple]:
    if g and g[0] == "@shared":                   # K10: bedroom | shared bath | bedroom, all on the corridor
        b1, bath, b2 = g[1], g[2], g[3]
        c1 = b1 if end == 0 else tuple(reversed(b1))
        c2 = b2 if end == 0 else tuple(reversed(b2))
        return [(c1, (bath,), c2), (c2, (bath,), c1)]
    forms = [(f,) for f in _band_forms(g, end)]
    if len(g) > 1:
        forms.append(tuple((x,) for x in g))
        forms.append(tuple((x,) for x in g[1:]) + ((g[0],),))
    return forms


def _corridor_arrangements(ways: list[list[list[str]]], along_x: bool, end: int, limit: int, seed: int = 0):
    """Bands along the corridor. Each group is one band (its room at the corridor end, its spaces behind it, in a
    line or side by side), or a run of adjacent bands (every space on the corridor, the dependants next to their
    room, opening onto it through the shared wall). All arrangements when they are at most `limit`, else a
    deterministic sample of `limit` of them (seeded), so every grouping, order and band form is represented."""
    blocks = [[_group_blocks(g, end) for g in groups] for groups in ways]
    total = sum(math.factorial(len(groups)) * math.prod(len(b) for b in bl) for groups, bl in zip(ways, blocks))
    if total <= limit:
        for groups, bl in zip(ways, blocks):
            for perm in itertools.permutations(range(len(groups))):
                for picked in itertools.product(*(bl[k] for k in perm)):
                    yield Guillotine(along_x, tuple(col for block in picked for col in block))
        return
    rng = random.Random(seed)
    seen = set()
    for _ in range(limit * 4):
        w = rng.randrange(len(ways))
        perm = list(range(len(ways[w])))
        rng.shuffle(perm)
        picked = tuple(rng.choice(blocks[w][k]) for k in perm)
        cols = tuple(col for block in picked for col in block)
        if cols in seen:
            continue
        seen.add(cols)
        yield Guillotine(along_x, cols)
        if len(seen) >= limit:
            return


def _mid_strip(unit: UnitFrame, runs_along_y: bool, cells: int, c0: int | None = None):
    """A hall strip across the unit (through the middle, or starting at line c0) and the two halves it leaves
    (masks), or None."""
    i0, i1, j0, j1 = unit.box
    strip = np.zeros_like(unit.mask)
    low = np.zeros_like(unit.mask)
    high = np.zeros_like(unit.mask)
    if runs_along_y:
        c0 = round((i0 + i1) / 2 - cells / 2) if c0 is None else c0
        strip[j0:j1, c0:c0 + cells] = True
        low[j0:j1, i0:c0] = True
        high[j0:j1, c0 + cells:i1] = True
    else:
        c0 = round((j0 + j1) / 2 - cells / 2) if c0 is None else c0
        strip[c0:c0 + cells, i0:i1] = True
        low[j0:c0, i0:i1] = True
        high[c0 + cells:j1, i0:i1] = True
    strip &= unit.mask
    low &= unit.mask
    high &= unit.mask
    if not strip.any() or not low.any() or not high.any():
        return None
    return strip, low, high


def _mid_arrangements(ways: list[list[list[str]]], along_x: bool, limit: int, seed: int):
    """Double-loaded corridor: groups split between the two halves, bands facing the strip on each side
    (deterministic sample when there are more than `limit`)."""
    rng = random.Random(seed)
    seen = set()
    for _ in range(limit * 4):
        groups = ways[rng.randrange(len(ways))]
        if len(groups) < 2:
            return
        side = [rng.random() < 0.5 for _ in groups]
        if all(side) or not any(side):
            side[rng.randrange(len(groups))] = not side[0]
        lo = [g for g, sd in zip(groups, side) if not sd]
        hi = [g for g, sd in zip(groups, side) if sd]
        rng.shuffle(lo)
        rng.shuffle(hi)
        a = tuple(col for g in lo for col in rng.choice(_group_blocks(g, -1)))
        b = tuple(col for g in hi for col in rng.choice(_group_blocks(g, 0)))
        if not a or not b or (a, b) in seen:
            continue
        seen.add((a, b))
        yield Guillotine(along_x, a), Guillotine(along_x, b)
        if len(seen) >= limit:
            return


def _closet_spec(rules: SpaceRules, host: SpaceSpec, k: int, sqft: float, role: str = "closet") -> SpaceSpec:
    """A closet the layout adds to `host`; `role` names it in the id (closet, bath_closet, linen)."""
    return SpaceSpec(f"{host.space_id}_{role}{'' if k == 0 else k + 1}", rules.closet_type, host.zone, host.unit_id,
                     sqft, rules.closet_min_sqft, rules.closet_min_side_ft, False, False, False, frozenset(),
                     host.space_id, False, True)


BATH_TYPES = ("bathroom", "primary_bath", "social_bath", "half_bath")
SIDE_NAMES = ("low_x", "high_x", "low_y", "high_y")           # the order of the exterior flags (-x, +x, -y, +y)
ROOF_TYPE, TERRACE_TYPE = "upper_roof", "terrace"              # S2.2d: open air left on the upper floor
OPEN_AIR = (ROOF_TYPE, TERRACE_TYPE)
WALK_IN = "walk_in_closet"


def shape_weighted(rules: SpaceRules, weights: dict[str, float], floor) -> dict[str, float]:
    """Weights with the shape weight raised in the maximum profile (client 2026-10-12: never stretch spaces to
    fill the maximum area)."""
    if getattr(floor, "profile", None) != "maximum" or "shape" not in weights:
        return weights
    return {**weights, "shape": weights["shape"] * float(rules.policy("maximum_shape_factor") or 1.0)}


def _aspect(rect: tuple[int, int, int, int]) -> float:
    w, h = rect[1] - rect[0], rect[3] - rect[2]
    return max(w, h) / max(min(w, h), 1)


def _with_outside(ext, outside: np.ndarray):
    """Exterior flags (-x, +x, -y, +y) with `outside` (box coordinates) added as outside neighbours."""
    lo_x, hi_x, lo_y, hi_y = ext
    nb = [np.zeros_like(outside) for _ in range(4)]
    nb[0][:, 1:] = outside[:, :-1]
    nb[1][:, :-1] = outside[:, 1:]
    nb[2][1:, :] = outside[:-1, :]
    nb[3][:-1, :] = outside[1:, :]
    return (lo_x | nb[0], hi_x | nb[1], lo_y | nb[2], hi_y | nb[3])


def _box_rect(mask: np.ndarray) -> tuple[int, int, int, int] | None:
    """Bounding rectangle (i0, i1, j0, j1) of a mask, in the mask's own coordinates."""
    return mask_bounds(mask)


class UnitLayout:
    """Options of one unit of a floor."""

    def __init__(self, floor: SpaceFloor, unit: UnitFrame, rules: SpaceRules, catalog, matrix):
        self.floor, self.unit, self.rules = floor, unit, rules
        walls = getattr(floor, "below_lines", None)            # S2.2f: room walls over the ground walls
        reach = int(round(float(rules.design.get("structure.snap_max_ft") or 0.0) / floor.res))
        self.snap = None
        if walls is not None and reach > 0:
            xs, ys = box_lines(walls, unit.box, float(rules.design.get("structure.snap_share") or 0.25))
            self.snap = (xs, ys, reach)
        self.catalog, self.matrix = catalog, matrix
        self.res = floor.res
        s = rules.s21
        self.max_stack = int(s["layout"]["max_stack"])
        self.tol = float(s["layout"]["target_tolerance_fraction"])
        self.limit = int(s["search"]["max_arrangements_per_unit"])
        self.keep = int(s["search"]["options_per_unit"])
        self.first_violations: dict[str, int] = {}
        i0, i1, j0, j1 = unit.box
        out = floor.outside
        self.landing = floor.landing[j0:j1, i0:i1]
        d_ = rules.design                                      # S2.2i: bedrooms near the stair, baths on the sides
        upper = floor.level > 0
        self.near_w = float(d_.get("circulation.upper_rooms.bed_near_weight") or 0.0) if upper else 0.0
        self.bath_w = float(d_.get("circulation.upper_rooms.bath_side_weight") or 0.0) if upper else 0.0
        self.near_scale = float(d_.get("circulation.upper_rooms.near_scale_ft") or 1.0)
        self.near_min = float(d_.get("circulation.upper_hall.vestibule_min_ft") or 0.0)
        bath_walls = set(d_.get("circulation.upper_rooms.bath_walls") or ())
        self.bath_sides = [k for k, n in enumerate(SIDE_NAMES) if n in bath_walls]
        self.landing_dist = None
        if self.near_w and floor.landing is not None and floor.landing.any():
            self.landing_dist = distance_transform_edt(~floor.landing)[j0:j1, i0:i1] * self.res
        self.need_cells = float(catalog.data["circulation"]["door_contact_ft"]) / self.res   # as S2 links zones
        self.shared_cells = float(rules.s21["program"]["shared_contact_ft"]) / self.res
        by_id = {u.unit_id: u for u in floor.units}
        linked = [by_id[x] for x in sorted(floor.links.get(unit.unit_id, ())) if x in by_id]
        pad = (slice(j0 - 1, j1 + 1), slice(i0 - 1, i1 + 1))
        self.link_targets = [(u.unit_id, u.mask[pad]) for u in linked]
        circ_fixed = np.isin(floor.base, [k for k, s in enumerate(floor.fixed) if s.circulation and s.space_type != "stair"])
        self.fixed_circ = circ_fixed[pad] if circ_fixed[pad].any() else None
        self.stair_pad = floor.stair[pad] if floor.stair[pad].any() else None
        self.circ_targets = [m for uid, m in self.link_targets if by_id[uid].zone == "circulation"]
        self.room_targets = [m for uid, m in self.link_targets if by_id[uid].zone != "circulation"]
        self.private_targets = [m for uid, m in self.link_targets if by_id[uid].zone == "private"]
        own = {sp.space_type for sp in unit.specs}
        self.hard_d = []                          # (role here, mask of a linked unit holding the partner role)
        for p in matrix.pairs:
            if p.type != "D" or p.kind != "hard":
                continue
            passable = all(t.startswith("@") or (catalog.has_space_type(t) and catalog.space_type(t).get("passable"))
                           for r in (p.a, p.b) for t in matrix.roles.get(r, ()))
            if not passable:
                continue                          # a terminal room meets D through a shared hall
            for mine, other in ((p.a, p.b), (p.b, p.a)):
                theirs = matrix.roles.get(other, frozenset())
                if theirs & own:
                    continue                      # the partner may sit in this unit
                if any(t.startswith("@entry") for t in theirs):
                    self.hard_d.append((mine, None))       # D with the entry: onto the circulation it opens to
                    continue
                for uid, m in self.link_targets:
                    if theirs & {sp.space_type for sp in by_id[uid].specs}:
                        self.hard_d.append((mine, m))
        es = rules.s21["doors"]["en_suite"]
        self.to_roles, self.from_roles = set(es["to_roles"]), set(es["from_roles"])
        if self.fixed_circ is not None:
            self.circ_targets.append(self.fixed_circ)
        self.ext = (out[j0:j1, i0 - 1:i1 - 1], out[j0:j1, i0 + 1:i1 + 1],      # neighbour at -x, +x
                    out[j0 - 1:j1 - 1, i0:i1], out[j0 + 1:j1 + 1, i0:i1])      # neighbour at -y, +y
        self.base_ext = self.ext                                               # S2.2d: roof pieces add outside

    # ---------------------------------------------------------------- helpers

    def _cells(self, ft: float) -> int:
        return max(1, int(np.ceil(ft / self.res - 1e-9)))

    def _fail(self, why: str) -> None:
        self.first_violations[why] = self.first_violations.get(why, 0) + 1

    def _facade_ok(self, spec: SpaceSpec, kept: np.ndarray, sqft: float) -> tuple[bool, float]:
        """`kept` is a mask in unit-box coordinates."""
        need = self.rules.facade_need_ft(spec.space_type, sqft, spec.habitable)
        if need <= 0.0:
            return True, 0.0
        have = exterior_run(kept, self.ext) * self.res
        return have >= need - 1e-9, have - need

    def hall_spec(self) -> SpaceSpec:
        row = {"space_id": f"hall_{self.unit.unit_id.replace(':', '_')}", "space_type": HALL_TYPE,
               "zone": "circulation", "area_sqft": 0.0}
        s = spec_of(self.catalog, self.rules, self.matrix, row, self.unit.unit_id)
        return SpaceSpec(**{**s.__dict__, "synthetic": True})

    # ---------------------------------------------------------------- one realization

    def _pieces(self, area_box: np.ndarray, rects: dict[str, tuple], specs: dict[str, SpaceSpec],
                with_closets: bool = True, avoid: np.ndarray | None = None):
        """Pieces of a realization (masks in unit-box coordinates), closets from leftovers and closets carved on a
        short wall; None and a reason when a hard rule fails."""
        i0, _, j0, _ = self.unit.box
        ca = self.res * self.res
        rules = self.rules
        one_piece = bool(rules.policy("one_piece"))
        one_piece_circ = bool(rules.policy("one_piece_circulation"))
        pieces: list[Piece] = []
        facade_slack = []
        stray: list[tuple[np.ndarray, SpaceSpec]] = []          # parts cut off their space (one space, one piece)
        roofs: list[Piece] = []
        for sid, r in rects.items():                          # S2.2d: open air first (it is outside for the rooms)
            if specs[sid].space_type == ROOF_TYPE:
                got = self._roof_piece(area_box, specs[sid], r)
                if got is None:
                    return None, "roof:inside"
                roofs.append(got)
        if roofs:
            self.ext = _with_outside(self.base_ext, np.logical_or.reduce([p.mask for p in roofs]))
        rects = {sid: r for sid, r in rects.items() if specs[sid].space_type != ROOF_TYPE}
        for sid, (a0, a1, b0, b1) in rects.items():          # cheap bounds first: a clipped rectangle only shrinks
            spec = specs[sid]
            if min(a1 - a0, b1 - b0) * self.res < spec.min_side_ft - 1e-9:
                return None, f"min_side:{spec.space_type}"
            if int(area_box[b0 - j0:b1 - j0, a0 - i0:a1 - i0].sum()) * ca < spec.min_sqft - 1e-6:
                return None, f"min_area:{spec.space_type}"
        for sid, (a0, a1, b0, b1) in rects.items():
            spec = specs[sid]
            crop = area_box[b0 - j0:b1 - j0, a0 - i0:a1 - i0]
            n = int(crop.sum())
            if n == 0:
                return None, "empty"
            closets = []
            kept = np.zeros_like(area_box)
            if n == crop.size:                                   # a full rectangle: the common case
                rect = (a0, a1, b0, b1)
                kept[b0 - j0:b1 - j0, a0 - i0:a1 - i0] = True
            else:
                region = np.zeros_like(area_box)
                region[b0 - j0:b1 - j0, a0 - i0:a1 - i0] = crop
                _, local = largest_rect(region)
                rect = (local[0] + i0, local[1] + i0, local[2] + j0, local[3] + j0)
                kept[local[2]:local[3], local[0]:local[1]] = True
                kept &= region
                loose = []
                for comp in components(region & ~kept):
                    c_cells = int(comp.sum())
                    c_n, c_rect = largest_rect(comp)
                    c_side = min(c_rect[1] - c_rect[0], c_rect[3] - c_rect[2]) * self.res
                    big = c_cells >= rules.keep_fraction * n
                    if (with_closets and big and spec.space_type in rules.closet_hosts and c_n == c_cells
                            and rules.closet_min_sqft <= c_cells * ca <= rules.closet_max_sqft
                            and c_side >= rules.closet_min_side_ft - 1e-9 and _touches(comp, kept)
                            and not (comp & self.landing).any()):
                        closets.append((comp, (c_rect[0] + i0, c_rect[1] + i0, c_rect[2] + j0, c_rect[3] + j0),
                                        "closet"))
                    elif _touches(comp, kept) or not one_piece or (spec.circulation and not one_piece_circ):
                        kept |= comp
                    else:
                        loose.append(comp)
                while loose:                                     # parts reached through other parts
                    joined = [c for c in loose if _touches(c, kept)]
                    if not joined:
                        break
                    for c in joined:
                        kept |= c
                    loose = [c for c in loose if not any(c is x for x in joined)]
                stray += [(c, spec) for c in loose]              # S2.2b: given to a neighbour below
            if min(rect[1] - rect[0], rect[3] - rect[2]) * self.res < spec.min_side_ft - 1e-9:
                return None, f"min_side:{spec.space_type}"
            own_closet = any(o.host == sid and o.space_type in (rules.closet_type, "walk_in_closet")
                             for o in specs.values())
            if with_closets and not closets and not own_closet:   # S2.2b: closet across a short wall
                carved = self._carve(spec, kept, rect, avoid)
                if carved is not None:
                    kept, cmask, crect, role = carved
                    closets.append((cmask, crect, role))
            sqft = int(kept.sum()) * ca
            if sqft < spec.min_sqft - 1e-6:
                return None, f"min_area:{spec.space_type}"
            ok, slack = self._facade_ok(spec, kept, sqft)
            if not ok:
                return None, f"facade:{spec.space_type}"
            why = self._hard_shape(spec, kept)
            if why:
                return None, why
            if spec.habitable or spec.space_type in rules.sleeping_types:
                facade_slack.append(slack)
            piece = Piece(spec, kept, rect)
            pieces.append(piece)
            for k, (comp, c_rect, role) in enumerate(closets):
                pieces.append(Piece(_closet_spec(rules, spec, k if role == "closet" else 0, int(comp.sum()) * ca,
                                                 role), comp, c_rect))
        for comp, spec in stray:                                # S2.2b: a cut-off part joins the neighbour that
            best = None                                          # shares the most wall with it (never a closet)
            for k, q in enumerate(pieces):
                if q.spec.space_id == spec.space_id or q.spec.space_type == rules.closet_type:
                    continue
                t = self._touch_cells(comp, q.mask)
                if t > 0 and (best is None or t > best[0]):
                    best = (t, k)
            if best is None:
                own = next((k for k, q in enumerate(pieces) if q.spec.space_id == spec.space_id), None)
                if spec.circulation and own is not None and self.stair_pad is not None \
                        and self._contact(comp, self.stair_pad) > 0:
                    q = pieces[own]                              # a hall around the stairwell: joined through it
                    pieces[own] = Piece(q.spec, q.mask | comp, q.rect)
                    continue
                return None, f"fragment:{spec.space_type}"
            q = pieces[best[1]]
            pieces[best[1]] = Piece(q.spec, q.mask | comp, q.rect)
        why = self._full_wall(pieces)
        if why:
            return None, why
        if roofs:
            pieces += self._terraces(roofs, pieces)
        return (pieces, facade_slack), None

    # ---------------------------------------------------------------- S2.2d: roof and terrace

    def _roof_spec(self, specs: dict[str, SpaceSpec]) -> SpaceSpec | None:
        """The open-air part of an upper unit when its spaces at their optimal areas leave enough of it."""
        rules = self.rules
        if self.floor.level <= 0 or self.unit.zone == "circulation" or not rules.design.get("space.upper.optimal_enabled"):
            return None
        small = set(rules.policy("typical_area_types") or ())
        cap_f = float(rules.policy("typical_area_cap") or 1.0)
        need = 0.0
        for sp in specs.values():
            t = sp.target_sqft
            w, d = rules.std(sp.space_type, "typical_w_ft"), rules.std(sp.space_type, "typical_d_ft")
            if sp.space_type in small and w and d:
                t = min(t, float(w) * float(d) * cap_f)
            need += t
        free = self.unit.cells * self.res * self.res
        slack = free - need
        if slack < float(rules.design.get("space.upper.min_roof_sqft") or 0.0):
            return None
        return SpaceSpec(f"roof_{self.unit.unit_id.replace(':', '_')}", ROOF_TYPE, "exterior", self.unit.unit_id,
                         slack, 0.0, self.res, False, False, False, frozenset(), None, False, True)

    def _roof_variants(self, roof: SpaceSpec) -> list[tuple[str, np.ndarray, SpaceSpec, None]]:
        """(tag, area left for the rooms, roof spec, None) per unit side on the facade: a strip deep enough to
        hold the slack, along the whole side, entirely on the facade."""
        unit = self.unit
        i0, i1, j0, j1 = unit.box
        out = []
        slack = roof.target_sqft / (self.res * self.res)
        for side in self.rules.s21["layout"]["hall_sides"]:
            length = (j1 - j0) if side in ("low_x", "high_x") else (i1 - i0)
            depth = int(np.ceil(slack / max(length, 1)))
            if depth <= 0:
                continue
            strip = _hall_strip(unit, side, depth)
            if strip is None:
                continue
            box = strip[j0:j1, i0:i1]
            sb = _box_rect(box)
            if sb is None or exterior_run(box, self.base_ext) < max(sb[1] - sb[0], sb[3] - sb[2]) - 1:
                continue                          # the strip must stand on the facade along its whole length
            out.append((f"roof:{side}", unit.mask & ~strip, roof, None))
        return out

    def _roof_piece(self, area_box: np.ndarray, spec: SpaceSpec, rect) -> Piece | None:
        """The roof part of a realization: on the facade along its whole long side (no roof inside the house)."""
        i0, _, j0, _ = self.unit.box
        a0, a1, b0, b1 = rect
        m = np.zeros_like(area_box)
        m[b0 - j0:b1 - j0, a0 - i0:a1 - i0] = area_box[b0 - j0:b1 - j0, a0 - i0:a1 - i0]
        box = _box_rect(m)
        if box is None:
            return None
        long_ = max(box[1] - box[0], box[3] - box[2])
        if exterior_run(m, self.base_ext) < long_ - 1:
            return None
        return Piece(spec, m, rect)

    def _terraces(self, roofs: list[Piece], pieces: list[Piece]) -> list[Piece]:
        """Roof pieces, each split into a terrace (at most the registry depth, along the whole wall of the room it
        serves) and the rest as roof, when a room that may open onto a terrace borders it."""
        rules = self.rules
        out: list[Piece] = []
        allowed = set(rules.design.get("space.upper.terrace_from") or ())
        depth = self._cells(float(rules.design.get("space.upper.terrace_max_depth_ft") or 0.0))
        for r in roofs:
            room = None
            if rules.design.get("space.upper.terrace_enabled"):
                cands = [(shared_edge(r.mask, q.mask), q) for q in pieces if q.spec.space_type in allowed]
                cands = [c for c in cands if c[0][0] > 0]
                if cands:
                    room = max(cands, key=lambda c: c[0][0])
            if room is None:
                out.append(r)
                continue
            (_, along_y), q = room
            box = _box_rect(r.mask)
            terrace = np.zeros_like(r.mask)
            if along_y:                            # common wall on a vertical line: the terrace is a band in x
                left = (q.mask[:, :-1] & r.mask[:, 1:]).any()          # the room is on the low-x side
                x0, x1 = (box[0], min(box[0] + depth, box[1])) if left else (max(box[1] - depth, box[0]), box[1])
                terrace[:, x0:x1] = r.mask[:, x0:x1]
            else:
                below = (q.mask[:-1, :] & r.mask[1:, :]).any()
                y0, y1 = (box[2], min(box[2] + depth, box[3])) if below else (max(box[3] - depth, box[2]), box[3])
                terrace[y0:y1, :] = r.mask[y0:y1, :]
            rest = r.mask & ~terrace
            tspec = SpaceSpec(r.spec.space_id.replace("roof_", "terrace_"), TERRACE_TYPE, "exterior", r.spec.unit_id,
                              float(terrace.sum()) * self.res * self.res, 0.0, 0.0, False, False, False, frozenset(),
                              q.spec.space_id, False, True)
            out.append(Piece(tspec, terrace, r.rect))
            if rest.any():
                out.append(Piece(r.spec, rest, r.rect))
        return out

    # ---------------------------------------------------------------- S2.2b: carving, hard shape, whole wall

    def _carve(self, spec: SpaceSpec, kept: np.ndarray, rect: tuple[int, int, int, int],
               avoid: np.ndarray | None = None):
        """(room, closet, closet rect, role) when a long room or bath gets a closet across a whole short wall: a strip
        of the closet depth at the short end that faces neither the facade nor the circulation, when the room keeps
        its least side and its area; None otherwise."""
        rules = self.rules
        t = spec.space_type
        if t in BATH_TYPES and rules.closets("bath_closet_enabled"):
            depth_ft, role = rules.closets("bath_closet_depth_ft"), "bath_closet"
        elif t in (rules.closets("reach_in_types") or ()) and rules.closets("reach_in_enabled"):
            depth_ft, role = rules.closets("reach_in_depth_ft"), "closet"
        else:
            return None
        pref = rules.std(t, "aspect_pref_max")
        box = _box_rect(kept)
        if pref is None or box is None or int(kept.sum()) != (box[1] - box[0]) * (box[3] - box[2]):
            return None                                   # only full rectangles
        if _aspect(box) <= float(pref) + 1e-9:
            return None
        d = self._cells(float(depth_ft))
        w, h = box[1] - box[0], box[3] - box[2]
        if role == "bath_closet":                         # the closet takes the length beyond the preferred ratio
            short, long_ = min(w, h), max(w, h)
            d = max(d, long_ - int(np.floor(float(pref) * short + 1e-9)))
            d = min(d, int(np.floor(self.rules.closet_max_sqft / (short * self.res * self.res))))
            if d <= 0:
                return None
        ends = []
        if w >= h:
            ends = [(box[0], box[0] + d, box[2], box[3]), (box[1] - d, box[1], box[2], box[3])]
        else:
            ends = [(box[0], box[1], box[2], box[2] + d), (box[0], box[1], box[3] - d, box[3])]
        best = None
        for e in ends:
            strip = np.zeros_like(kept)
            strip[e[2]:e[3], e[0]:e[1]] = True
            if (strip & self.landing).any():
                continue
            rest = kept & ~strip
            r_box = _box_rect(rest)
            if r_box is None or min(r_box[1] - r_box[0], r_box[3] - r_box[2]) * self.res < spec.min_side_ft - 1e-9:
                continue
            area = int(strip.sum()) * self.res * self.res
            if not (rules.closet_min_sqft - 1e-9 <= area <= rules.closet_max_sqft + 1e-9):
                continue
            door_side = sum(self._contact(strip, m) for m in self.circ_targets) + (
                self._touch_cells(strip, avoid) if avoid is not None else 0)
            cost = exterior_cells(strip, self.ext) + 10 * door_side      # keep the window wall and the door side
            if best is None or cost < best[0]:
                best = (cost, rest, strip, e)
        if best is None:
            return None
        _, rest, strip, e = best
        i0, _, j0, _ = self.unit.box
        return rest, strip, (e[0] + i0, e[1] + i0, e[2] + j0, e[3] + j0), role

    def _hard_shape(self, spec: SpaceSpec, kept: np.ndarray) -> str | None:
        """Hard proportion and furniture of the types the profile marks hard (client: baths, dining room, kitchen;
        bed clearance in bedrooms)."""
        rules = self.rules
        t = spec.space_type
        box = _box_rect(kept)
        if box is None:
            return f"empty:{t}"
        amax = rules.std(t, "aspect_max")
        if amax is not None and rules.hard(t, "aspect_max") and _aspect(box) > float(amax) + 1e-9:
            return f"aspect:{t}"
        if rules.furniture_hard(t):
            options = rules.furniture_ft(t)
            if options and not any(fits_in_mask(kept, self._cells(w), self._cells(d)) for w, d in options):
                return f"furniture:{t}"
        return None

    def _full_wall(self, pieces: list[Piece]) -> str | None:
        """A space of a whole-wall type covers the whole wall it shares with its host (or its main neighbour):
        the common wall is as long as the space's side and the host's side along it (client 2026-10-11)."""
        rules = self.rules
        types = set(rules.policy("full_wall_types") or ())
        if not types or rules.design_kinds.get("space.policy.full_wall_types") != "hard":
            return None
        bad = self._wall_misses(pieces)
        return f"full_wall:{bad[0]}" if bad else None

    def _wall_misses(self, pieces: list[Piece]) -> list[str]:
        """Types of the whole-wall pieces that do not cover the whole wall of their room (empty: all do)."""
        rules = self.rules
        types = set(rules.policy("full_wall_types") or ())
        misses: list[str] = []
        if not types:
            return misses
        tol = float(rules.policy("full_wall_tolerance_ft") or 0.0) / self.res + 1e-9
        for p in pieces:
            if p.spec.space_type not in types:
                continue
            host = next((q for q in pieces if q.spec.space_id == p.spec.host), None) if p.spec.host else None
            if host is None:
                cands = [(shared_edge(p.mask, q.mask)[0], q) for q in pieces
                         if q is not p and q.spec.space_type not in types]
                cands = [c for c in cands if c[0] > 0]
                if not cands:
                    continue                              # its wall is on another unit: checked there
                host = max(cands, key=lambda c: c[0])[1]
            shared, along_y = shared_edge(p.mask, host.mask)
            if shared == 0:
                misses.append(p.spec.space_type)
                continue
            pb, hb = _box_rect(p.mask), _box_rect(host.mask)
            p_len = (pb[3] - pb[2]) if along_y else (pb[1] - pb[0])
            h_len = (hb[3] - hb[2]) if along_y else (hb[1] - hb[0])
            if shared < p_len - tol or shared < h_len - tol:
                misses.append(p.spec.space_type)
        return misses

    def _linen(self, pieces: list[Piece]) -> list[Piece] | None:
        """Pieces with a linen closet across the whole width of the upper hall, at its quieter end; None when the
        hall is not a plain rectangle or the closet does not fit (S2.2b, client 2026-10-11)."""
        rules = self.rules
        if self.floor.level <= 0 or not rules.closets("linen_enabled"):
            return None
        halls = [p for p in pieces if p.spec.space_type == HALL_TYPE]
        if len(halls) != 1:
            return None
        h = halls[0]
        box = _box_rect(h.mask)
        if box is None or int(h.mask.sum()) != (box[1] - box[0]) * (box[3] - box[2]):
            return None
        d = self._cells(float(rules.closets("linen_depth_ft")))
        w, ht = box[1] - box[0], box[3] - box[2]
        ends = ([(box[0], box[0] + d, box[2], box[3]), (box[1] - d, box[1], box[2], box[3])] if w >= ht
                else [(box[0], box[1], box[2], box[2] + d), (box[0], box[1], box[3] - d, box[3])])
        others = [q.mask for q in pieces if q is not h]
        best = None
        for e in ends:
            strip = np.zeros_like(h.mask)
            strip[e[2]:e[3], e[0]:e[1]] = True
            if (strip & self.landing).any():
                continue
            rest = h.mask & ~strip
            area = int(strip.sum()) * self.res * self.res
            if int(rest.sum()) * self.res * self.res < h.spec.min_sqft - 1e-6:
                continue
            if not (rules.closet_min_sqft - 1e-9 <= area <= rules.closet_max_sqft + 1e-9):
                continue
            cost = (sum(self._touch_cells(strip, m) for m in others)
                    + sum(self._contact(strip, m) for m in self.circ_targets + self.room_targets))
            if best is None or cost < best[0]:
                best = (cost, rest, strip, e)
        if best is None:
            return None
        _, rest, strip, e = best
        i0, _, j0, _ = self.unit.box
        r = _box_rect(rest)
        hall = Piece(h.spec, rest, (r[0] + i0, r[1] + i0, r[2] + j0, r[3] + j0))
        closet = Piece(_closet_spec(rules, h.spec, 0, int(strip.sum()) * self.res * self.res, "linen"), strip,
                       (e[0] + i0, e[1] + i0, e[2] + j0, e[3] + j0))
        return [hall if q is h else q for q in pieces] + [closet]

    # ---------------------------------------------------------------- score (S2.2b)

    def _shape_of(self, p: Piece) -> float | None:
        rules = self.rules
        t = p.spec.space_type
        box = _box_rect(p.mask)
        if box is None:
            return None
        long_ft = max(box[1] - box[0], box[3] - box[2]) * self.res
        if p.spec.circulation:
            rect_fill = p.cells / max((box[1] - box[0]) * (box[3] - box[2]), 1)
            limit = rules.design.get("circulation.hall.max_length_ft")
            length = 1.0 if not limit or long_ft <= limit else float(limit) / long_ft
            return rect_fill * length
        pref, amax = rules.std(t, "aspect_pref_max"), rules.std(t, "aspect_max")
        if pref is None or amax is None:
            return None                                    # exempt (closets, laundry closet)
        a = _aspect(box)
        pref, amax = float(pref), float(amax)
        if a <= pref + 1e-9:
            s = 1.0
        elif a <= amax + 1e-9:
            s = 1.0 - 0.5 * (a - pref) / max(amax - pref, 1e-9)
        else:
            s = max(0.0, 0.5 - 0.5 * (a - amax))
        side = rules.std(t, "max_side_ft")
        if side and long_ft > float(side):
            s *= max(0.0, 1.0 - (long_ft - float(side)) / float(side))
        return s

    def _score(self, pieces: list[Piece], targets: dict[str, float], facade_slack: list[float]) -> dict:
        rules = self.rules
        level = self.floor.level
        shapes, fits, furn = [], [], []
        circ_parts = []
        n_daylit, n_total, n_cross = 0, 0, 0
        m_ext, all_ext = 0, 0
        head = float(rules.light("daylight.window_head_ft") or 0.0)
        factor = float(rules.light("daylight.depth_factor") or 0.0)
        for p in pieces:
            t = p.spec.space_type
            if t in OPEN_AIR:
                continue
            s = self._shape_of(p)
            if s is not None:
                (circ_parts if p.spec.circulation else shapes).append(s)
            if p.spec.space_id in targets and targets[p.spec.space_id] > 0:
                dev = abs(p.cells - targets[p.spec.space_id]) / targets[p.spec.space_id]
                fits.append(max(0.0, 1.0 - dev / self.tol) if self.tol else 1.0)
            if not p.spec.synthetic:
                options = rules.furniture_ft(t)
                if options:
                    furn.append(1.0 if any(fits_in_mask(p.mask, self._cells(w), self._cells(d)) for w, d in options)
                                else 0.0)
            ext = exterior_cells(p.mask, self.ext)
            all_ext += ext
            cat = rules.category(t, level)
            if cat == "M":
                m_ext += ext
            elif cat == "N":
                n_total += 1
                run = exterior_run(p.mask, self.ext) * self.res
                if run > 0 and head and factor and p.cells * self.res * self.res / run <= head * factor + 1e-9:
                    n_daylit += 1
                if exposed_sides(p.mask, self.ext) >= 2:
                    n_cross += 1
        wall_types = set(rules.policy("full_wall_types") or ())
        n_wall = sum(1 for p in pieces if p.spec.space_type in wall_types)
        if n_wall:                                         # S2.2b: whole-wall rule scored with the furniture term
            misses = len(self._wall_misses(pieces))
            furn += [1.0] * max(0, n_wall - misses) + [0.0] * min(misses, n_wall)
        w_worst = float(rules.policy("worst_weight") or 0.0)
        shape = (1.0 - w_worst) * float(np.mean(shapes)) + w_worst * float(min(shapes)) if shapes else 1.0
        full = float(rules.s21["facade"]["surplus_full_ft"])
        exterior = float(np.mean([min(1.0, max(0.0, s) / full) for s in facade_slack])) if facade_slack else 1.0
        daylit = n_daylit / n_total if n_total else 1.0
        m_share = m_ext / all_ext if all_ext else 0.0
        cross = float(rules.light("ventilation.cross_bonus_weight") or 0.0) * (n_cross / n_total if n_total else 0.0)
        light = min(1.0, 0.5 * daylit + 0.25 * exterior + 0.25 * (1.0 - m_share) + cross)
        parts = {"shape": shape, "furniture": float(np.mean(furn)) if furn else 1.0,
                 "fit": float(np.mean(fits)) if fits else 1.0,
                 "circulation": float(np.mean(circ_parts)) if circ_parts else 1.0,
                 "light": light, "exterior": exterior, "daylit": daylit, "m_facade_share": m_share}
        w = shape_weighted(rules, rules.s21["layout"]["local_weights"], self.floor)
        parts["total"] = sum(w[k] * parts[k] for k in w) / (sum(w.values()) or 1.0)
        self._upper_parts(pieces, parts)
        return parts

    def _upper_parts(self, pieces: list[Piece], parts: dict) -> None:
        """S2.2i (upper floor): bedrooms as near the stair landing as possible, baths against the preferred walls;
        both blended into the total with their registry weights."""
        extra, weight = 0.0, 0.0
        if self.landing_dist is not None:
            beds = [p for p in pieces if p.spec.space_type in self.rules.sleeping_types and p.mask.any()]
            if beds:
                near = float(np.mean([1.0 / (1.0 + max(0.0, float(self.landing_dist[p.mask].min()) - self.near_min)
                                             / self.near_scale) for p in beds]))
                parts["bed_near"] = near
                extra, weight = extra + self.near_w * near, weight + self.near_w
        if self.bath_w and self.bath_sides:
            baths = [p for p in pieces if p.spec.space_type in BATH_TYPES and not p.spec.fixed and p.mask.any()]
            if baths:
                side = float(np.mean([1.0 if any((p.mask & self.ext[k]).any() for k in self.bath_sides)
                                      else 0.5 if exterior_cells(p.mask, self.ext) else 0.0 for p in baths]))
                parts["bath_side"] = side
                extra, weight = extra + self.bath_w * side, weight + self.bath_w
        if weight:
            parts["total"] = (1.0 - weight) * parts["total"] + extra

    def _contact(self, box_mask: np.ndarray, target_pad: np.ndarray) -> int:
        m = np.zeros(target_pad.shape, dtype=bool)
        m[1:-1, 1:-1] = box_mask
        t = target_pad
        return int((m[:, 1:] & t[:, :-1]).sum() + (m[:, :-1] & t[:, 1:]).sum()
                   + (m[1:, :] & t[:-1, :]).sum() + (m[:-1, :] & t[1:, :]).sum())

    def _corridor_ok(self, pieces: list[Piece]) -> bool:
        """The circulation space of a circulation unit touches every linked unit (and the fixed vestibules it
        borders); a hall strip touches a circulation unit or vestibule."""
        if self.unit.zone == "circulation":
            circ = [p for p in pieces if p.spec.circulation]
            if not circ:
                return False
            mask = np.zeros_like(circ[0].mask)
            for p in circ:
                mask |= p.mask
            targets = [m for _, m in self.link_targets]
            i0, i1, j0, j1 = self.unit.box
            if self.fixed_circ is not None and self._contact(self.unit.mask[j0:j1, i0:i1], self.fixed_circ) > 0:
                targets.append(self.fixed_circ)
            return all(self._contact(mask, t) >= self.need_cells - 1e-9 for t in targets)
        halls = [p for p in pieces if p.spec.circulation]
        if not halls or not self.circ_targets:
            return True
        need = self.need_cells
        if self.floor.level > 0 and self.rules.design.get("circulation.arrival.single_hall"):
            width = self.rules.hall_width_accessible_ft if self.floor.accessible else self.rules.hall_width_ft
            need = max(need, self._cells(width))         # S2.2f: one continuous hall, met over its whole width
        return all(any(self._contact(h.mask, t) >= need - 1e-9 for t in self.circ_targets) for h in halls)

    @staticmethod
    def _touch_cells(a: np.ndarray, b: np.ndarray) -> int:
        return int((a[:, 1:] & b[:, :-1]).sum() + (a[:, :-1] & b[:, 1:]).sum()
                   + (a[1:, :] & b[:-1, :]).sum() + (a[:-1, :] & b[1:, :]).sum())

    def _reach_ok(self, pieces: list[Piece]) -> bool:
        """Every room of the option can get a door: onto circulation (a hall of the option, a circulation unit or a
        vestibule), onto its host or en-suite bedroom, or (rooms that are not private) onto a passable space of the
        option or a linked room unit."""
        need = self.need_cells - 1e-9
        rules = self.rules
        for p in pieces:
            sp = p.spec
            if sp.circulation or sp.space_type in OPEN_AIR:
                continue
            if sp.passable:                       # a passable room joins the corridor or a linked unit
                if not (any(self._contact(p.mask, t) >= need for t in self.circ_targets + self.room_targets)
                        or any(self._touch_cells(p.mask, q.mask) >= need for q in pieces
                               if q is not p and (q.spec.passable or q.spec.circulation))):
                    return False
                continue
            private = bool(sp.roles & rules.private_roles)
            ok = any(self._contact(p.mask, t) >= need for t in self.circ_targets)
            for q in pieces:
                if ok:
                    break
                if q is p:
                    continue
                t = self._touch_cells(p.mask, q.mask)
                if t < need:
                    continue
                qs = q.spec
                ok = (qs.circulation or (sp.host and sp.host == qs.space_id) or (qs.host == sp.space_id and False)
                      or (self.rules.policy("walk_through_closet") and sp.space_type in BATH_TYPES and sp.host
                          and qs.space_type == WALK_IN and qs.host == sp.host)            # S2.2c: through the walk-in
                      or (sp.roles & self.from_roles and qs.roles & self.to_roles)
                      or (not private and qs.passable))
            if not ok and not private:
                ok = any(self._contact(p.mask, t) >= need for t in self.room_targets)
            if not ok and private:                # a hall strip of a neighbouring private unit may reach it
                ok = any(self._contact(p.mask, t) >= need for t in self.private_targets)
            if ok and sp.between:                 # K10: between its two bedrooms
                for b in sp.between:
                    q = next((x for x in pieces if x.spec.space_id == b), None)
                    if q is not None and self._touch_cells(p.mask, q.mask) < self.shared_cells:
                        return False
            if not ok:
                return False
        return True

    def _hard_pairs_ok(self, pieces: list[Piece]) -> bool:
        """A room with a hard D partner in a linked unit touches that unit (the partner may then share a wall or a
        door); a room in a hard D pair with the entry touches the circulation."""
        need = self.need_cells - 1e-9
        for role, target in self.hard_d:
            holders = [p for p in pieces if role in p.spec.roles]
            if not holders:
                continue
            targets = self.circ_targets if target is None else [target]
            if not targets:
                continue
            if not any(self._contact(p.mask, t) >= need for p in holders for t in targets):
                return False
        return True

    def _edge_contact(self, side: str) -> int:
        """Cells of the unit whose neighbour across `side` belongs to a circulation unit or vestibule."""
        if not self.circ_targets:
            return 0
        i0, i1, j0, j1 = self.unit.box
        m = self.unit.mask[j0:j1, i0:i1]
        best = 0
        for t in self.circ_targets:
            inner = t[1:-1, 1:-1]
            nb = {"low_x": t[1:-1, :-2], "high_x": t[1:-1, 2:], "low_y": t[:-2, 1:-1], "high_y": t[2:, 1:-1]}[side]
            best = max(best, int((m & nb & ~inner).sum()))
        return best

    def _edge_span(self, side: str) -> tuple[int, int] | None:
        """Cells along `side` (whole-floor index along the side) where the unit meets a circulation unit or a
        vestibule: (first, last + 1), or None."""
        if not self.circ_targets:
            return None
        i0, i1, j0, j1 = self.unit.box
        m = self.unit.mask[j0:j1, i0:i1]
        hit = np.zeros_like(m)
        for t in self.circ_targets:
            nb = {"low_x": t[1:-1, :-2], "high_x": t[1:-1, 2:], "low_y": t[:-2, 1:-1], "high_y": t[2:, 1:-1]}[side]
            hit |= m & nb
        if not hit.any():
            return None
        if side in ("low_x", "high_x"):
            rows = np.nonzero(hit.any(1))[0]
            return int(rows[0]) + j0, int(rows[-1]) + 1 + j0
        cols = np.nonzero(hit.any(0))[0]
        return int(cols[0]) + i0, int(cols[-1]) + 1 + i0

    def _cap_small(self, targets: dict[str, float], specs: dict[str, SpaceSpec]) -> dict[str, float]:
        """Small spaces at most their typical size (typical width x depth x cap); what they give up goes to the
        habitable rooms of the unit (or the other spaces), in proportion (S2.2b)."""
        rules = self.rules
        if not rules.policy("small_types_to_typical"):
            return targets
        small = set(rules.policy("typical_area_types") or ())
        cap_f = float(rules.policy("typical_area_cap") or 1.0)
        ca = self.res * self.res
        out = dict(targets)
        excess = 0.0
        for k, v in targets.items():
            t = specs[k].space_type
            w, d = rules.std(t, "typical_w_ft"), rules.std(t, "typical_d_ft")
            if t in small and w and d:
                cap = float(w) * float(d) * cap_f / ca
                if v > cap:
                    excess += v - cap
                    out[k] = cap
        if excess <= 0:
            return targets
        takers = [k for k in out if specs[k].habitable] or [k for k in out if specs[k].space_type not in small]
        if not takers:
            return targets
        base = sum(out[k] for k in takers) or 1.0
        for k in takers:
            out[k] += excess * out[k] / base
        return out

    def _cap_area(self, targets: dict[str, float], specs: dict[str, SpaceSpec]) -> dict[str, float]:
        """S2.2e: no space above its effective maximum (program adjustment) plus the drawn-plan wall allowance; what
        a capped space gives up goes to the uncapped spaces of the unit (habitable rooms first), in proportion,
        repeated until nothing more is capped. When every space is at its cap the rest stays spread in proportion
        (the floor is larger than the program; the quality indicators report it)."""
        ca = self.res * self.res
        caps = {k: drawn_cap(self.rules.design, specs[k].cap_sqft) / ca for k in targets
                if specs[k].cap_sqft is not None}
        if not caps:
            return targets
        out = dict(targets)
        fixed: set[str] = set()
        for _ in range(len(out)):
            excess = 0.0
            for k, cap in caps.items():
                if k not in fixed and out[k] > cap + 1e-9:
                    excess += out[k] - cap
                    out[k] = cap
                    fixed.add(k)
            if excess <= 0:
                break
            free = [k for k in out if k not in fixed]
            takers = [k for k in free if specs[k].habitable] or free
            if not takers:                                  # all capped: keep the excess in proportion
                base = sum(out.values()) or 1.0
                return {k: v + excess * v / base for k, v in out.items()}
            base = sum(out[k] for k in takers) or 1.0
            for k in takers:
                out[k] += excess * out[k] / base
        return out

    def _pad(self):
        i0, i1, j0, j1 = self.unit.box
        return slice(j0 - 1, j1 + 1), slice(i0 - 1, i1 + 1)

    # ---------------------------------------------------------------- options

    def options(self) -> list[UnitOption]:
        """Options with every space of the unit and, when the unit has closets its rooms may hold, with those
        closets built into their rooms (layout.mergeable_into_host); best of each hall side first."""
        base = {s.space_id: s for s in self.unit.specs}
        found = self._options(base, ())
        roof = self._roof_spec(base)
        if roof is not None:                      # S2.2d: rooms at their optimal areas, the rest roof or terrace
            found += self._options(base, (), roof)
        merge = set(self.rules.s21["layout"]["mergeable_into_host"])
        merged = [k for k, sp in base.items() if sp.space_type in merge and sp.host in base]
        if merged:
            specs = {k: sp for k, sp in base.items() if k not in merged}
            for k in merged:
                host = specs[base[k].host]
                cap = host.cap_sqft + base[k].target_sqft if host.cap_sqft is not None else None
                specs[host.space_id] = SpaceSpec(**{**host.__dict__, "cap_sqft": cap,
                                                    "target_sqft": host.target_sqft + base[k].target_sqft})
            found += self._options(specs, tuple(sorted(merged)))
        found.sort(key=lambda o: (-o.score, o.hall_side))
        out, sides = [], {}
        for o in found:                          # keep the best of each hall side, then fill by score
            if o.hall_side not in sides:
                sides[o.hall_side] = o
        out = list(sides.values())
        for o in found:
            if len(out) >= self.keep:
                break
            if all(o is not x for x in out):
                out.append(o)
        out.sort(key=lambda o: (-o.score, o.hall_side))
        return out[: max(self.keep, len(sides))]

    def _options(self, specs: dict[str, SpaceSpec], merged: tuple[str, ...],
                 roof: SpaceSpec | None = None) -> list[UnitOption]:
        unit = self.unit
        if not specs:
            return [UnitOption(unit.index, NO_HALL, (), 1.0, {"total": 1.0})]
        width = self.rules.hall_width_accessible_ft if self.floor.accessible else self.rules.hall_width_ft
        variants: list[tuple[str, np.ndarray, SpaceSpec | None, str | None]] = [(NO_HALL, unit.mask, None, None)]
        if roof is not None:                      # S2.2d: a strip of the slack along one facade side of the unit
            variants = self._roof_variants(roof)
            if not variants:
                return []
        if roof is None and unit.zone != "circulation":
            for side in self.rules.s21["layout"]["hall_sides"]:          # the circulation unit already on a side
                if self._edge_contact(side) >= self.need_cells - 1e-9:
                    variants.append((f"edge:{side}", unit.mask, None, side))
        if roof is None and unit.zone != "circulation" and \
                _terminals(unit.specs, self.rules) >= self.rules.hall_min_terminals:
            width = self.rules.hall_width_accessible_ft if self.floor.accessible else self.rules.hall_width_ft
            hspec = self.hall_spec()
            for side in self.rules.s21["layout"]["hall_sides"]:
                strip = _hall_strip(unit, side, self._cells(width))
                if strip is not None:
                    variants.append((side, unit.mask & ~strip, hspec, side))
        mids = []
        if roof is None and unit.zone != "circulation" and \
                _terminals(unit.specs, self.rules) >= self.rules.hall_min_terminals:
            cells_w = self._cells(width)
            for runs_along_y in (True, False):
                starts = [None]                    # through the middle, and wherever it meets the circulation
                ends = ("low_y", "high_y") if runs_along_y else ("low_x", "high_x")
                for side in ends:
                    span = self._edge_span(side)
                    if span is not None:
                        a, b = span
                        starts += [a, max(a, b - cells_w), (a + b - cells_w) // 2]
                for c0 in dict.fromkeys(starts):
                    got = _mid_strip(unit, runs_along_y, cells_w, c0)
                    if got is not None:
                        tag = ("mid_x" if runs_along_y else "mid_y") + ("" if c0 is None else f"@{c0}")
                        mids.append((tag, got, runs_along_y))
        found: list[UnitOption] = []
        seen = set()
        groups = suite_groups(specs, self.rules, self.matrix)
        min_cells = {k: self._cells(s.min_side_ft) for k, s in specs.items()}
        i0, i1, j0, j1 = unit.box

        def scaled(ids, free):
            total = sum(specs[k].target_sqft for k in ids) or 1.0
            return self._cap_area(self._cap_small({k: specs[k].target_sqft / total * free for k in ids}, specs), specs)

        jobs = []                                 # (side, area mask, hall spec, iterator of [(g, mask, targets)])
        for side, area_mask, hspec, toward in variants:
            targets = scaled(list(specs), int(area_mask.sum()))
            ids = list(specs)
            if len(ids) == 1:
                it = iter([Guillotine(True, (tuple(ids),))])
            elif toward is not None:
                along_x, end = CORRIDOR_AXIS[toward]
                it = _corridor_arrangements(groups, along_x, end, self.limit,
                                            zlib.crc32(f"{unit.unit_id}:{side}".encode()))
            else:
                it = _arrangements(ids, self.max_stack, self.limit)
            jobs.append((side, area_mask, hspec, ((g, area_mask, targets) for g in it), targets))
        for side, (strip, low, high), runs_along_y in mids:
            area_mask = low | high
            along_x = not runs_along_y
            pairs = _mid_arrangements(groups, along_x, self.limit, zlib.crc32(f"{unit.unit_id}:{side}".encode()))

            def halves(pairs=pairs, low=low, high=high):
                for ga, gb in pairs:
                    ia = [n for col in ga.columns for part in col for n in (part if isinstance(part, tuple) else (part,))]
                    ib = [n for col in gb.columns for part in col for n in (part if isinstance(part, tuple) else (part,))]
                    yield [(ga, low, scaled(ia, int(low.sum()))), (gb, high, scaled(ib, int(high.sum())))]
            jobs.append((side, area_mask, self.hall_spec(), halves(), scaled(list(specs), int(area_mask.sum()))))
        for side, area_mask, hspec, it, targets in jobs:
            hall_piece = None
            if hspec is not None:
                strip = unit.mask & ~area_mask
                if self.rules.policy("one_piece_circulation") and len(components(strip[j0:j1, i0:i1])) > 1:
                    self._fail("fragment:hall")                 # S2.2b: the hall is one piece
                    continue
                _, rect = largest_rect(strip)
                hall_piece = Piece(hspec, strip[j0:j1, i0:i1], rect)
            area_box = area_mask[j0:j1, i0:i1]
            for job in it:
                parts_list = job if isinstance(job, list) else [job]
                rects = {}
                for g, mask, tg in parts_list:
                    r = realize(mask, unit.box if len(parts_list) == 1 else mask_bounds(mask), g, tg, min_cells,
                                self.snap)
                    if r is None:
                        rects = None
                        break
                    rects.update(r)
                if rects is None:
                    self._fail("cuts")
                    continue
                key = (side, tuple(sorted(rects.items())))
                if key in seen:
                    continue
                seen.add(key)
                is_roof = hall_piece is not None and hall_piece.spec.space_type == ROOF_TYPE
                for with_closets in (True, False):
                    self.ext = _with_outside(self.base_ext, hall_piece.mask) if is_roof else self.base_ext
                    got, why = self._pieces(area_box, rects, specs, with_closets,
                                            hall_piece.mask if hall_piece is not None else None)
                    if got is None:
                        self._fail(why)
                        break
                    pieces, slack = got
                    has_closet = any(p.spec.synthetic and p.spec.space_type == self.rules.closet_type for p in pieces)
                    if is_roof:
                        pieces = pieces + self._terraces([hall_piece], pieces)
                    elif hall_piece is not None:
                        pieces = pieces + [hall_piece]
                    variants = [pieces]
                    linen = self._linen(pieces) if with_closets else None
                    if linen is not None:                       # S2.2b: linen closet across the upper hall
                        variants.insert(0, linen)
                        has_closet = True
                    for cand in variants:
                        if not self._corridor_ok(cand):
                            self._fail("corridor")
                        elif not self._reach_ok(cand):
                            self._fail("reach")
                        elif not self._hard_pairs_ok(cand):
                            self._fail("hard_pair")
                        else:
                            parts = self._score(cand, targets, slack)
                            parts["closets_in_rooms"] = list(merged)
                            found.append(UnitOption(unit.index, side, tuple(cand), parts["total"], parts))
                    if not has_closet:
                        break
        return found


def _rect_mask(shape, rect) -> np.ndarray:
    out = np.zeros(shape, dtype=bool)
    if rect is not None:
        i0, i1, j0, j1 = rect
        out[j0:j1, i0:i1] = True
    return out


def _touches(a: np.ndarray, b: np.ndarray) -> bool:
    return bool((a[:, 1:] & b[:, :-1]).any() or (a[:, :-1] & b[:, 1:]).any()
                or (a[1:, :] & b[:-1, :]).any() or (a[:-1, :] & b[1:, :]).any())


__all__ = ["HALL_TYPE", "NO_HALL", "Piece", "UnitLayout", "UnitOption"]
