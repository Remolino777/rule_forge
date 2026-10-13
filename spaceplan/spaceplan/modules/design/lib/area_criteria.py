"""Area and door criteria (step 6.7a S2.2e): one reading of the area budget rules for the generator, a person (CLI)
and an LLM (tools).

Three layers, never mixed:
  * code       the CRC floor of a space (habitable area and least side), carried by the catalog minimum reference;
  * program    the residential catalog range (min / target / max) the area matrix and the profiles size the program
               with (registered by reference);
  * design     the recommended and the absolute maximum net area, the share of the house's net program area and the
               hierarchy ratios (design_space_standards S00-AREA-CAPS and the per-space rules).

Effective maximum of a space in a house of net program area N (garage excluded):

    cap = max(recommended, catalog minimum, min(absolute cap, hierarchy limit, share x N x size factor))

The size factor raises the shares in small houses (linear from 1 + bonus at the small house to 1 at the large one):
the suite and the kitchen take a larger share of a small home. A cap never cuts below the recommended size. The whole
suite (bedroom + walk-in + its bath) has its own cap relative to the target 2-car garage.

Every value comes from the registry values (baseline or a client profile); nothing here is a normative number.
"""

from __future__ import annotations

from typing import Any

AREA, DOORS, STRUCTURE = "area", "doors", "structure"
GROUPS = (AREA, DOORS, STRUCTURE)
STRUCTURE_PREFIXES = ("structure.", "circulation.arrival.", "door.grouping.", "upper.cantilever",
                      "circulation.upper_hall.")   # S2.2f; upper_hall: S2.2h
POLICY_PREFIX = "space.area."
DOOR_PREFIX = "door.conflicts."
SUITE, BEDROOM, DINING, LIVING = "primary_suite", "bedroom", "dining_room", "living_room"
GARAGE_REF = "space.garage_2car.area_target_sqft"
SUITE_PARTS = ("walk_in_closet", "primary_bath")
HIERARCHY = {SUITE: ("suite_to_bedroom_max", BEDROOM),      # space: (ratio parameter, reference space)
             DINING: ("dining_to_living_max", LIVING)}
SPACE_KEYS = {          # criteria key of a space -> parameter id pattern
    "rec_sqft": "space.{t}.area_rec_sqft",
    "cap_sqft": "space.{t}.area_cap_sqft",
    "share_max": "space.{t}.area_share_max",
    "program_min_sqft": "space.{t}.area_min_sqft",
    "program_target_sqft": "space.{t}.area_target_sqft",
    "program_max_sqft": "space.{t}.area_max_sqft",
    "min_side_ft": "space.{t}.min_side_ft",
}


class CriteriaError(KeyError):
    pass


# ------------------------------------------------------------------ values


def policy(values: dict[str, Any], key: str, default: Any = None) -> Any:
    return values.get(POLICY_PREFIX + key, default)


def cap_types(values: dict[str, Any]) -> list[str]:
    """Space types with design area criteria."""
    return sorted(pid.split(".")[1] for pid in values
                  if pid.startswith("space.") and pid.endswith(".area_cap_sqft"))


def enabled(values: dict[str, Any]) -> bool:
    return bool(policy(values, "caps_enabled", False))


def size_factor(values: dict[str, Any], net_sqft: float | None) -> float:
    if not net_sqft:
        return 1.0
    small = float(policy(values, "share_small_house_sqft", 0.0) or 0.0)
    large = float(policy(values, "share_large_house_sqft", 0.0) or 0.0)
    bonus = float(policy(values, "share_small_bonus", 0.0) or 0.0)
    if large <= small:
        return 1.0
    x = min(1.0, max(0.0, (large - net_sqft) / (large - small)))
    return 1.0 + bonus * x


def _v(values: dict[str, Any], t: str, key: str) -> float | None:
    v = values.get(SPACE_KEYS[key].format(t=t))
    return None if v is None else float(v)


def effective_cap(values: dict[str, Any], space_type: str, net_sqft: float | None = None) -> dict[str, Any] | None:
    """{cap, binding, recommended, floor, limits} of one space type, or None when the type has no design criteria."""
    cap_abs = _v(values, space_type, "cap_sqft")
    if cap_abs is None:
        return None
    rec = _v(values, space_type, "rec_sqft") or 0.0
    floor = max(rec, _v(values, space_type, "program_min_sqft") or 0.0)
    limits: dict[str, float] = {"absolute": cap_abs}
    if space_type in HIERARCHY:
        ratio_key, ref = HIERARCHY[space_type]
        ratio, ref_rec = policy(values, ratio_key), _v(values, ref, "rec_sqft")
        if ratio is not None and ref_rec:
            limits["hierarchy"] = round(float(ratio) * ref_rec, 1)
    share = _v(values, space_type, "share_max")
    if share is not None and net_sqft:
        limits["share"] = round(share * float(net_sqft) * size_factor(values, net_sqft), 1)
    binding = min(limits, key=lambda k: limits[k])
    cap = limits[binding]
    if cap < floor:
        cap, binding = floor, "recommended" if rec >= floor else "program_min"
    return {"space_type": space_type, "cap_sqft": round(cap, 1), "binding": binding, "recommended_sqft": rec,
            "floor_sqft": round(floor, 1), "limits": limits}


