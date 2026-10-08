"""Markdown parameter table with sources (step 3 deliverable: 'tabla de parametros con fuente')."""

from __future__ import annotations

from spaceplan.core.lib.catalog import Catalog
from spaceplan.modules.household.lib.program_builder import expand_typology
from spaceplan.core.lib.rules import RuleSet


def _fmt(value) -> str:
    return "—" if value is None else f"{value:g}" if isinstance(value, (int, float)) else str(value)


def render_parameter_table(catalog: Catalog, crc: RuleSet, garage_cars: int = 2) -> str:
    src = catalog.data["default_source"]
    lines = [
        f"# spaceplan parameter table — {catalog.catalog_id} v{catalog.version}",
        "",
        f"Catalog SHA-256 `{catalog.sha256}`. Default source: {src['citation']} "
        f"(status **{src['status']}**). CRC ruleset `{crc.ruleset_id}` v{crc.version}.",
        "",
        "## Scales",
        "",
        "| Scale | Area min | Area max | Facade | Topology | Placement order |",
        "|---|---|---|---|---|---|",
    ]
    for s in catalog.data["scales"]:
        lines.append(f"| {s['scale']} | {_fmt(s['area_min'])} | {_fmt(s['area_max'])} | {s['facade']} | "
                     f"{s['topology']} | {_fmt(s['placement_order'])} |")
    lines += ["", "## Zones", "", "| Zone | Dominant scale | Floor | Sun | Morning light | Street privacy | Content |",
              "|---|---|---|---|---|---|---|"]
    for z in catalog.data["zones"]:
        o = z["orientation"]
        lines.append(f"| {z['zone']} | {z['dominant_scale']} | {z['floor_preference']} ({z['floor_rule']}) | "
                     f"{o['sun']:g} | {o['morning_light']:g} | {o['street_privacy']:g} | {z['content']} |")
    lines += ["", "## Space types (sq ft)", "",
              "| Space type | Zone | Scale | Habitable | Wet | Min | Target | Max | Hosts | Scale exception | Status |",
              "|---|---|---|---|---|---|---|---|---|---|---|"]
    for t in catalog.data["space_types"]:
        a = t["area"]
        lines.append(
            f"| {t['space_type']} | {t['zone']} | {t['scale']} | {'yes' if t['habitable'] else 'no'} | "
            f"{'yes' if t['wet'] else 'no'} | {a['min']:g} | {a['target']:g} | {a['max']:g} | "
            f"{', '.join(t.get('host_types', [])) or '—'} | {t.get('scale_range_exception', '—')} | "
            f"{catalog.source_of(t)['status']} |"
        )
    lines += ["", "## Profiles (target multipliers by zone)", "",
              "| Profile | " + " | ".join(catalog.data["profiles"]["balanced"]) + " |",
              "|---|" + "---|" * len(catalog.data["profiles"]["balanced"])]
    for name, mult in catalog.data["profiles"].items():
        lines.append(f"| {name} | " + " | ".join(f"{v:g}" for v in mult.values()) + " |")
    lines += ["", f"## Typologies (garage for {garage_cars} cars, balanced profile)", "",
              "| Typology | Dwelling | Label | Spaces | Net min | Net target | Net max | Gross factor | Gross estimate |",
              "|---|---|---|---|---|---|---|---|---|"]
    for typ in catalog.data["typologies"]:
        cars = garage_cars if typ["dwelling_type"] == "house" else 0
        program = expand_typology(catalog, typ["typology_id"], cars)
        net_min = sum(s["min_area_sqft"] for s in program["spaces"])
        net_target = sum(s["target_area_sqft"] for s in program["spaces"])
        net_max = sum(catalog.space_type(s["space_type"])["area"]["max"] for s in program["spaces"])
        lines.append(f"| {typ['typology_id']} | {typ['dwelling_type']} | {typ['label']} | {len(program['spaces'])} | {net_min:g} | "
                     f"{net_target:g} | {net_max:g} | {typ['gross_factor']:g} | {net_target * typ['gross_factor']:.0f} |")
    lines += ["", "## Zone parts (zones split by their spaces)", "",
              "| Zone | Scheme | Dwelling | Part | Space types | Min width ft |", "|---|---|---|---|---|---|"]
    for zone, rule in catalog.data["zone_parts"].items():
        for scheme in rule["schemes"]:
            for part in scheme["parts"]:
                lines.append(f"| {zone} | {scheme['scheme_id']} | {', '.join(scheme['dwelling_types'])} | {part['part']} | "
                             f"{', '.join(part['space_types'])} | {part['min_width_ft']:g} |")
    rm = catalog.data["relation_matrix"]
    lines += ["", "## Space relation matrix (D direct, I indirect, absent = N)", "",
              "Roles: " + "; ".join(f"**{r}** = {', '.join(t)}" for r, t in rm["roles"].items()), "",
              "| Dwelling | A | B | Type | Kind | Weight | Source |", "|---|---|---|---|---|---|---|"]
    for dwelling in ("house", "apartment"):
        for pr in rm[dwelling]:
            lines.append(f"| {dwelling} | {pr['a']} | {pr['b']} | {pr['type']} | {pr['kind']} | {pr['weight']:g} | "
                         f"{pr['source']['citation']} |")
        for g in rm["hard_groups"][dwelling]:
            lines.append(f"| {dwelling} | group {g['group_id']} | at least {g['k']} of {', '.join(g['pairs'])} | D | hard | — | "
                         f"{g['source']['citation']} |")
    lines += ["", "Semantics: " + "; ".join(f"{k}: {v}" for k, v in rm["semantics"].items())]
    circ = catalog.data["circulation"]
    lines += ["", "## Circulation network", "",
              f"Design width {circ['design_width_ft']:g} ft (normative minimum: rule {circ['normative_width']['rule_id']}); "
              f"door contact {circ['door_contact_ft']:g} ft; target {circ['target_fraction']:.0%} of the footprint, warning above "
              f"{circ['warn_fraction']:.0%}; derived (replaced by the network): {', '.join(circ['derived_space_types'])}; "
              f"private roles open only onto circulation: {', '.join(circ['private_roles'])}.", "",
              "| Space type | Passable | Min side ft |", "|---|---|---|"]
    for t in catalog.data["space_types"]:
        lines.append(f"| {t['space_type']} | {'yes' if t['passable'] else 'no'} | {t['min_side_ft']:g} |")
    lines += ["", "## Zoning profiles by dwelling type", "", "| Dwelling | Rule | Kind | Target | Facade role / sequence | Min contact ft | Source |",
              "|---|---|---|---|---|---|---|"]
    for dwelling, prof in catalog.data["zoning_profiles"].items():
        e = prof["entry"]
        lines.append(f"| {dwelling} | entry | hard | {e['zone']} | on {e['interval']} | {e['min_overlap_ft']:g} | catalog |")
        for a in prof["anchors"]:
            lines.append(f"| {dwelling} | {a['anchor_id']} | {a['kind']} | {', '.join(a['space_types'])} | {a['facade_role']} | "
                         f"{a['min_contact_ft']:g} | {a['source']['citation']} |")
        seq = prof["entry_sequence"]
        if seq:
            lines.append(f"| {dwelling} | {seq['anchor_id']} | {seq['kind']} | {seq['target_zone']} | entrance -> {seq['via_zone']} -> "
                         f"{seq['target_zone']} (never on the entrance) | — | {seq['source']['citation']} |")
    pol = catalog.data["backyard_policy"]
    lines += ["", f"## Backyard elements (minimum green {pol['min_green_fraction']:.0%} of the yard reserved first)", "",
              "| Element | Priority | Min | Target | Max | Min dim ft | Placement | Group | Requires | Clearances |",
              "|---|---|---|---|---|---|---|---|---|---|"]
    for el in catalog.data["backyard_elements"]:
        a = el["area"]
        gaps = ", ".join(f"{k}: {v['rule_id']}.{v['param']}" for k, v in el["clearances"].items()) or "—"
        lines.append(f"| {el['element']} | {el['priority']} | {a['min']:g} | {a['target']:g} | {a['max']:g} | {el['min_dim_ft']:g} | "
                     f"{el['placement']} | {el['group'] or '—'} | {', '.join(el['requires']) or '—'} | {gaps} |")
    lines += ["", "## Normative minima used by the review (CRC 2025)", "",
              "| Rule | Magnitude | Value | Unit | Status | Source |", "|---|---|---|---|---|---|"]
    for r in crc.data["rules"]:
        lines.append(f"| {r['rule_id']} | {r['magnitude']} | {r['operator']} {_fmt(r['value'])} | {r['unit']} | "
                     f"{crc.status(r['rule_id'])} | {crc.source_tag(r['rule_id'])} |")
    return "\n".join(lines) + "\n"


