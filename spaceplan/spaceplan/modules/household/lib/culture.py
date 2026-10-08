"""Cultural layer -> brief blocks the zoning already consumes (step 6.5c).

The culture output of one tier (relation overrides by matrix role, zoning anchor modes, backyard
priorities and green reserve) is merged into the brief with one precedence rule: **what the brief
states explicitly wins**.

* relation_overrides: a brief entry for a role pair wins over the culture entry for that pair;
* zoning_overrides.anchors: a brief mode for an anchor wins;
* backyard_program: an element with an explicit brief priority keeps it; elements without priority
  take the culture priority; culture elements marked `add` (covered terrace, outdoor kitchen) are
  appended when absent; an explicit brief green reserve wins. Without a brief backyard program, the
  culture preferences become one.

Everything the brief overrode is reported, so the client sees which preferences did not apply.
"""

from __future__ import annotations

import copy


def _pair(a: str, b: str) -> frozenset:
    return frozenset((a, b))


def merge_culture_into_brief(brief: dict, culture_tier: dict) -> tuple[dict, dict]:
    """(brief with culture merged, record of applied and overridden preferences)."""
    out = copy.deepcopy(brief)
    applied, overridden = [], []

    relations = culture_tier["relation_overrides"]
    if relations:
        given = list(out.get("relation_overrides") or [])
        stated = {_pair(o["a"], o["b"]) for o in given}
        for o in relations:
            if _pair(o["a"], o["b"]) in stated:
                overridden.append({"kind": "relation", "a": o["a"], "b": o["b"], "rule_id": o["rule_id"]})
                continue
            given.append({k: o[k] for k in ("a", "b", "type", "kind", "weight") if k in o})
            applied.append({"kind": "relation", "a": o["a"], "b": o["b"], "type": o["type"], "rule_id": o["rule_id"]})
        out["relation_overrides"] = given

    anchors = culture_tier["anchor_overrides"]
    if anchors:
        zo = copy.deepcopy(out.get("zoning_overrides") or {"anchors": {}})
        for anchor_id, o in anchors.items():
            if anchor_id in zo["anchors"]:
                overridden.append({"kind": "anchor", "anchor_id": anchor_id, "rule_id": o["rule_id"]})
                continue
            zo["anchors"][anchor_id] = o["mode"]
            applied.append({"kind": "anchor", "anchor_id": anchor_id, "mode": o["mode"], "rule_id": o["rule_id"]})
        out["zoning_overrides"] = zo

    yard = culture_tier["backyard"]
    if yard["elements"] or yard["min_green_fraction"]:
        program = copy.deepcopy(out.get("backyard_program"))
        created = program is None
        if created:
            program = {"min_green_fraction": None, "elements": []}
        present = {e["element"]: e for e in program["elements"]}
        for element, pref in yard["elements"].items():
            entry = present.get(element)
            if entry is None:
                if created or pref.get("add"):
                    program["elements"].append({"element": element, "priority": pref["priority"]})
                    applied.append({"kind": "backyard_element", "element": element, "priority": pref["priority"],
                                    "rule_id": pref["rule_id"]})
            elif entry.get("priority") is None:
                entry["priority"] = pref["priority"]
                applied.append({"kind": "backyard_priority", "element": element, "priority": pref["priority"],
                                "rule_id": pref["rule_id"]})
            else:
                overridden.append({"kind": "backyard_priority", "element": element, "rule_id": pref["rule_id"]})
        green = yard["min_green_fraction"]
        if green:
            if program.get("min_green_fraction") is None:
                program["min_green_fraction"] = green["value"]
                applied.append({"kind": "backyard_green", "value": green["value"], "rule_id": green["rule_id"]})
            else:
                overridden.append({"kind": "backyard_green", "rule_id": green["rule_id"]})
        if program["elements"]:
            out["backyard_program"] = program
    return out, {"applied": applied, "overridden_by_brief": overridden}
