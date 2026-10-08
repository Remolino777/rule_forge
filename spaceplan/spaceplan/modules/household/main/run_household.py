"""Workflow for step 6.5a: household -> needs per tier -> programs -> review, now and at the next stage.

    raw household (or archetype id) -> validate + archetype overlay + defaults
        -> bedroom grouping (required / preferred) -> facts -> household rules -> needs
        -> program per tier (required, preferred, desirable) -> CRC / catalog review
        -> advance by the horizon (aging + events) -> same chain -> growth delta

`resolve_brief_program` lets a brief carry a household block instead of (or besides) a program.
"""

from __future__ import annotations

import copy
from pathlib import Path

from spaceplan.core.lib.catalog import Catalog, load_catalog
from spaceplan.core.lib.enums import HOUSEHOLD_TIERS as TIERS
from spaceplan.core.lib.rules import CRC_RULESET, load_ruleset_resource
from spaceplan.modules.cost.main.run_cost import household_cost
from spaceplan.modules.household.lib.culture import merge_culture_into_brief
from spaceplan.modules.household.lib.household import (
    Household,
    advance,
    composition,
    load_household,
)
from spaceplan.modules.household.lib.household_catalog import (
    HouseholdCatalog,
    load_household_catalog,
)
from spaceplan.modules.household.lib.household_rules import (
    Derivation,
    active_anchor_overrides,
    active_backyard,
    active_hints,
    active_relation_overrides,
    active_weights,
    apply_rules,
)
from spaceplan.modules.household.lib.program_builder import program_from_needs
from spaceplan.modules.household.lib.program_review import review_program

PRIVACY_NOTE = ("Composition by age band only; member list and cultural profile are copied only when "
                "household.include_household is true. Bedroom grouping is design guidance, not an occupancy limit.")


def load_catalogs(catalog_path: str | Path | None = None,
                  household_catalog_path: str | Path | None = None) -> tuple[Catalog, HouseholdCatalog]:
    catalog = load_catalog(catalog_path)
    return catalog, load_household_catalog(household_catalog_path, residential=catalog)


def _review_summary(review: dict) -> dict:
    s = review["summary"]
    return {"buildable_as_stated": review["buildable_as_stated"], "counts": review["counts"],
            "net_area_sqft": s["net_area_sqft"], "gross_estimate_sqft": s["gross_estimate_sqft"],
            "findings": [f for f in review["findings"] if f["severity"] != "info"]}


def _stage(h: Household, hcat: HouseholdCatalog, catalog: Catalog, crc, dwelling_type: str) -> dict:
    derivation = apply_rules(hcat, catalog, h)
    needs = derivation.needs_list(catalog)
    gross = hcat.data["program_defaults"]["gross_factor"]
    programs, reviews = {}, {}
    for tier in TIERS:
        cars = 0 if dwelling_type == "apartment" else derivation.garage_cars[tier]
        program = program_from_needs(catalog, needs, tier, cars, hcat.tier(tier)["area_profile"],
                                     derivation.zone_factors[tier], gross, derivation.type_factors[tier])
        programs[tier] = program
        reviews[tier] = _review_summary(review_program(catalog, crc, program))
    return {"household": h, "derivation": derivation, "needs": needs, "programs": programs, "reviews": reviews}


def _public_stage(stage: dict, hcat: HouseholdCatalog, dwelling_type: str) -> dict:
    h: Household = stage["household"]
    d: Derivation = stage["derivation"]
    facts = dict(d.facts)
    dims = {k: facts[k] for k in ("social_life", "guests", "cooking", "vehicles", "pets", "shared_rooms_ok")}
    if h.include_household:
        dims["cultural_profile"] = h.cultural_profile
    else:
        facts.pop("cultural_profile")
    culture_rules = [t["rule_id"] for t in d.trace if t["layer"] == "culture"]
    out = {
        "stage_offset_years": h.stage_offset_years,
        "composition": composition(h, hcat),
        "dimensions": dims,
        "facts": facts,
        "bedrooms": {"required": [r.public() for r in d.grouping.required],
                     "preferred": [r.public() for r in d.grouping.preferred]},
        "needs": [n.to_dict() for n in stage["needs"]],
        "garage_cars": dict(d.garage_cars) if dwelling_type == "house" else dict.fromkeys(TIERS, 0),
        "driveway_vehicles": {t: max(0, h.vehicles - (d.garage_cars[t] if dwelling_type == "house" else 0))
                              for t in TIERS},
        "zone_factors": d.zone_factors,
        "relation_hints": {t: active_hints(d, t) for t in TIERS},
        "quality_weights": {t: active_weights(d, t) for t in TIERS},
        "programs": stage["programs"],
        "reviews": stage["reviews"],
        "rule_trace": d.trace,
        "rules_not_fired": d.not_fired,
        "culture": {
            "applied": bool(culture_rules),
            "aspects": dict(sorted(h.culture_aspects.items())),
            "kitchen_typology": d.kitchen_typology,
            "rule_ids": culture_rules,
            "type_factors": d.type_factors,
            "relation_overrides": {t: active_relation_overrides(d, t) for t in TIERS},
            "anchor_overrides": {t: active_anchor_overrides(d, t) for t in TIERS},
            "backyard": {t: active_backyard(d, t) for t in TIERS},
            "note": "Cultural aspects are client choices; tendencies are editable starting points, not a "
                    "characterization of any group.",
        },
    }
    if h.include_household:
        out["members"] = [{"member_id": m.member_id, "age_years": m.age_years, "mobility": m.mobility,
                           "works_from_home": m.works_from_home, "partner_id": m.partner_id} for m in h.members]
    return out