def _predicate_text(p: dict) -> str:
    if "always" in p:
        return "always"
    if "all" in p:
        return " and ".join(_predicate_text(x) for x in p["all"])
    if "any" in p:
        return "(" + " or ".join(_predicate_text(x) for x in p["any"]) + ")"
    if "not" in p:
        return f"not ({_predicate_text(p['not'])})"
    return f"{p['fact']} {p['op']} {p['value']}"


def _effect_text(e: dict) -> str:
    tiers = "/".join(t[0].upper() for t in e["tiers"])
    if e["effect"] == "space":
        count = e["count"] if not isinstance(e["count"], dict) else (
            e["count"]["fact"] + "".join(f" {k}={v}" for k, v in e["count"].items() if k != "fact"))
        role = "" if e["household_role"] == "general" else f":{e['household_role']}"
        return f"{e['space_type']}{role} x {count} [{tiers}]" + (" ground" if e.get("ground_floor") else "")
    if e["effect"] == "area_factor":
        return f"{e['zone']} area x{e['factor']:g} [{tiers}]"
    if e["effect"] == "garage_cars":
        return f"garage cars {e['count']} [{tiers}]"
    if e["effect"] == "relation_hint":
        return f"{e['a']} {e['relation']} {e['b']} [{tiers}]"
    if e["effect"] == "type_area_factor":
        return f"{e['space_type']} area x{e['factor']:g} [{tiers}]"
    if e["effect"] == "relation_override":
        extra = f" {e['kind']} w{e['weight']:g}" if e["type"] != "N" else ""
        return f"matrix {e['a']}-{e['b']} {e['type']}{extra} [{tiers}]"
    if e["effect"] == "anchor_override":
        return f"anchor {e['anchor_id']} {e['mode']} [{tiers}]"
    if e["effect"] == "backyard_element":
        return f"backyard {e['element']} #{e['priority']}" + (" (add)" if e.get("add") else "") + f" [{tiers}]"
    if e["effect"] == "backyard_green":
        return f"backyard green >= {e['min_green_fraction']:.0%} [{tiers}]"
    return f"weight {e['criterion']} x{e['weight']:g} [{tiers}]"


