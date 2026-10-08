"""Household rules -> needs per tier (step 6.5a).

Layers apply in a fixed order: bedroom policy, household rules, then (6.5c) culture rules. The
composition is deterministic and order-free:

* space counts per (space_type, household_role) and tier: maximum over the rules that set them;
* ground-floor counts: maximum, never above the count of the same tier;
* zone and space-type area factors: product of every factor that applies to the tier;
* culture layer (6.5c, after the household layer): kitchen typology first, then culture rules; relation
  overrides (highest weight per role pair), anchor overrides (strongest mode), backyard priorities
  (lowest number) and green reserve (largest). Culture only adds or raises: counts are maxima, so a
  space required by the household is never removed;
* garage cars: maximum, capped by the largest garage the residential catalog knows;
* relation hints and quality weights are recorded for later steps (6.7, 6.8) with their rule id.

Every fired rule leaves a trace entry with its realized effects, source and status.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from spaceplan.core.lib.catalog import Catalog
from spaceplan.core.lib.enums import HOUSEHOLD_TIERS as TIERS
from spaceplan.modules.household.lib.household import Grouping, Household, bedrooms, household_facts
from spaceplan.modules.household.lib.household_catalog import HouseholdCatalog
from spaceplan.core.lib_aux.predicates import evaluate, evaluate_number

BEDROOM_RULE = "BEDROOM-POLICY"
NO_TYPOLOGY = "none"


@dataclass
class Need:
    space_type: str
    household_role: str
    counts: dict[str, int] = field(default_factory=lambda: dict.fromkeys(TIERS, 0))
    ground_counts: dict[str, int] = field(default_factory=lambda: dict.fromkeys(TIERS, 0))
    rule_ids: list[str] = field(default_factory=list)

    @property
    def key(self) -> tuple[str, str]:
        return self.space_type, self.household_role

    def to_dict(self) -> dict:
        return {"space_type": self.space_type, "household_role": self.household_role, "counts": dict(self.counts),
                "ground_floor_counts": dict(self.ground_counts), "rule_ids": list(self.rule_ids)}


@dataclass
class Derivation:
    facts: dict[str, Any]
    grouping: Grouping
    needs: dict[tuple[str, str], Need]
    zone_factors: dict[str, dict[str, float]]
    garage_cars: dict[str, int]
    relation_hints: list[dict]
    quality_weights: list[dict]
    trace: list[dict]
    not_fired: list[str]
    type_factors: dict[str, dict[str, float]] = field(default_factory=dict)
    kitchen_typology: str = "none"
    relation_overrides: list[dict] = field(default_factory=list)
    anchor_overrides: list[dict] = field(default_factory=list)
    backyard_elements: list[dict] = field(default_factory=list)
    backyard_green: list[dict] = field(default_factory=list)

    def needs_list(self, catalog: Catalog) -> list[Need]:
        order = {t["space_type"]: i for i, t in enumerate(catalog.data["space_types"])}
        return sorted(self.needs.values(), key=lambda n: (order.get(n.space_type, len(order)), n.household_role))


def _need(needs: dict, space_type: str, role: str) -> Need:
    return needs.setdefault((space_type, role), Need(space_type, role))


def _bedroom_needs(hcat: HouseholdCatalog, grouping: Grouping, needs: dict) -> dict:
    policy = hcat.data["bedroom_policy"]
    types = policy["room_space_types"]
    ground_tiers = policy["accessible_ground_floor_tiers"]
    realized = []
    for tier in TIERS:
        per_key: dict[tuple[str, str], list[int]] = {}
        for room in grouping.for_tier(tier):
            space_type = types.get(room.role, types["default"])[tier]
            slot = per_key.setdefault((space_type, room.role), [0, 0])
            slot[0] += 1
            slot[1] += room.accessibility in ground_tiers and tier in ground_tiers[room.accessibility]
        for (space_type, role), (count, ground) in sorted(per_key.items()):
            need = _need(needs, space_type, role)
            need.counts[tier] = max(need.counts[tier], count)
            need.ground_counts[tier] = max(need.ground_counts[tier], ground)
            if BEDROOM_RULE not in need.rule_ids:
                need.rule_ids.append(BEDROOM_RULE)
            realized.append({"tier": tier, "space_type": space_type, "household_role": role, "count": count,
                             "ground_floor": ground})
    return {"rule_id": BEDROOM_RULE, "layer": "household",
            "description": "Bedroom grouping: partners share, own-room bands, children share by tier policy",
            "effects": realized, "source": hcat.source_of(policy)}


def _cap_cars(catalog: Catalog) -> int:
    return max(int(k) for k, v in catalog.data["garage_by_cars"].items() if v is not None)


@dataclass
class _State:
    needs: dict
    zone_factors: dict
    type_factors: dict
    garage: dict
    hints: list
    weights: list
    relation_overrides: list
    anchor_overrides: list
    backyard_elements: list
    backyard_green: list


def _apply_effect(effect: dict, rule_id: str, facts: dict, st: _State, cap: int) -> dict:
    """Apply one effect to the state; returns the realized effect for the trace."""
    kind, tiers = effect["effect"], effect["tiers"]
    if kind == "space":
        count = max(0, int(evaluate_number(effect["count"], facts)))
        need = _need(st.needs, effect["space_type"], effect["household_role"])
        for tier in tiers:
            need.counts[tier] = max(need.counts[tier], count)
            if effect.get("ground_floor"):
                need.ground_counts[tier] = max(need.ground_counts[tier], count)
        if count and rule_id not in need.rule_ids:
            need.rule_ids.append(rule_id)
        return {**effect, "count": count}
    if kind == "area_factor":
        for tier in tiers:
            st.zone_factors[tier][effect["zone"]] = st.zone_factors[tier].get(effect["zone"], 1.0) * effect["factor"]
    elif kind == "type_area_factor":
        for tier in tiers:
            key = effect["space_type"]
            st.type_factors[tier][key] = st.type_factors[tier].get(key, 1.0) * effect["factor"]
    elif kind == "garage_cars":
        cars = min(cap, max(0, int(evaluate_number(effect["count"], facts))))
        for tier in tiers:
            st.garage[tier] = max(st.garage[tier], cars)
        return {**effect, "count": cars}
    elif kind == "relation_hint":
        st.hints.append({**{k: effect[k] for k in ("a", "b", "relation", "tiers")}, "rule_id": rule_id})
    elif kind == "quality_weight":
        st.weights.append({**{k: effect[k] for k in ("criterion", "weight", "tiers")}, "rule_id": rule_id})
    elif kind == "relation_override":
        st.relation_overrides.append({**effect, "rule_id": rule_id})
    elif kind == "anchor_override":
        st.anchor_overrides.append({**effect, "rule_id": rule_id})
    elif kind == "backyard_element":
        st.backyard_elements.append({**effect, "rule_id": rule_id})
    elif kind == "backyard_green":
        st.backyard_green.append({**effect, "rule_id": rule_id})
    return dict(effect)


def select_kitchen_typology(hcat: HouseholdCatalog, household: Household, facts: dict) -> tuple[str, str]:
    """(typology, why): the client's explicit choice, else the first selection rule that holds, else none."""
    if household.kitchen_typology:
        return household.kitchen_typology, "client choice"
    for i, sel in enumerate(hcat.data["kitchen_typology_selection"]):
        if evaluate(sel["when"], facts):
            return sel["typology"], f"kitchen_typology_selection[{i}]"
    return NO_TYPOLOGY, "no cultural aspect selects a typology"


