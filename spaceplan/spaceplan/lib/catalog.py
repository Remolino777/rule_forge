"""Zone, scale and typology catalog (layer 2 inputs; spaceplan v1.1 section 8).

Design ranges live in data/catalog/residential_catalog.json with their source; code
only reads them. Normative minima (CRC) stay in a ruleset, never in the catalog.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from spaceplan.lib.schema_validation import load_schema
from spaceplan.lib_aux.hashing import sha256_of
from spaceplan.lib_aux.json_io import load_json, load_resource_json

DEFAULT_CATALOG = ("data", "catalog", "residential_catalog.json")


class CatalogError(ValueError):
    pass


@dataclass(frozen=True)
class Catalog:
    data: dict[str, Any]
    sha256: str

    @property
    def catalog_id(self) -> str:
        return self.data["catalog_id"]

    @property
    def version(self) -> str:
        return self.data["catalog_version"]

    def _find(self, key: str, field: str, value: str) -> dict[str, Any]:
        for item in self.data[key]:
            if item[field] == value:
                return item
        raise CatalogError(f"{field} {value!r} not found in catalog {self.catalog_id}")

    def scale(self, scale: str) -> dict[str, Any]:
        return self._find("scales", "scale", scale)

    def zone(self, zone: str) -> dict[str, Any]:
        return self._find("zones", "zone", zone)

    def space_type(self, space_type: str) -> dict[str, Any]:
        return self._find("space_types", "space_type", space_type)

    def has_space_type(self, space_type: str | None) -> bool:
        return any(t["space_type"] == space_type for t in self.data["space_types"])

    def typology(self, typology_id: str) -> dict[str, Any]:
        return self._find("typologies", "typology_id", typology_id)

    def profile(self, profile: str) -> dict[str, float]:
        try:
            return self.data["profiles"][profile]
        except KeyError as exc:
            raise CatalogError(f"profile {profile!r} not in catalog") from exc

    def garage_type(self, cars: int) -> str | None:
        return self.data["garage_by_cars"][str(cars)]

    def source_of(self, entry: dict[str, Any]) -> dict[str, str]:
        return entry.get("source") or self.data["default_source"]


def catalog_errors(data: dict[str, Any]) -> list[str]:
    validator = Draft202012Validator(load_schema("catalog"))
    errors = [f"{'/'.join(map(str, e.absolute_path))}: {e.message}" for e in validator.iter_errors(data)]
    if errors:
        return errors
    types = {t["space_type"]: t for t in data["space_types"]}
    for t in data["space_types"]:
        a = t["area"]
        if not a["min"] <= a["target"] <= a["max"]:
            errors.append(f"space_type {t['space_type']}: min <= target <= max violated")
        if t["scale"] == "support" and not t.get("host_types"):
            errors.append(f"space_type {t['space_type']}: support scale needs host_types")
        for host in t.get("host_types", []):
            if host not in types:
                errors.append(f"space_type {t['space_type']}: unknown host type {host!r}")
    for typ in data["typologies"]:
        for entry in typ["spaces"]:
            if entry["space_type"] not in types:
                errors.append(f"typology {typ['typology_id']}: unknown space type {entry['space_type']!r}")
    for cars, garage in data["garage_by_cars"].items():
        if garage is not None and garage not in types:
            errors.append(f"garage_by_cars[{cars}]: unknown space type {garage!r}")
    errors += cost_index_errors(data["cost_index"], types)
    if "vertical_schemes" in data:
        errors += vertical_scheme_errors(data["vertical_schemes"], types)
    if "area_analysis" in data:
        errors += area_analysis_errors(data["area_analysis"], types)
    return errors


VERTICAL_METRICS = ("open_area", "stair_independence", "supervision", "separation", "upper_efficiency", "frontage",
                    "cost")
AREA_PROFILES = ("minimum", "optimum", "maximum", "accessible", "staged_final")


def vertical_scheme_errors(vs: dict[str, Any], types: dict[str, Any]) -> list[str]:
    """Semantic checks of the vertical schemes (step 6.6)."""
    errors = []
    groups = [g["group"] for g in vs["groups"]]
    if len(groups) != len(set(groups)):
        errors.append("vertical_schemes.groups: duplicate group")
    for g in vs["groups"]:
        for st in g["match"].get("space_type", []):
            if st not in types:
                errors.append(f"vertical_schemes.groups.{g['group']}: unknown space type {st!r}")
    for name in [*vs["bedroom_groups"], *vs.get("cohesive_groups", [])]:
        if name not in groups:
            errors.append(f"vertical_schemes.bedroom_groups: unknown group {name!r}")
    ids = [s["scheme_id"] for s in vs["schemes"]]
    if len(ids) != len(set(ids)):
        errors.append("vertical_schemes.schemes: duplicate scheme_id")
    for scheme in vs["schemes"]:
        for group, floor in scheme["assign"].items():
            if group not in groups:
                errors.append(f"vertical scheme {scheme['scheme_id']}: unknown group {group!r}")
            if floor != "rule" and not (isinstance(floor, int) and 0 <= floor < scheme["floors"]):
                errors.append(f"vertical scheme {scheme['scheme_id']}: floor {floor!r} outside 0..{scheme['floors'] - 1}")
            if floor == "rule" and group != "laundry":
                errors.append(f"vertical scheme {scheme['scheme_id']}: only laundry follows a rule")
    sc = vs["scoring"]
    if set(sc["weights"]) != set(VERTICAL_METRICS):
        errors.append(f"vertical_schemes.scoring.weights must cover exactly {list(VERTICAL_METRICS)}")
    for m in sc["multipliers"]:
        if m["metric"] not in VERTICAL_METRICS:
            errors.append(f"vertical_schemes multiplier {m['rule_id']}: unknown metric {m['metric']!r}")
        if m["factor"] <= 0:
            errors.append(f"vertical_schemes multiplier {m['rule_id']}: factor must be positive")
    for key in ("separation_groups", "supervision_groups"):
        for name in sc[key]:
            if name not in groups:
                errors.append(f"vertical_schemes.scoring.{key}: unknown group {name!r}")
    return errors


def area_analysis_errors(aa: dict[str, Any], types: dict[str, Any]) -> list[str]:
    errors = []
    for prof in aa["profiles"]:
        if prof not in AREA_PROFILES:
            errors.append(f"area_analysis.profiles: unknown profile {prof!r}")
    for st in aa["daily_use"]["space_types"]:
        if st not in types:
            errors.append(f"area_analysis.daily_use: unknown space type {st!r}")
    if not 0 <= aa["garden_min_fraction_of_lot"] < 1:
        errors.append("area_analysis.garden_min_fraction_of_lot must be in [0, 1)")
    return errors


def cost_index_errors(ci: dict[str, Any], types: dict[str, Any]) -> list[str]:
    """Semantic checks of the relative cost catalog (step 6.5b)."""
    errors = []
    classes = ci["area_classes"]
    interior = {classes["wet_class"], *classes["zone_class"].values()}
    known = interior | set(classes["exterior_classes"])
    if set(ci["coefficients"]) != known:
        errors.append(f"cost_index.coefficients must cover exactly the area classes {sorted(known)}")
    anchor = ci["coefficients"].get(classes["anchor_class"], {})
    if anchor and not anchor["min"] == anchor["mode"] == anchor["max"] == 1:
        errors.append("cost_index: the anchor class coefficient must be fixed at 1")
    for group in ("coefficients", "form_factors"):
        for name, rng in ci[group].items():
            if not rng["min"] <= rng["mode"] <= rng["max"]:
                errors.append(f"cost_index.{group}.{name}: min <= mode <= max violated")
    mix = ci["reference_mix"]
    if set(mix) - interior:
        errors.append(f"cost_index.reference_mix: unknown classes {sorted(set(mix) - interior)}")
    if abs(sum(mix.values()) - 1) > 1e-9:
        errors.append("cost_index.reference_mix must sum to 1")
    if ci["estimates"]["stair_space_type"] not in types:
        errors.append("cost_index.estimates.stair_space_type is not a space type")
    if ci["default_model"] not in ci["models"]:
        errors.append("cost_index.default_model must be one of models")
    return errors


def load_catalog(path: str | Path | None = None) -> Catalog:
    data = load_json(path) if path else load_resource_json("spaceplan", *DEFAULT_CATALOG)
    errors = catalog_errors(data)
    if errors:
        raise CatalogError("invalid catalog:\n  - " + "\n  - ".join(errors))
    return Catalog(data=data, sha256=sha256_of(data))


def site_parameters(catalog: Catalog, site_zone: str) -> dict[str, Any]:
    return catalog._find("site_zone_types", "site_zone", site_zone)["parameters"]