def suite_total_cap(values: dict[str, Any]) -> float | None:
    """Cap of the whole primary suite (bedroom + walk-in + its bath), None when not defined."""
    ratio, garage = policy(values, "suite_total_to_garage_max"), values.get(GARAGE_REF)
    if ratio is None or not garage:
        return None
    return round(float(ratio) * float(garage), 1)


def drawn_cap(values: dict[str, Any], cap_sqft: float) -> float:
    """The cap in the drawn plan (wall centrelines, no wall thickness yet)."""
    return cap_sqft * (1.0 + float(policy(values, "drawn_wall_allowance", 0.0) or 0.0))


def extra_package(values: dict[str, Any]) -> tuple[list[str], float]:
    """(space types, net area with overhead) of the extra-room package at the recommended sizes."""
    types = list(policy(values, "extra_room_types", []) or [])
    need = sum((_v(values, t, "rec_sqft") or _v(values, t, "program_target_sqft") or 0.0) for t in types)
    return types, round(need + float(policy(values, "extra_room_overhead_sqft", 0.0) or 0.0), 1)


# ------------------------------------------------------------------ views for a person or an LLM


def _row(reg, values: dict[str, Any], kinds: dict[str, str], pid: str, lang: str) -> dict[str, Any] | None:
    if pid not in values:
        return None
    p = reg.params[pid]
    return {"id": pid, "value": values[pid], "unit": p.unit, "kind": kinds.get(pid, p.kind), "who": p.who,
            "range": list(p.range) if p.range else None,
            "choices": list(p.choices) if p.choices is not None else None,
            "description": p.description.get(lang, p.description.get("en"))}