def apply_rules(hcat: HouseholdCatalog, catalog: Catalog, household: Household,
                layers: tuple[str, ...] = ("household", "culture")) -> Derivation:
    grouping = bedrooms(household, hcat)
    facts = household_facts(household, hcat, grouping)
    st = _State(needs={}, zone_factors={t: {} for t in TIERS}, type_factors={t: {} for t in TIERS},
                garage=dict.fromkeys(TIERS, 0), hints=[], weights=[], relation_overrides=[], anchor_overrides=[],
                backyard_elements=[], backyard_green=[])
    trace = [_bedroom_needs(hcat, grouping, st.needs)]
    cap = _cap_cars(catalog)
    not_fired = []
    typology, why = select_kitchen_typology(hcat, household, facts) if "culture" in layers else (NO_TYPOLOGY, "")
    facts["kitchen_typology"] = typology
    for layer in layers:
        if layer == "culture" and typology != NO_TYPOLOGY:
            kt = hcat.kitchen_typology(typology)
            rid = f"KT-{typology.upper().replace('_', '-')}"
            realized = [_apply_effect(e, rid, facts, st, cap) for e in kt["effects"]]
            trace.append({"rule_id": rid, "layer": "culture", "description": f"Kitchen typology: {kt['label']} ({why})",
                          "effects": realized, "source": hcat.data["culture_presets"][0]["source"]})
        for rule in hcat.rules(layer):
            if not evaluate(rule["when"], facts):
                not_fired.append(rule["rule_id"])
                continue
            realized = [_apply_effect(e, rule["rule_id"], facts, st, cap) for e in rule["effects"]]
            trace.append({"rule_id": rule["rule_id"], "layer": layer, "description": rule["description"],
                          "effects": realized, "source": hcat.source_of(rule)})
    for need in st.needs.values():
        for tier in TIERS:
            need.ground_counts[tier] = min(need.ground_counts[tier], need.counts[tier])
    return Derivation(facts, grouping, st.needs, st.zone_factors, st.garage, st.hints, st.weights, trace, not_fired,
                      st.type_factors, typology, st.relation_overrides, st.anchor_overrides, st.backyard_elements,
                      st.backyard_green)


