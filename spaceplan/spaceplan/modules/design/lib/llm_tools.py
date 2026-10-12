"""Tool definitions over the design registry, in the JSON-Schema form an LLM tool-use API accepts
(name, description, input_schema), plus a local dispatcher that runs them on a profile.

The tools let an assistant list, explain, propose and apply parameter changes and compare profiles; every change
goes through the same validation as the CLI (range, choices, code floor, constraints). `run_variant` and
`compare_variants` are declared for the pipeline integration of step S2.2f and answer "not_available" until then.
"""

from __future__ import annotations

from typing import Any

from spaceplan.modules.design.lib import design_profile as dp
from spaceplan.modules.design.lib.design_registry import KINDS, WHO, DesignRegistry

TOOLS_VERSION = "0.1.0"
VALUE_SCHEMA = {"description": "New value: number, text (enum), true/false or a list of texts",
                "anyOf": [{"type": "number"}, {"type": "string"}, {"type": "boolean"},
                          {"type": "array", "items": {"type": "string"}}]}
NOT_AVAILABLE = ("run_variant", "compare_variants")


def tool_definitions(reg: DesignRegistry) -> dict[str, Any]:
    ids = sorted(reg.params)
    pid = {"type": "string", "enum": ids, "description": "Parameter id, e.g. space.bathroom.aspect_max"}
    tools = [
        {"name": "list_parameters",
         "description": "List design parameters with their current value, unit, kind and who defines them. Filter "
                        "by id prefix (space.bedroom, door., light.), by who (client/designer/code), by kind or by "
                        "free text.",
         "input_schema": {"type": "object", "properties": {
             "prefix": {"type": "string"}, "who": {"type": "string", "enum": list(WHO)},
             "kind": {"type": "string", "enum": list(KINDS)}, "text": {"type": "string"},
             "lang": {"type": "string", "enum": ["es", "en"]}}, "additionalProperties": False}},
        {"name": "explain_parameter",
         "description": "Explain one parameter: value, unit, allowed range or choices, code limit (rule and source), "
                        "kind, who defines it, source and verification status.",
         "input_schema": {"type": "object", "properties": {"id": pid, "lang": {"type": "string", "enum": ["es", "en"]}},
                          "required": ["id"], "additionalProperties": False}},
        {"name": "propose_change",
         "description": "Validate a change of one parameter in the current profile without applying it; returns "
                        "ok, problems (range, code limit, constraints) and warnings.",
         "input_schema": {"type": "object", "properties": {
             "id": pid, "value": VALUE_SCHEMA, "kind": {"type": "string", "enum": list(KINDS)}},
             "required": ["id"], "additionalProperties": False}},
        {"name": "apply_changes",
         "description": "Apply one or more validated changes to the current profile with a reason; fails as a whole "
                        "if any change is invalid. Setting a value back to the baseline removes the change.",
         "input_schema": {"type": "object", "properties": {
             "changes": {"type": "array", "minItems": 1, "items": {"type": "object", "properties": {
                 "id": pid, "value": VALUE_SCHEMA, "kind": {"type": "string", "enum": list(KINDS)},
                 "reason": {"type": "string"}}, "required": ["id"], "additionalProperties": False}},
             "reason": {"type": "string"}}, "required": ["changes", "reason"], "additionalProperties": False}},
        {"name": "diff_profile",
         "description": "Parameters of the current profile that differ from the baseline.",
         "input_schema": {"type": "object", "properties": {}, "additionalProperties": False}},
        {"name": "run_variant",
         "description": "Run the generator on pilot lots with the current profile and return quality indicators "
                        "(available from step S2.2f).",
         "input_schema": {"type": "object", "properties": {
             "lots": {"type": "array", "items": {"type": "string"}},
             "stage": {"type": "string", "enum": ["S2.1"]}}, "additionalProperties": False}},
        {"name": "compare_variants",
         "description": "Compare the quality indicators of two runs (available from step S2.2f).",
         "input_schema": {"type": "object", "properties": {"a": {"type": "string"}, "b": {"type": "string"}},
                          "required": ["a", "b"], "additionalProperties": False}},
    ]
    return {"tools_version": TOOLS_VERSION, "registry_id": reg.registry_id, "registry_version": reg.version,
            "parameters": len(ids), "tools": tools}


def dispatch(reg: DesignRegistry, profile: dict[str, Any], name: str, arguments: dict[str, Any], author: str,
             date: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """(result, profile after the call). Errors come back as {"ok": False, "error": ...}, never raised."""
    try:
        lang = arguments.get("lang", "es")
        if name == "list_parameters":
            snap = {r["id"]: r for r in dp.snapshot(reg, profile, lang)}
            rows = reg.list(arguments.get("prefix"), arguments.get("who"), arguments.get("kind"), arguments.get("text"))
            return {"ok": True, "parameters": [{k: snap[p.id][k] for k in (
                "id", "value", "unit", "kind", "who", "changed", "description")} for p in rows]}, profile
        if name == "explain_parameter":
            row = next(r for r in dp.snapshot(reg, profile, lang) if r["id"] == arguments["id"]) \
                if arguments["id"] in reg.params else reg.explain(arguments["id"], lang)
            return {"ok": True, "parameter": row}, profile
        if name == "propose_change":
            return dp.propose(reg, profile, arguments["id"], arguments.get("value", dp.UNSET),
                              arguments.get("kind")), profile
        if name == "apply_changes":
            new = dp.apply(reg, profile, arguments["changes"], author, date, arguments.get("reason", ""))
            return {"ok": True, "changes": new["changes"], "profile_sha256": dp.profile_sha256(new)}, new
        if name == "diff_profile":
            return {"ok": True, "diff": dp.diff(reg, None, profile)}, profile
        if name in NOT_AVAILABLE:
            return {"ok": False, "error": "not_available", "detail": "pipeline integration arrives in step S2.2f"}, \
                profile
        return {"ok": False, "error": f"unknown tool {name!r}"}, profile
    except dp.ProfileError as exc:
        return {"ok": False, "error": "invalid_changes", "problems": exc.problems}, profile
    except KeyError as exc:
        return {"ok": False, "error": str(exc)}, profile


__all__ = ["TOOLS_VERSION", "dispatch", "tool_definitions"]