def render_household_table(hcat) -> str:
    """Markdown table of the household rules and archetypes (for the report)."""
    lines = [f"# Household rules — {hcat.catalog_id} {hcat.version}", "",
             "Tiers: R = required (minimum), P = preferred, D = desirable. Every value is a design hypothesis "
             "with its status; none is an occupancy limit.", "",
             "| Rule | Layer | When | Effects | Status | Source |", "|---|---|---|---|---|---|"]
    for r in hcat.data["rules"]:
        src = hcat.source_of(r)
        lines.append(f"| {r['rule_id']} | {r['layer']} | {_predicate_text(r['when'])} | "
                     f"{'; '.join(_effect_text(e) for e in r['effects'])} | {src['status']} | {src['citation']} |")
    lines += ["", "## Cultural layer (6.5c)", "",
              "A profile is only a preset of explicit aspects the client sees and edits; culture rules read the "
              "aspects, never the label. Without a profile or aspects, no culture rule fires.", "",
              "| Aspect | Values | " + " | ".join(p["label"] for p in hcat.data["culture_presets"][:2]) + " | Effect |",
              "|---|---|---|---|---|"]
    presets = hcat.data["culture_presets"][:2]
    for a in hcat.data["culture_aspects"]:
        lines.append(f"| {a['aspect']} | {', '.join(a['values'])} | "
                     + " | ".join(p["aspects"].get(a["aspect"], "-") for p in presets) + f" | {a['effect']} |")
    lines += ["", "| Kitchen typology | Effects |", "|---|---|"]
    lines += [f"| {t['typology_id']} ({t['label']}) | {'; '.join(_effect_text(e) for e in t['effects'])} |"
              for t in hcat.data["kitchen_typologies"]]
    lines += ["", "Selection (first match; an explicit client choice wins):", ""]
    lines += [f"{i + 1}. {_predicate_text(sel['when'])} -> {sel['typology']}"
              for i, sel in enumerate(hcat.data["kitchen_typology_selection"])]
    lines += ["", "## Reference archetypes", "", "| Archetype | Members (age) | Dimensions | Trajectory |",
              "|---|---|---|---|"]
    for a in hcat.data["archetypes"]:
        h = a["household"]
        members = ", ".join(f"{m['age_years']}" + (" (WFH)" if m.get("works_from_home") else "")
                            + (f" ({m['mobility']})" if m.get("mobility", "full") != "full" else "") for m in h["members"])
        dims = ", ".join(f"{k}={h[k]}" for k in ("social_life", "guests", "cooking", "vehicles", "pets") if k in h)
        events = ", ".join(f"{e['event']} in {e['in_years']} y" for e in h.get("trajectory", {}).get("events", [])) or "-"
        lines.append(f"| {a['label']} | {members} | {dims} | {events} |")
    return "\n".join(lines) + "\n"


def render_cost_table(catalog) -> str:
    """Markdown table of the relative cost parameters (step 6.5b): ranges, references, budget levels."""
    ci = catalog.data["cost_index"]
    src = ci["source"]
    lines = [f"# Relative cost index — {catalog.catalog_id} {catalog.version}", "", ci["note"], "",
             f"Status: {src['status']}. Source: {src['citation']}.", "",
             "| Parameter | Kind | Min | Most likely | Max |", "|---|---|---|---|---|"]
    for group, kind in (("coefficients", "area class coefficient"), ("form_factors", "form factor")):
        for name, r in ci[group].items():
            lines.append(f"| {name} | {kind} | {r['min']:g} | {r['mode']:g} | {r['max']:g} |")
    lines += ["", "| Reference mix class | Fraction |", "|---|---|"]
    lines += [f"| {k} | {v:g} |" for k, v in ci["reference_mix"].items()]
    lines += ["", f"Reference dwelling: {ci['reference_dwelling_gross_sqft']:g} sq ft gross; hillside factor from mean "
              f"slope {ci['hillside_mean_slope_threshold']:g}.", "", "| Budget level | Fraction of the lot maximum |",
              "|---|---|"]
    lines += [f"| {k} | {v:g} |" for k, v in ci["budget_levels"].items()]
    return "\n".join(lines) + "\n"