def household_stages(
    raw: dict,
    catalog_path: str | Path | None = None,
    household_catalog_path: str | Path | None = None,
    dwelling_type: str = "house",
) -> dict:
    """Internal stages (derivation and Need objects) now and at the horizon, for the profile generator."""
    catalog, hcat = load_catalogs(catalog_path, household_catalog_path)
    crc = load_ruleset_resource(*CRC_RULESET)
    household = load_household(raw, hcat)
    now = _stage(household, hcat, catalog, crc, dwelling_type)
    later_household, applied = advance(household, household.horizon_years, hcat)
    later = _stage(later_household, hcat, catalog, crc, dwelling_type)
    return {"catalog": catalog, "hcat": hcat, "household": household, "now": now, "later": later,
            "events_applied": applied}


def growth_delta(now: dict, later: dict, hcat: HouseholdCatalog,
                 tiers: tuple[str, ...] = ("required", "preferred")) -> dict:
    """What changes between stages: counts and ground-floor demands per tier, areas, and design notes."""
    def table(stage, tier):
        return {(n.space_type, n.household_role): (n.counts[tier], n.ground_counts[tier]) for n in stage["needs"]}

    changes = []
    for tier in tiers:
        a, b = table(now, tier), table(later, tier)
        for k in sorted(set(a) | set(b)):
            (ca, ga), (cb, gb) = a.get(k, (0, 0)), b.get(k, (0, 0))
            if (ca, ga) != (cb, gb):
                changes.append({"tier": tier, "space_type": k[0], "household_role": k[1], "now": ca, "next": cb,
                                "change": cb - ca, "ground_now": ga, "ground_next": gb})
    notes = []
    preferred = [c for c in changes if c["tier"] == "preferred"]
    bedroom_types = {t for types in hcat.data["bedroom_policy"]["room_space_types"].values() for t in types.values()}
    convertible = set(hcat.data["trajectory"]["convertible_space_types"])
    gained_rooms = sum(c["change"] for c in preferred if c["space_type"] in bedroom_types and c["change"] > 0)
    flex_now = sum(n.counts["preferred"] for n in now["needs"] if n.space_type in convertible)
    if gained_rooms and flex_now:
        notes.append(f"{gained_rooms} bedroom(s) needed next; {flex_now} flex room(s)/study now can be built "
                     f"as convertible bedrooms (closet and egress window) to absorb the change")
    if any(c["ground_next"] > c["ground_now"] for c in changes):
        notes.append("more spaces must be on the ground floor next (mobility): reserve them in the ground floor now")
    if any(c["tier"] == "required" and c["change"] > 0 and c["now"] == 0 for c in changes):
        notes.append("some spaces become indispensable next: the minimum program of today should leave room for them")
    ra, rb = now["reviews"]["preferred"], later["reviews"]["preferred"]
    return {"tiers": list(tiers), "changes": changes,
            "net_area_change_sqft": rb["net_area_sqft"] - ra["net_area_sqft"],
            "gross_area_change_sqft": rb["gross_estimate_sqft"] - ra["gross_estimate_sqft"],
            "notes": notes}


