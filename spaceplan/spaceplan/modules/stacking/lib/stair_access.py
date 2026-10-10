"""Receiving spaces at the stair ends, use of the space under the stair and rule traces (step 6.7a, stage S1.1).

Client rules (data/rules/client_stair_rules.json, kind "client") say which spaces may receive each end (K01, K02),
what the space under the stair may become (K03) and that a half bath is always vestibulated (K04); K05 extends the
D/I/N matrix for stage S2. Normative rules come from the CRC stair ruleset. Every check is traced with its kind so a
reader (and RuleForge) can tell a code failure from a client-rule failure: a design can pass the code and still break
a client rule (a stair arriving into a bedroom).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from spaceplan.core.lib.rules import RuleSet, load_ruleset, load_ruleset_resource

CLIENT_RULESET = ("data", "rules", "client_stair_rules.json")
TOP_RULE = "K01-STAIR-TOP-ARRIVAL"
BOTTOM_RULE = "K02-STAIR-BOTTOM-START"
UNDER_KITCHEN_RULE = "K03-UNDER-STAIR-KITCHEN"
HALF_BATH_RULE = "K04-HALF-BATH-VESTIBULE"
RELATIONS_RULE = "K05-STAIR-RELATIONS"
NORMATIVE, CLIENT = "normative", "client"
PASS, FAIL, DEFERRED = "pass", "fail", "deferred_to_S2"


def load_client_ruleset(path: str | Path | None = None) -> RuleSet:
    return load_ruleset(path) if path else load_ruleset_resource(*CLIENT_RULESET)


def rule_kind(rs: RuleSet, rule_id: str) -> str:
    return rs.rule(rule_id).get("kind") or rs.data.get("kind") or NORMATIVE


def trace(rs: RuleSet, rule_id: str, result: str, detail: str | None = None) -> dict[str, Any]:
    return {"rule_id": rule_id, "kind": rule_kind(rs, rule_id), "result": result, "status": rs.status(rule_id),
            "source": rs.source_tag(rule_id), "detail": detail}


def space_type_of(name: str, types: list[str]) -> str | None:
    """Space type of a program instance name (bedroom_teen_1 -> bedroom): the longest type it starts with."""
    best = None
    for t in types:
        if (name == t or name.startswith(t + "_")) and (best is None or len(t) > len(best)):
            best = t
    return best


def upper_rooms(upper_spaces: list[str], catalog, access: dict[str, Any]) -> int:
    """Rooms the upper floor serves: habitable spaces of the room zones plus the extra room types."""
    types = [t["space_type"] for t in catalog.data["space_types"]]
    n = 0
    for name in upper_spaces:
        st = space_type_of(name, types)
        if st is None:
            continue
        spec = catalog.space_type(st)
        if st in access["room_space_types_extra"] or (spec.get("habitable") and spec["zone"] in access["room_zones"]):
            n += 1
    return n


def top_receiving(client: RuleSet, rooms: int, small_max: int) -> dict[str, Any]:
    p = client.params(TOP_RULE)
    small = rooms <= small_max
    return {"receiving": p["small_house"] if small else p["default"], "small_house": small, "upper_rooms": rooms,
            "allowed": list(p["allowed"]), "max": p["max"], "forbidden": list(p["forbidden"])}


def bottom_receiving(client: RuleSet, options: list[str], preferred: str) -> dict[str, Any]:
    p = client.params(BOTTOM_RULE)
    by_opt = {o["option"]: o for o in p["options"]}
    return {"options": [{"option": o, "label": by_opt[o]["label"], "receiving": list(by_opt[o]["receiving"])}
                        for o in options],
            "preferred": preferred, "forbidden": list(p["forbidden"])}


def check_receiving(client: RuleSet, end: str, space_type: str) -> dict[str, Any]:
    """Trace of a client rule for the space an end lands in (used by S2 and by the RuleForge test cases)."""
    if end == "top":
        p = client.params(TOP_RULE)
        ok = space_type in p["allowed"] and space_type not in p["forbidden"]
        return trace(client, TOP_RULE, PASS if ok else FAIL, f"top end into {space_type}")
    p = client.params(BOTTOM_RULE)
    allowed = {s for o in p["options"] for s in o["receiving"]}
    ok = space_type in allowed and space_type not in p["forbidden"]
    return trace(client, BOTTOM_RULE, PASS if ok else FAIL, f"bottom end from {space_type}")


def under_stair_use(client: RuleSet, opens_to: str | None, half_bath_fits: bool) -> dict[str, Any]:
    """Use of the space under the stair given the space its access side opens to (None: decided in S2)."""
    kitchen = client.params(UNDER_KITCHEN_RULE)
    hb = client.params(HALF_BATH_RULE)
    if opens_to in kitchen["opens_to"]:
        return {"use": kitchen["uses"][0], "rule": UNDER_KITCHEN_RULE,
                "trace": trace(client, UNDER_KITCHEN_RULE, PASS, f"opens to {opens_to}: storage only")}
    if not half_bath_fits:
        return {"use": "storage", "rule": None, "trace": None}
    if opens_to in hb["door_to_allowed"] or opens_to is None:
        return {"use": "half_bath", "rule": HALF_BATH_RULE,
                "trace": trace(client, HALF_BATH_RULE, PASS if opens_to else DEFERRED,
                               "vestibule beside the half bath" + ("" if opens_to else "; door side set in S2"))}
    return {"use": "half_bath", "rule": HALF_BATH_RULE,
            "trace": trace(client, HALF_BATH_RULE, PASS,
                           f"opens to {opens_to}: door through the vestibule, not directly into it")}


def access_side(half_bath: dict[str, Any] | None, bottom_zone, tol: float = 0.5) -> str:
    """Where the half-bath spot under the stair opens relative to the bottom end: 'bottom' when its vestibule or the
    half bath touches the bottom arrival zone (it then opens to whatever receives the bottom), else 'apart'."""
    if half_bath is None:
        return "none"
    near = half_bath["vestibule"].distance(bottom_zone) <= tol or half_bath["half_bath"].distance(bottom_zone) <= tol
    return "bottom" if near else "apart"


def uses_by_bottom_option(client: RuleSet, bottom: dict[str, Any], side: str, half_bath_fits: bool) -> dict[str, Any]:
    """Use of the space under the stair for each allowed bottom option (K03: toward the kitchen -> storage)."""
    out = {}
    for o in bottom["options"]:
        opens_to = o["receiving"][0] if side == "bottom" else None
        out[o["option"]] = under_stair_use(client, opens_to, half_bath_fits)["use"]
    return out


def relations(client: RuleSet) -> dict[str, Any]:
    p = client.params(RELATIONS_RULE)
    return {"roles": p["roles"], "relations": p["relations"], "rule_id": RELATIONS_RULE}


__all__ = ["BOTTOM_RULE", "CLIENT", "CLIENT_RULESET", "DEFERRED", "FAIL", "HALF_BATH_RULE", "NORMATIVE", "PASS",
           "RELATIONS_RULE", "TOP_RULE", "UNDER_KITCHEN_RULE", "access_side", "bottom_receiving", "check_receiving",
           "load_client_ruleset", "relations", "rule_kind", "space_type_of", "top_receiving", "trace",
           "under_stair_use", "upper_rooms", "uses_by_bottom_option"]