# ------------------------------------------------------------------------- culture outputs per tier

ANCHOR_RANK = {"off": 0, "soft": 1, "hard": 2}


def active_relation_overrides(derivation: Derivation, tier: str) -> list[dict]:
    """One override per unordered role pair: highest weight wins (N counts as 0), ties by rule id."""
    best: dict[frozenset, dict] = {}
    for o in derivation.relation_overrides:
        if tier not in o["tiers"]:
            continue
        key = frozenset((o["a"], o["b"]))
        rank = (o.get("weight", 0.0), o["rule_id"])
        if key not in best or rank >= (best[key].get("weight", 0.0), best[key]["rule_id"]):
            best[key] = o
    out = []
    for o in sorted(best.values(), key=lambda o: (o["a"], o["b"])):
        entry = {"a": o["a"], "b": o["b"], "type": o["type"], "rule_id": o["rule_id"]}
        if o["type"] != "N":
            entry.update(kind=o["kind"], weight=o["weight"])
        out.append(entry)
    return out


def active_anchor_overrides(derivation: Derivation, tier: str) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for o in derivation.anchor_overrides:
        if tier in o["tiers"] and (o["anchor_id"] not in out or ANCHOR_RANK[o["mode"]] > ANCHOR_RANK[out[o["anchor_id"]]["mode"]]):
            out[o["anchor_id"]] = {"mode": o["mode"], "rule_id": o["rule_id"]}
    return dict(sorted(out.items()))


def active_backyard(derivation: Derivation, tier: str) -> dict:
    """Culture backyard preferences: element priorities (lowest number wins) and the green reserve (largest)."""
    elements: dict[str, dict] = {}
    for e in derivation.backyard_elements:
        if tier in e["tiers"] and (e["element"] not in elements or e["priority"] < elements[e["element"]]["priority"]):
            elements[e["element"]] = {"priority": e["priority"], "rule_id": e["rule_id"], "add": e.get("add", False)}
    greens = [g for g in derivation.backyard_green if tier in g["tiers"]]
    green = max(greens, key=lambda g: g["min_green_fraction"]) if greens else None
    return {"elements": dict(sorted(elements.items())),
            "min_green_fraction": None if green is None else {"value": green["min_green_fraction"],
                                                              "rule_id": green["rule_id"]}}


def active_hints(derivation: Derivation, tier: str) -> list[dict]:
    """Relation hints of a tier, one per (a, b, relation), with every rule that asked for it."""
    merged: dict[tuple[str, str, str], dict] = {}
    for h in derivation.relation_hints:
        if tier in h["tiers"]:
            entry = merged.setdefault((h["a"], h["b"], h["relation"]),
                                      {"a": h["a"], "b": h["b"], "relation": h["relation"], "rule_ids": []})
            entry["rule_ids"].append(h["rule_id"])
    return [merged[k] for k in sorted(merged)]


def active_weights(derivation: Derivation, tier: str) -> dict[str, float]:
    out: dict[str, float] = {}
    for w in derivation.quality_weights:
        if tier in w["tiers"]:
            out[w["criterion"]] = max(out.get(w["criterion"], 0.0), w["weight"])
    return out
