"""Expand a catalog typology into a brief program block (spaces + zone budgets)."""

from __future__ import annotations

from collections import defaultdict

from spaceplan.core.lib.catalog import Catalog, CatalogError
from spaceplan.core.lib.enums import Zone


def _round_to(value: float, step: float) -> float:
    return float(round(value / step) * step)


def profiled_target(catalog: Catalog, space_type: dict, profile: str) -> float:
    """Catalog target scaled by the profile multiplier of its zone, clamped to [min, max]."""
    area = space_type["area"]
    factor = catalog.profile(profile)[space_type["zone"]]
    target = _round_to(area["target"] * factor, catalog.data["target_rounding_sqft"])
    return min(max(target, area["min"]), area["max"])


def _instances(catalog: Catalog, typology: dict, garage_cars: int) -> list[tuple[str, str]]:
    """(space_id, space_type) in typology order; numbered ids when a type repeats."""
    entries = [(e["space_type"], e["count"]) for e in typology["spaces"]]
    garage = catalog.garage_type(garage_cars)
    if garage:
        entries.append((garage, 1))
    out = []
    for space_type, count in entries:
        for i in range(1, count + 1):
            out.append((space_type if count == 1 else f"{space_type}_{i}", space_type))
    return out


def _assign_hosts(catalog: Catalog, instances: list[tuple[str, str]]) -> dict[str, str | None]:
    """Satellites get a host: round-robin over instances of the first host type available.

    Closets go one per bedroom first; once bedrooms run out they fall to the next host type.
    """
    by_type: dict[str, list[str]] = defaultdict(list)
    for space_id, space_type in instances:
        by_type[space_type].append(space_id)
    used: dict[str, int] = defaultdict(int)
    hosts: dict[str, str | None] = {}
    for space_id, space_type in instances:
        host_types = catalog.space_type(space_type).get("host_types")
        if not host_types:
            continue
        hosts[space_id] = None
        for host_type in host_types:
            candidates = by_type.get(host_type, [])
            if used[host_type] < len(candidates):
                hosts[space_id] = candidates[used[host_type]]
                used[host_type] += 1
                break
        else:
            for host_type in host_types:
                if by_type.get(host_type):
                    hosts[space_id] = by_type[host_type][0]
                    break
    return hosts


def expand_typology(catalog: Catalog, typology_id: str, garage_cars: int, profile: str = "balanced") -> dict:
    typology = catalog.typology(typology_id)
    if typology["dwelling_type"] == "apartment" and garage_cars:
        raise CatalogError(f"{typology_id} is an apartment typology: garage_cars must be 0")
    instances = _instances(catalog, typology, garage_cars)
    hosts = _assign_hosts(catalog, instances)
    spaces, budgets = [], defaultdict(lambda: [0.0, 0.0])
    for space_id, space_type in instances:
        t = catalog.space_type(space_type)
        zone = catalog.zone(t["zone"])
        spaces.append(
            {
                "space_id": space_id,
                "space_type": space_type,
                "zone": t["zone"],
                "scale": t["scale"],
                "wet": t["wet"],
                "min_area_sqft": float(t["area"]["min"]),
                "target_area_sqft": profiled_target(catalog, t, profile),
                "floor_preference": 0 if zone["floor_rule"] == "hard" and zone["floor_preference"] == "ground" else None,
                "host_space_id": hosts.get(space_id),
            }
        )
        budgets[t["zone"]][0] += t["area"]["min"]
        budgets[t["zone"]][1] += t["area"]["max"]
    return {
        "spaces": spaces,
        "zone_budgets": {
            z.value: {"min_sqft": budgets[z.value][0], "max_sqft": budgets[z.value][1]}
            for z in Zone
            if z.value in budgets
        },
        "garage_cars": garage_cars,
        "required_gross_area_sqft": None,
        "gross_factor": typology["gross_factor"],
    }


# ----------------------------------------------------------------------------- household programs (6.5a)


def _instance_ids(space_type: str, role: str, count: int) -> list[str]:
    base = space_type if role == "general" or space_type.startswith(role) else f"{space_type}_{role}"
    return [base] if count == 1 else [f"{base}_{i}" for i in range(1, count + 1)]


def program_from_needs(
    catalog: Catalog,
    needs: list,
    tier: str,
    garage_cars: int,
    area_profile: str,
    zone_factors: dict[str, float],
    gross_factor: float,
    type_factors: dict[str, float] | None = None,
) -> dict:
    """Brief program block for one tier of a household derivation.

    needs: Need objects in catalog order (space_type, household_role, counts, ground_counts).
    Targets: catalog target x profile factor of the zone x household zone factor x space-type factor
    (cultural layer), rounded and
    clamped to the type range. The first `ground_counts[tier]` instances of a need get floor 0.
    """
    instances: list[tuple[str, str, str, bool]] = []  # (space_id, space_type, role, ground)
    for need in needs:
        count = need.counts[tier]
        ground = need.ground_counts[tier]
        for i, space_id in enumerate(_instance_ids(need.space_type, need.household_role, count)):
            instances.append((space_id, need.space_type, need.household_role, i < ground))
    garage = catalog.garage_type(garage_cars)
    if garage:
        instances.append((garage, garage, "general", False))
    hosts = _assign_hosts(catalog, [(sid, st) for sid, st, _, _ in instances])
    profile = catalog.profile(area_profile)
    step = catalog.data["target_rounding_sqft"]
    spaces, budgets = [], defaultdict(lambda: [0.0, 0.0])
    for space_id, space_type, role, ground in instances:
        t = catalog.space_type(space_type)
        zone = catalog.zone(t["zone"])
        area = t["area"]
        raw = area["target"] * profile[t["zone"]] * zone_factors.get(t["zone"], 1.0) * (type_factors or {}).get(space_type, 1.0)
        target = min(max(_round_to(raw, step), area["min"]), area["max"])
        hard_ground = zone["floor_rule"] == "hard" and zone["floor_preference"] == "ground"
        spaces.append(
            {
                "space_id": space_id,
                "space_type": space_type,
                "zone": t["zone"],
                "scale": t["scale"],
                "wet": t["wet"],
                "min_area_sqft": float(area["min"]),
                "target_area_sqft": float(target),
                "floor_preference": 0 if hard_ground or ground else None,
                "host_space_id": hosts.get(space_id),
                "household_role": role,
            }
        )
        budgets[t["zone"]][0] += area["min"]
        budgets[t["zone"]][1] += area["max"]
    return {
        "spaces": spaces,
        "zone_budgets": {
            z.value: {"min_sqft": budgets[z.value][0], "max_sqft": budgets[z.value][1]}
            for z in Zone
            if z.value in budgets
        },
        "garage_cars": garage_cars,
        "required_gross_area_sqft": None,
        "gross_factor": gross_factor,
    }
