"""Schema and semantic validation of briefs and packages."""

from __future__ import annotations

from collections import Counter

from jsonschema import Draft202012Validator

from spaceplan.core.lib.relation_graph import (
    build_relation_graph,
    node_namespace,
    relation_conflicts,
)
from spaceplan.core.lib_aux.json_io import load_resource_json


class BriefValidationError(ValueError):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("invalid brief:\n  - " + "\n  - ".join(errors))


class PackageValidationError(ValueError):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("invalid package:\n  - " + "\n  - ".join(errors))


def load_schema(name: str) -> dict:
    return load_resource_json("spaceplan", "data", "schemas", f"{name}.schema.json")


def _schema_errors(instance: dict, schema_name: str) -> list[str]:
    validator = Draft202012Validator(load_schema(schema_name))
    errors = sorted(validator.iter_errors(instance), key=lambda e: list(e.absolute_path))
    return [f"{'/'.join(map(str, e.absolute_path)) or '<root>'}: {e.message}" for e in errors]


def _duplicates(values: list[str], label: str) -> list[str]:
    return [f"duplicate {label} {v!r}" for v, n in Counter(values).items() if n > 1]


def _unit_errors(brief: dict) -> list[str]:
    errors: list[str] = []
    unit = brief["unit"]
    ids = [e["edge_id"] for e in unit["edges"]]
    errors += _duplicates(ids, "unit edge_id")
    if len(ids) != len(unit["vertices"]):
        errors.append(f"unit has {len(unit['vertices'])} vertices but {len(ids)} edges")
    roles = {e["edge_id"]: e["role"] for e in unit["edges"]}
    if roles.get(unit["entrance"]["edge_id"]) != "access":
        errors.append("unit entrance must be on an edge with role 'access'")
    if "exterior" not in roles.values():
        errors.append("unit needs at least one exterior edge (light and ventilation)")
    if brief["program"]["garage_cars"] != 0:
        errors.append("apartments cannot have garage_cars > 0")
    return errors


def semantic_errors(brief: dict) -> list[str]:
    """Cross-field checks the JSON Schema cannot express."""
    errors: list[str] = []
    errors += _duplicates([s["space_id"] for s in brief["program"]["spaces"]], "space_id")
    errors += _duplicates([r["relation_id"] for r in brief["relations"]], "relation_id")
    errors += _duplicates([g["group_id"] for g in brief["relation_groups"]], "group_id")
    if brief["dwelling_type"] == "apartment":
        errors += _unit_errors(brief)
    else:
        errors += _lot_errors(brief)
    errors += _program_errors(brief)
    return errors


def _lot_errors(brief: dict) -> list[str]:
    errors: list[str] = []
    lot, streets = brief["lot"], brief["streets"]
    edges = lot["edges"]
    edge_ids = [e["edge_id"] for e in edges]
    errors += _duplicates(edge_ids, "edge_id")
    errors += _duplicates([s["street_id"] for s in streets], "street_id")
    if len(edges) != len(lot["vertices"]):
        errors.append(f"lot has {len(lot['vertices'])} vertices but {len(edges)} edges")

    roles = Counter(s["role"] for s in streets)
    if roles["primary"] != 1:
        errors.append(f"exactly one primary street is required (found {roles['primary']})")
    if roles["secondary"] > 1:
        errors.append("at most one secondary street is allowed")

    frontage_of: dict[str, str] = {}
    for street in streets:
        for eid in street["frontage_edge_ids"]:
            if eid not in edge_ids:
                errors.append(f"street {street['street_id']}: unknown frontage edge {eid!r}")
            elif eid in frontage_of:
                errors.append(f"edge {eid} fronts two streets")
            else:
                frontage_of[eid] = street["street_id"]
        cut = street["curb_cut"]
        if cut and cut["edge_id"] not in street["frontage_edge_ids"]:
            errors.append(f"street {street['street_id']}: curb cut on non-frontage edge {cut['edge_id']}")
    role_of = {s["street_id"]: s["role"] for s in streets}
    for edge in edges:
        eid, sid, cls = edge["edge_id"], edge["street_id"], edge["boundary_class"]
        if sid is not None and frontage_of.get(eid) != sid:
            errors.append(f"edge {eid}: street_id {sid!r} does not list it as frontage")
        if eid in frontage_of and sid != frontage_of[eid]:
            errors.append(f"edge {eid}: is frontage of {frontage_of[eid]!r} but street_id is {sid!r}")
        expected = {"primary": "front", "secondary": "street_side"}.get(role_of.get(frontage_of.get(eid)))
        if cls is not None and expected is not None and cls != expected:
            errors.append(f"edge {eid}: declared {cls!r} but its street makes it {expected!r}")
        if cls in ("front", "street_side") and eid not in frontage_of:
            errors.append(f"edge {eid}: declared {cls!r} without a street")
    return errors


