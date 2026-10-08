"""Household catalog (step 6.5a): dimensions, bedroom policy, tiers, rules and archetypes.

All design values live in data/catalog/household_catalog.json with source and status; the code
only reads them. Semantic checks: every predicate and count expression is well formed and uses
known facts, every space type exists in the residential catalog, every tier names an existing
area profile, household-layer rules never read the cultural profile.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from spaceplan.core.lib.catalog import Catalog
from spaceplan.core.lib.enums import CULTURE_ASPECTS, CULTURE_FACTS, HOUSEHOLD_FACTS, HOUSEHOLD_TIERS
from spaceplan.core.lib.schema_validation import load_schema
from spaceplan.core.lib_aux.hashing import sha256_of
from spaceplan.core.lib_aux.json_io import load_json, load_resource_json
from spaceplan.core.lib_aux.predicates import facts_used, number_errors, predicate_errors

DEFAULT_HOUSEHOLD_CATALOG = ("data", "catalog", "household_catalog.json")


class HouseholdCatalogError(ValueError):
    pass


@dataclass(frozen=True)
class HouseholdCatalog:
    data: dict[str, Any]
    sha256: str

    @property
    def catalog_id(self) -> str:
        return self.data["household_catalog_id"]

    @property
    def version(self) -> str:
        return self.data["household_catalog_version"]

    def archetype_ids(self) -> list[str]:
        return [a["archetype_id"] for a in self.data["archetypes"]]

    def has_archetype(self, archetype_id: str) -> bool:
        return archetype_id in self.archetype_ids()

    def archetype(self, archetype_id: str) -> dict[str, Any]:
        for a in self.data["archetypes"]:
            if a["archetype_id"] == archetype_id:
                return a
        raise HouseholdCatalogError(f"archetype {archetype_id!r} not in {self.catalog_id}")

    def preset(self, profile: str | None) -> dict[str, str]:
        for p in self.data["culture_presets"]:
            if p["profile"] == profile:
                return dict(p["aspects"])
        return {}

    def kitchen_typology(self, typology_id: str) -> dict[str, Any]:
        return next(t for t in self.data["kitchen_typologies"] if t["typology_id"] == typology_id)

    def tier(self, tier: str) -> dict[str, Any]:
        return next(t for t in self.data["tiers"] if t["tier"] == tier)

    def rules(self, layer: str = "household") -> list[dict[str, Any]]:
        return [r for r in self.data["rules"] if r["layer"] == layer]

    def source_of(self, entry: dict[str, Any]) -> dict[str, str]:
        return entry.get("source") or self.data["default_source"]

    def tag(self) -> dict[str, str]:
        return {"household_catalog_id": self.catalog_id, "household_catalog_version": self.version,
                "household_catalog_sha256": self.sha256}


def _effect_errors(effect: dict, path: str, known: set[str], residential: Catalog | None, layer: str) -> list[str]:
    errors = []
    if "count" in effect:
        errors += [f"{path}{e}" for e in number_errors(effect["count"], known, "/count")]
        if isinstance(effect["count"], dict) and effect["count"]["fact"] in CULTURE_FACTS and layer == "household":
            errors.append(f"{path}: household-layer rules must not read the cultural profile or aspects")
    if residential is None:
        return errors
    kind = effect["effect"]
    if kind in ("space", "type_area_factor") and not residential.has_space_type(effect["space_type"]):
        errors.append(f"{path}: unknown space type {effect['space_type']!r}")
    if kind == "relation_override":
        roles = residential.data["relation_matrix"]["roles"]
        errors += [f"{path}: unknown matrix role {r!r}" for r in (effect["a"], effect["b"]) if r not in roles]
    if kind == "anchor_override":
        anchors = {a["anchor_id"] for prof in residential.data["zoning_profiles"].values() for a in prof["anchors"]}
        if effect["anchor_id"] not in anchors:
            errors.append(f"{path}: unknown zoning anchor {effect['anchor_id']!r}")
    if kind == "backyard_element":
        elements = {e["element"] for e in residential.data["backyard_elements"]}
        if effect["element"] not in elements:
            errors.append(f"{path}: unknown backyard element {effect['element']!r}")
    if layer == "household" and kind in CULTURE_ONLY_EFFECTS:
        errors.append(f"{path}: effect {kind!r} belongs to the culture layer")
    return errors


CULTURE_ONLY_EFFECTS = ("relation_override", "anchor_override", "backyard_element", "backyard_green")


def _rule_errors(rule: dict, known: set[str], residential: Catalog | None) -> list[str]:
    rid = rule["rule_id"]
    errors = [f"rule {rid}{e}" for e in predicate_errors(rule["when"], known, "/when")]
    if rule["layer"] == "household" and facts_used(rule["when"]) & set(CULTURE_FACTS):
        errors.append(f"rule {rid}: household-layer rules must not read the cultural profile or aspects")
    for i, effect in enumerate(rule["effects"]):
        errors += _effect_errors(effect, f"rule {rid}/effects[{i}]", known, residential, rule["layer"])
    return errors


def _culture_errors(data: dict, known: set[str], residential: Catalog | None) -> list[str]:
    errors = []
    aspects = {a["aspect"]: set(a["values"]) for a in data["culture_aspects"]}
    if tuple(aspects) != CULTURE_ASPECTS:
        errors.append(f"culture_aspects must list exactly {CULTURE_ASPECTS} in order")
    for preset in data["culture_presets"]:
        for aspect, value in preset["aspects"].items():
            if value not in aspects.get(aspect, ()):
                errors.append(f"culture preset {preset['profile']}: {aspect}={value!r} is not an allowed value")
    typologies = [t["typology_id"] for t in data["kitchen_typologies"]]
    errors += [f"duplicate kitchen typology {t!r}" for t in sorted({t for t in typologies if typologies.count(t) > 1})]
    for t in data["kitchen_typologies"]:
        for i, effect in enumerate(t["effects"]):
            errors += _effect_errors(effect, f"kitchen typology {t['typology_id']}/effects[{i}]", known, residential,
                                     "culture")
    for i, sel in enumerate(data["kitchen_typology_selection"]):
        errors += [f"kitchen_typology_selection[{i}]{e}" for e in predicate_errors(sel["when"], known, "/when")]
        if sel["typology"] not in typologies:
            errors.append(f"kitchen_typology_selection[{i}]: unknown typology {sel['typology']!r}")
    return errors


def household_catalog_errors(data: dict[str, Any], residential: Catalog | None = None) -> list[str]:
    validator = Draft202012Validator(load_schema("household_catalog"))
    errors = [f"{'/'.join(map(str, e.absolute_path)) or '<root>'}: {e.message}" for e in validator.iter_errors(data)]
    if errors:
        return errors
    known = set(HOUSEHOLD_FACTS) | set(CULTURE_FACTS)
    errors += _culture_errors(data, known, residential)
    ids = [r["rule_id"] for r in data["rules"]]
    errors += [f"duplicate rule_id {r!r}" for r in sorted({r for r in ids if ids.count(r) > 1})]
    for rule in data["rules"]:
        errors += _rule_errors(rule, known, residential)
    tiers = [t["tier"] for t in data["tiers"]]
    if tuple(tiers) != HOUSEHOLD_TIERS:
        errors.append(f"tiers must be listed in order {HOUSEHOLD_TIERS}, got {tiers}")
    if residential is not None:
        for t in data["tiers"]:
            if t["area_profile"] not in residential.data["profiles"]:
                errors.append(f"tier {t['tier']}: unknown area profile {t['area_profile']!r}")
        for role, types in data["bedroom_policy"]["room_space_types"].items():
            errors += [f"room_space_types.{role}.{tier}: unknown space type {st!r}"
                       for tier, st in types.items() if not residential.has_space_type(st)]
    bands = data["age_bands"]
    for lo, hi in pairwise(bands):
        if lo["max_years"] is None or hi["min_years"] != lo["max_years"] + 1:
            errors.append(f"age bands {lo['band']} and {hi['band']} are not contiguous")
    if bands and (bands[0]["min_years"] != 0 or bands[-1]["max_years"] is not None):
        errors.append("age bands must start at 0 and end open")
    archetype_ids = [a["archetype_id"] for a in data["archetypes"]]
    errors += [f"duplicate archetype {a!r}" for a in sorted({a for a in archetype_ids if archetype_ids.count(a) > 1})]
    return errors


def load_household_catalog(path: str | Path | None = None, residential: Catalog | None = None) -> HouseholdCatalog:
    data = load_json(path) if path else load_resource_json("spaceplan", *DEFAULT_HOUSEHOLD_CATALOG)
    errors = household_catalog_errors(data, residential)
    if errors:
        raise HouseholdCatalogError("invalid household catalog:\n  - " + "\n  - ".join(errors))
    return HouseholdCatalog(data=data, sha256=sha256_of(data))