def criteria_view(reg, values: dict[str, Any], kinds: dict[str, str], group: str, space_type: str | None = None,
                  house_net_sqft: float | None = None, lang: str = "es") -> dict[str, Any]:
    """The criteria of a group, by layer, with the effective maximum for a house size when one is given."""
    if group == STRUCTURE:                      # S2.2f: structure of the upper floor, stair arrival, door grouping
        rows = [_row(reg, values, kinds, pid, lang) for pid in sorted(values) if pid.startswith(STRUCTURE_PREFIXES)]
        return {"group": STRUCTURE, "rules": [r for r in rows if r],
                "how_it_works": {"es": "Planta alta sobre la baja en una retícula común: las líneas portantes (contorno y "
                                       "muros que se apoyan en muros o vigas de abajo) dejan luces de vigueta de a lo "
                                       "más joist_span_max_ft; cada viga entre apoyos a lo más beam_span_max_ft; los "
                                       "muros de zona se corren hacia los ejes de abajo (snap_max_ft). La llegada de "
                                       "la escalera es un nodo de a lo más node_short_side_max_ft con un solo pasillo; "
                                       "las puertas de los dormitorios van en la esquina más cercana a la llegada.",
                                 "en": "Upper floor on the ground floor on one grid: the bearing lines (outline and "
                                       "walls standing on walls or beams below) keep joist spans within "
                                       "joist_span_max_ft; every beam between supports within beam_span_max_ft; zone "
                                       "walls move toward the axes below (snap_max_ft). The stair arrives into a node "
                                       "at most node_short_side_max_ft wide with one hall; bedroom doors go in the "
                                       "corner nearer the arrival."}[lang]}
    if group == DOORS:
        rows = [_row(reg, values, kinds, pid, lang) for pid in sorted(values) if pid.startswith(DOOR_PREFIX)]
        return {"group": DOORS, "rules": [r for r in rows if r],
                "how_it_works": {"es": "Geometría exacta (shapely) del barrido, la hoja cerrada y la zona de paso de "
                                       "cada puerta; R1 barridos que se cruzan, R2 barrido fuera del ambiente, R3 "
                                       "barrido sobre la zona de paso de otra puerta; E1 excepción dentro de una "
                                       "suite privada. Hoy se informan como indicadores; la colocación conjunta "
                                       "(P3) los aplicará.",
                                 "en": "Exact geometry (shapely) of each door's swing, closed leaf and approach "
                                       "zone; R1 crossing swings, R2 swing outside its room, R3 swing on another "
                                       "door's approach zone; E1 exception inside a private suite. Reported as "
                                       "indicators today; the joint placement (P3) will enforce them."}[lang]}
    if group != AREA:
        raise CriteriaError(f"unknown group {group!r}; use one of {list(GROUPS)}")
    types = cap_types(values)
    if space_type is not None and space_type not in types:
        raise CriteriaError(f"no area criteria for {space_type!r}; types: {types}")
    pol = [_row(reg, values, kinds, pid, lang) for pid in sorted(values) if pid.startswith(POLICY_PREFIX)]
    spaces = []
    for t in [space_type] if space_type else types:
        layers: dict[str, Any] = {"program": {}, "design": {}}
        for key, pat in SPACE_KEYS.items():
            row = _row(reg, values, kinds, pat.format(t=t), lang)
            if row is None:
                continue
            layers["program" if key.startswith("program_") or key == "min_side_ft" else "design"][key] = row
        floor = reg.params.get(SPACE_KEYS["program_min_sqft"].format(t=t))
        if floor is not None and floor.floor is not None:
            layers["code"] = floor.floor.to_dict()
        item: dict[str, Any] = {"space_type": t, "layers": layers}
        if house_net_sqft:
            item["effective"] = effective_cap(values, t, house_net_sqft)
        spaces.append(item)
    out = {"group": AREA, "policy": [r for r in pol if r], "spaces": spaces,
           "suite_total_cap_sqft": suite_total_cap(values),
           "extra_package": dict(zip(("types", "net_sqft"), extra_package(values), strict=True)),
           "how_it_works": {"es": "Máximo efectivo = max(recomendada, mínima del catálogo, min(máximo absoluto, límite "
                                  "de jerarquía, proporción × área neta × factor de tamaño)); nunca corta por debajo "
                                  "de la recomendada. El área que liberan los topes queda sin construir (freed_area) "
                                  "y, si alcanza para el paquete adicional, se propone según extra_room_policy.",
                            "en": "Effective maximum = max(recommended, catalog minimum, min(absolute cap, hierarchy "
                                  "limit, share x net area x size factor)); it never cuts below the recommended size. "
                                  "The area the caps free stays unbuilt (freed_area) and, when it holds the extra "
                                  "package, is proposed per extra_room_policy."}[lang]}
    if house_net_sqft:
        out["house_net_sqft"] = house_net_sqft
        out["size_factor"] = round(size_factor(values, house_net_sqft), 3)
    return out


def criteria_changes(values: dict[str, Any], group: str, changes: dict[str, Any],
                     space_type: str | None = None) -> list[dict[str, Any]]:
    """Registry changes ({"id", "value"}) of criteria keys: a space's keys (rec_sqft, cap_sqft, share_max,
    program_*_sqft, min_side_ft) with `space_type`, or the policy / door keys (the parameter id without its prefix)."""
    out = []
    for key, value in changes.items():
        if group == AREA and space_type is not None:
            if key not in SPACE_KEYS:
                raise CriteriaError(f"unknown space criterion {key!r}; use one of {sorted(SPACE_KEYS)}")
            pid = SPACE_KEYS[key].format(t=space_type)
        elif group == AREA:
            pid = POLICY_PREFIX + key
        elif group == STRUCTURE:
            ids = [key] if key in values and key.startswith(STRUCTURE_PREFIXES) else \
                [p + key for p in STRUCTURE_PREFIXES if p.endswith(".") and p + key in values]
            if len(ids) != 1:
                raise CriteriaError(f"unknown or ambiguous structure criterion {key!r}")
            pid = ids[0]
        elif group == DOORS:
            pid = DOOR_PREFIX + key
        else:
            raise CriteriaError(f"unknown group {group!r}; use one of {list(GROUPS)}")
        if pid not in values:
            raise CriteriaError(f"no parameter {pid!r} for criterion {key!r}")
        out.append({"id": pid, "value": value})
    return out


__all__ = [
    "AREA",
    "DOORS",
    "GROUPS",
    "HIERARCHY",
    "SPACE_KEYS",
    "STRUCTURE",
    "STRUCTURE_PREFIXES",
    "SUITE_PARTS",
    "CriteriaError",
    "cap_types",
    "criteria_changes",
    "criteria_view",
    "drawn_cap",
    "effective_cap",
    "enabled",
    "extra_package",
    "policy",
    "size_factor",
    "suite_total_cap",
]