def _program_errors(brief: dict) -> list[str]:
    errors: list[str] = []

    namespace = node_namespace(brief)
    collisions = {s["space_id"] for s in brief["program"]["spaces"]} & (
        set(namespace) - {s["space_id"] for s in brief["program"]["spaces"]}
    )
    errors += [f"space_id {c!r} collides with a reserved zone/street id" for c in sorted(collisions)]
    endpoints = [(r["relation_id"], r["a"]) for r in brief["relations"]]
    endpoints += [(r["relation_id"], r["b"]) for r in brief["relations"]]
    for group in brief["relation_groups"]:
        endpoints += [(group["group_id"], m[x]) for m in group["members"] for x in ("a", "b")]
        if group["k"] > len(group["members"]):
            errors.append(f"group {group['group_id']}: k={group['k']} exceeds its members")
    errors += [f"{owner}: unknown endpoint {node!r}" for owner, node in endpoints if node not in namespace]

    space_ids = {s["space_id"] for s in brief["program"]["spaces"]}
    for space in brief["program"]["spaces"]:
        host = space.get("host_space_id")
        if host is not None and (host not in space_ids or host == space["space_id"]):
            errors.append(f"space {space['space_id']}: host_space_id {host!r} is not another space")
        if space["min_area_sqft"] > space["target_area_sqft"]:
            errors.append(f"space {space['space_id']}: min area above target")
    for zone, budget in brief["program"]["zone_budgets"].items():
        if budget["min_sqft"] > budget["max_sqft"]:
            errors.append(f"zone budget {zone}: min above max")

    if not errors:
        errors += relation_conflicts(build_relation_graph(brief))
    return errors


def validate_brief(brief: dict) -> None:
    errors = _schema_errors(brief, "brief")
    if not errors and "program" not in brief:
        errors = ["brief has no program: give one, or a household block and derive it first "
                  "(spaceplan.main.run_household.resolve_brief_program)" if "household" in brief
                  else "brief needs a program or a household block"]
    if not errors:
        errors = semantic_errors(brief)
    if errors:
        raise BriefValidationError(errors)


def validate_package(package: dict) -> None:
    errors = _schema_errors(package, "package")
    if errors:
        raise PackageValidationError(errors)


# ------------------------------------------------------------------------------------ module contracts

CONTRACTS = ("lot_capacity", "site_plan", "program", "cost_report", "program_portfolio", "zoning_scheme",
             "area_matrix")
REFERENCED_SCHEMAS = ("brief", "package")  # contract blocks reference these definitions


def load_contract_schema(name: str) -> dict:
    return load_resource_json("spaceplan", "contracts", "schemas", f"{name}.schema.json")


def contract_registry():
    """Registry that resolves the references of the contract schemas into the brief and package schemas."""
    from referencing import Registry, Resource

    schemas = [load_schema(n) for n in REFERENCED_SCHEMAS] + [load_contract_schema(n) for n in CONTRACTS]
    resources = [Resource.from_contents(s) for s in schemas]
    return Registry().with_resources((r.id(), r) for r in resources)


def contract_errors(instance: dict, name: str, registry=None) -> list[str]:
    validator = Draft202012Validator(load_contract_schema(name), registry=registry or contract_registry())
    errors = sorted(validator.iter_errors(instance), key=lambda e: list(e.absolute_path))
    return [f"{'/'.join(map(str, e.absolute_path)) or '<root>'}: {e.message}" for e in errors]
