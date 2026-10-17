"""Garage -> kitchen without crossing the living or dining room (step V6.8 k2, client 2026-10-17, mandatory).

    S2     the garage stands against a unit of `circulation.garage_route.zone_opens_to` (service or kitchen) and, on
           the ground floor, the service unit against the kitchen unit (`service_kitchen_adjacent`), both hard;
           with `service_with_kitchen` the service zone joins the kitchen unit outright, so the mudroom, laundry and
           kitchen are arranged together; hard D pairs of passable rooms (dining - kitchen) need a link of their
           zones (a shared foyer does not give them their opening in S2.1);
    S2.1   the garage-to-house door opens to a space of `door_to_types` (mudroom, kitchen, laundry, service hall; the
           foyer only when the route crosses nothing social); the doors place it where the cheapest route to the
           kitchen crosses no space of `avoid_space_types`, adding the cased openings that route needs between
           passable spaces; the door graph must then hold such a route (`required`, hard). Its length along the door
           centres is scored (`length_ref_ft`, `length_scale_ft`, `length_weight`) and reported.

Every value comes from the design registry (data/rules/design_circulation_doors.json, P16); no numbers live here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from spaceplan.modules.stacking.lib_aux.route_graph import dijkstra, distance

PREFIX = "circulation.garage_route."
GARAGE_ZONE, GARAGE_PREFIX = "garage", "garage"
SERVICE_ZONE, KITCHEN_ZONE = "service", "kitchen"
STAIR_TYPE, VESTIBULE_TYPE = "stair", "vestibule"     # the stair goes upstairs; the half bath's vestibule is its own


@dataclass(frozen=True)
class RouteSettings:
    required: bool = False                       # hard: a door route garage -> kitchen off the social rooms
    avoid: frozenset[str] = frozenset()          # space types the route never crosses
    targets: frozenset[str] = frozenset()        # the route's end (kitchen)
    zone_opens_to: frozenset[str] = frozenset()  # S2: zones the garage stands against (empty: the catalog's)
    service_kitchen: bool = False                # S2: service unit against the kitchen unit
    service_with_kitchen: bool = False           # S2: the service zone joins the kitchen unit (ground floor)
    door_to: frozenset[str] = frozenset()        # S2.1: spaces the garage door may open to (empty: any allowed)
    preferred: frozenset[str] = frozenset()      # S2.1: preferred targets of the garage door
    other_penalty_ft: float = 0.0                # route-length penalty of a door onto another target
    length_ref_ft: float = 0.0
    length_scale_ft: float = 1.0
    length_weight: float = 0.0
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {k: (sorted(v) if isinstance(v, frozenset) else v) for k, v in self.__dict__.items() if k != "extra"}


def route_settings(values: dict[str, Any] | None, kinds: dict[str, str] | None = None) -> RouteSettings:
    """Settings from the registry values (an empty registry gives the pre-k2 behaviour). A soft `required` or
    `service_kitchen_adjacent` is only scored and reported."""
    v = values or {}
    k = kinds or {}

    def hard(pid: str) -> bool:
        return bool(v.get(PREFIX + pid)) and k.get(PREFIX + pid, "hard") == "hard"

    def items(pid: str) -> frozenset[str]:
        return frozenset(v.get(PREFIX + pid) or ())

    return RouteSettings(
        required=hard("required"),
        avoid=items("avoid_space_types"),
        targets=items("target_types"),
        zone_opens_to=items("zone_opens_to"),
        service_kitchen=hard("service_kitchen_adjacent"),
        service_with_kitchen=hard("service_with_kitchen"),
        door_to=items("door_to_types"),
        preferred=items("preferred_door_to"),
        other_penalty_ft=float(v.get(PREFIX + "other_door_penalty_ft") or 0.0),
        length_ref_ft=float(v.get(PREFIX + "length_ref_ft") or 0.0),
        length_scale_ft=float(v.get(PREFIX + "length_scale_ft") or 1.0),
        length_weight=float(v.get(PREFIX + "length_weight") or 0.0))


def is_garage(spec) -> bool:
    return spec.zone == GARAGE_ZONE or str(spec.space_type).startswith(GARAGE_PREFIX)


# ------------------------------------------------------------------ S2: the zones around the garage


def zone_violation(zones: list[str], garage_units: set[int], links, rs: RouteSettings | None) -> str | None:
    """S2 (ground floor): the garage against a unit of `zone_opens_to`, and some service unit linked to some kitchen
    unit when both are on the floor. `garage_units`: units with a door's contact on the garage; `links`: unit pairs
    (a, b) with a door contact."""
    if rs is None or not rs.required:
        return None
    if rs.zone_opens_to and garage_units and not any(zones[k] in rs.zone_opens_to for k in garage_units):
        return "doors:garage_zone"
    if rs.service_kitchen:
        svc = {k for k, z in enumerate(zones) if z == SERVICE_ZONE}
        kit = {k for k, z in enumerate(zones) if z == KITCHEN_ZONE}
        if svc and kit and not any((min(a, b), max(a, b)) in links for a in svc for b in kit):
            return "doors:service_kitchen"
    return None


def direct_pairs(matrix, catalog) -> tuple[Any, ...]:
    """Hard D pairs whose roles are all passable rooms (dining - kitchen): S2.1 meets them only by a shared wall
    with an opening, so S2 must link their zones (a shared circulation zone is not enough)."""
    out = []
    for p in matrix.pairs:
        if p.type != "D" or p.kind != "hard" or p.anchored:
            continue
        types = [t for r in (p.a, p.b) for t in matrix.roles.get(r, ())]
        if types and all(catalog.has_space_type(t) and catalog.space_type(t).get("passable") for t in types):
            out.append(p)
    return tuple(out)


def direct_violation(pairs, located: dict[str, Any], links) -> str | None:
    """A direct pair whose roles sit in different zone units that are not linked (S2, ground and upper)."""
    for p in pairs:
        na, nb = located.get(p.a), located.get(p.b)
        if not na or not nb or set(na) & set(nb):
            continue
        if not any((min(x, y), max(x, y)) in links for x in na for y in nb
                   if isinstance(x, int) and isinstance(y, int)):
            return f"matrix:direct:{p.pair_id}"
    return None


# ------------------------------------------------------------------ S2.1: where the garage door goes


def door_target_ok(rs: RouteSettings | None, space_type: str) -> bool:
    """May the garage-to-house door open onto a space of this type?"""
    if rs is None or not rs.required or not rs.door_to:
        return True
    return space_type in rs.door_to


def crossable(spec, rs: RouteSettings) -> bool:
    """A space the route may walk through: passable or circulation, not the stair, not the half bath's vestibule,
    not a space to avoid, not the garage."""
    return ((spec.passable or spec.circulation) and spec.space_type not in (STAIR_TYPE, VESTIBULE_TYPE)
            and spec.space_type not in rs.avoid and not is_garage(spec))


def centres(labels: np.ndarray, nodes) -> dict[int, tuple[float, float]]:
    """Cell centroid (x, y in cells) of each node."""
    out = {}
    for k in nodes:
        rows, cols = np.nonzero(labels == k)
        if len(rows):
            out[k] = (float(cols.mean()) + 0.5, float(rows.mean()) + 0.5)
    return out


def plan_route(specs, labels: np.ndarray, garage: int, starts: dict[int, tuple[float, float]], neighbours,
               rs: RouteSettings, res: float) -> tuple[float, list[int]] | None:
    """Cheapest planned route from the garage door to the kitchen: `starts` maps each space the door may open onto
    to the door's point; `neighbours(x)` gives the crossable spaces next to x that an existing door or a possible
    opening joins. Lengths are between space centroids (ft); a door onto a space outside `preferred` costs
    `other_penalty_ft`. Returns (cost, [first space, ..., kitchen]) or None."""
    nodes = {k for k, s in enumerate(specs) if crossable(s, rs) or s.space_type in rs.targets}
    ctr = centres(labels, nodes | set(starts))
    sources = {}
    for j, p in starts.items():
        pen = 0.0 if not rs.preferred or specs[j].space_type in rs.preferred else rs.other_penalty_ft
        sources[j] = distance(p, ctr.get(j)) * res + pen

    def edges(x):
        if specs[x].space_type in rs.targets:
            return ()
        return [(y, distance(ctr.get(x), ctr.get(y)) * res) for y in neighbours(x) if y in nodes]

    return dijkstra(sources, edges, lambda x: specs[x].space_type in rs.targets)


# ------------------------------------------------------------------ S2.1: the route the doors give


def door_route(specs, doors: list[tuple[int, int, tuple[float, float] | None]], rs: RouteSettings, res: float,
               avoid: bool = True) -> dict[str, Any] | None:
    """Garage -> kitchen over the placed doors (a, b, centre in cells): door to door, never through the stair or a
    space to avoid (with `avoid`). None when the floor has no garage or no kitchen."""
    garage = [k for k, s in enumerate(specs) if is_garage(s)]
    kitchens = {k for k, s in enumerate(specs) if s.space_type in rs.targets}
    if not garage or not kitchens:
        return None
    g = garage[0]
    by_space: dict[int, list[int]] = {}
    for i, (a, b, _) in enumerate(doors):
        for n in (a, b):
            if n is not None and n >= 0:
                by_space.setdefault(n, []).append(i)

    def other(i, x):
        a, b, _ = doors[i]
        return b if a == x else a

    def blocked(y) -> bool:
        if y is None or y < 0:
            return True
        st = specs[y].space_type
        return st == STAIR_TYPE or is_garage(specs[y]) or (avoid and st in rs.avoid)

    sources = {(i, other(i, g)): 0.0 for i in by_space.get(g, []) if not blocked(other(i, g))}

    def edges(state):
        i, x = state
        if specs[x].space_type in rs.targets:
            return ()
        out = []
        for e in by_space.get(x, []):
            y = other(e, x)
            if e == i or blocked(y):
                continue
            out.append(((e, y), distance(doors[i][2], doors[e][2]) * res))
        return out

    got = dijkstra(sources, edges, lambda st: specs[st[1]].space_type in rs.targets)
    if got is None:
        return None
    cost, path = got
    first = path[0][1]
    return {"opens_to": specs[first].space_type, "length_ft": round(cost, 1),
            "through": [specs[x].space_type for _, x in path[:-1]], "clean": avoid}


def garage_route(specs, doors, rs: RouteSettings, res: float) -> dict[str, Any] | None:
    """The route report of a ground floor: the clean route (crossing nothing to avoid) or, failing it, the route
    that crosses (clean False), or {'reached': False}; None without a garage or a kitchen."""
    clean = door_route(specs, doors, rs, res, avoid=True)
    if clean is not None:
        return {"reached": True, **clean}
    dirty = door_route(specs, doors, rs, res, avoid=False)
    if dirty is not None:
        return {"reached": True, **dirty, "clean": False}
    garage = any(is_garage(s) for s in specs)
    kitchen = any(s.space_type in rs.targets for s in specs)
    return {"reached": False, "clean": False} if garage and kitchen else None


def route_violation(report: dict[str, Any] | None, rs: RouteSettings | None) -> str | None:
    if rs is None or not rs.required or report is None:
        return None
    if not report.get("clean"):
        return "route:garage_kitchen"
    if rs.door_to and report.get("opens_to") not in rs.door_to:
        return f"route:garage_door:{report.get('opens_to')}"
    return None


def route_score(report: dict[str, Any] | None, rs: RouteSettings) -> float | None:
    """1 up to `length_ref_ft`, falling with the excess over `length_scale_ft`; 0 when the route crosses a space
    to avoid; None without a route to score."""
    if report is None:
        return None
    if not report.get("clean"):
        return 0.0
    over = max(0.0, float(report["length_ft"]) - rs.length_ref_ft)
    return 1.0 / (1.0 + over / max(rs.length_scale_ft, 1e-9))


__all__ = [
    "PREFIX",
    "RouteSettings",
    "centres",
    "crossable",
    "direct_pairs",
    "direct_violation",
    "door_route",
    "door_target_ok",
    "garage_route",
    "is_garage",
    "plan_route",
    "route_score",
    "route_settings",
    "route_violation",
    "zone_violation",
]