def derive_household(
    raw: dict,
    catalog_path: str | Path | None = None,
    household_catalog_path: str | Path | None = None,
    dwelling_type: str = "house",
    next_stage: bool = True,
    cost_model: str | None = None,
) -> dict:
    """Needs and programs for the current stage and (optionally) the next one, with growth delta and
    the relative cost index of every tier (reference-dwelling reading, step 6.5b)."""
    catalog, hcat = load_catalogs(catalog_path, household_catalog_path)
    crc = load_ruleset_resource(*CRC_RULESET)
    household = load_household(raw, hcat)
    now = _stage(household, hcat, catalog, crc, dwelling_type)
    result = {
        **hcat.tag(),
        "catalog_id": catalog.catalog_id,
        "catalog_version": catalog.version,
        "archetype_id": household.archetype_id,
        "dwelling_type": dwelling_type,
        "program_tier": household.program_tier or hcat.data["program_defaults"]["default_program_tier"],
        "privacy": PRIVACY_NOTE,
        **_public_stage(now, hcat, dwelling_type),
        "cost": household_cost(catalog, now, cost_model),
    }
    if next_stage:
        later_household, applied = advance(household, household.horizon_years, hcat)
        later = _stage(later_household, hcat, catalog, crc, dwelling_type)
        result["next_stage"] = {"horizon_years": household.horizon_years, "events_applied": applied,
                                **_public_stage(later, hcat, dwelling_type),
                                "cost": household_cost(catalog, later, cost_model),
                                "growth_delta": growth_delta(now, later, hcat)}
    return result


def _program_comparison(given: dict, derived: dict, given_review: dict, derived_review: dict) -> dict:
    def rooms(p):
        return sum(s.get("space_type") in ("bedroom", "primary_suite") for s in p["spaces"])

    def wet(p):
        return sum(s["wet"] and s["zone"] in ("private", "circulation") for s in p["spaces"])

    return {"brief_net_sqft": given_review["summary"]["net_area_sqft"],
            "derived_net_sqft": derived_review["net_area_sqft"],
            "brief_bedrooms": rooms(given), "derived_bedrooms": rooms(derived),
            "brief_bathrooms": wet(given), "derived_bathrooms": wet(derived),
            "brief_garage_cars": given["garage_cars"], "derived_garage_cars": derived["garage_cars"]}


def resolve_brief_program(
    brief: dict,
    catalog_path: str | Path | None = None,
    household_catalog_path: str | Path | None = None,
) -> tuple[dict, dict | None]:
    """(brief with a program, household package block or None); see resolve_brief_household."""
    resolved, block, _ = resolve_brief_household(brief, catalog_path, household_catalog_path)
    return resolved, block


def resolve_brief_household(
    brief: dict,
    catalog_path: str | Path | None = None,
    household_catalog_path: str | Path | None = None,
) -> tuple[dict, dict | None, dict | None]:
    """(brief with a program, household package block or None, tier programs or None).

    Without 'household' the brief is returned untouched. With 'household' and no 'program' the program of
    the household tier (default: catalog default) is derived; with both, the brief program wins and the
    block records the comparison.
    """
    if "household" not in brief:
        return brief, None, None
    result = derive_household(brief["household"], catalog_path, household_catalog_path,
                              brief.get("dwelling_type", "house"), next_stage=False)
    tier = result["program_tier"]
    derived = result["programs"][tier]
    resolved = copy.deepcopy(brief)
    block = {
        "household_catalog_id": result["household_catalog_id"],
        "household_catalog_version": result["household_catalog_version"],
        "household_catalog_sha256": result["household_catalog_sha256"],
        "archetype_id": result["archetype_id"],
        "program_tier": tier,
        "program_source": "brief" if "program" in brief else "derived",
        "composition": result["composition"],
        "needs": result["needs"],
        "garage_cars": result["garage_cars"],
        "driveway_vehicles": result["driveway_vehicles"][tier],
        "relation_hints": result["relation_hints"][tier],
        "quality_weights": result["quality_weights"][tier],
        "rule_trace": [{"rule_id": t["rule_id"], "status": t["source"]["status"]} for t in result["rule_trace"]],
        "privacy": PRIVACY_NOTE,
    }
    if "members" in result:
        block["members"] = result["members"]
    culture = result["culture"]
    if culture["applied"]:
        tier_culture = {"relation_overrides": culture["relation_overrides"][tier],
                        "anchor_overrides": culture["anchor_overrides"][tier], "backyard": culture["backyard"][tier]}
        resolved, record = merge_culture_into_brief(resolved, tier_culture)
        block["culture"] = {"applied": True, "kitchen_typology": culture["kitchen_typology"],
                            "rule_ids": culture["rule_ids"], **record, "note": culture["note"]}
        if result["dimensions"].get("cultural_profile") is not None:
            block["culture"]["profile"] = result["dimensions"]["cultural_profile"]
    else:
        block["culture"] = {"applied": False}
    if "program" in brief:
        catalog = load_catalog(catalog_path)
        given_review = review_program(catalog, load_ruleset_resource(*CRC_RULESET), brief["program"])
        block["program_comparison"] = _program_comparison(brief["program"], derived, given_review,
                                                          result["reviews"][tier])
    else:
        resolved["program"] = derived
    return resolved, block, result["programs"]
