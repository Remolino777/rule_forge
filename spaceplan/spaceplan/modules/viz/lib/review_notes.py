"""Review observations of a zoned scheme (step 6.5d): what a designer should look at first.

Each observation is a code with parameters; the text comes from catalog `display.review_notes[lang]`.
Checks (necessary-condition style, cheap):

    weak_patio_link       a D pair with the patio holds only through a hall or an open neighbour, the role's own
                          spaces have no door to the patio
    private_through_social a private hall or room opens directly onto a social/kitchen room
    patio_door_private    a bedroom or closet has its own door to the patio
    kitchen_no_garden     the kitchen does not reach the garden facade
    suite_no_garden       the primary suite has no garden facade while its bath or closet do
    below_target          achieved net area below the program target (above the minimum)
    below_minimum         achieved net area below the program minimum
    circulation_high      circulation fraction above the catalog target
    garden_short          garden area below the brief preference
    backyard_excluded     a requested backyard element was left out (reason)
    satellites            support spaces folded into a host (not drawn)
    passed                hard relations and site checks that hold (summary line)
"""

from __future__ import annotations

ROOMS_SOCIAL = ("social", "kitchen")


def _touches_rear(rect: list[float], footprint: list[float]) -> bool:
    return abs(rect[3] - footprint[3]) < 1e-6


def scheme_observations(package: dict, program: dict, option_id: str = "n1", rank: int = 1) -> list[dict]:
    zoning = next(o for o in package["zoning"]["options"] if o["option_id"] == option_id)
    scheme = next(s for s in zoning["schemes"] if s["rank"] == rank)
    site = next(o for o in package["site_partition"]["options"] if o["option_id"] == option_id)
    spaces = scheme["spaces"]
    targets = {s["space_id"]: s for s in program["spaces"]}
    doors = scheme["doors"]
    obs: list[dict] = []

    satisfied_hard = [m["pair"] for m in scheme.get("matrix", []) if m["kind"] == "hard" and m["applicable"]
                      and m["satisfied"] and not m["pair"].startswith("group:")]
    checks = {c["check_id"]: c for c in site.get("checks", [])}
    normative_ok = all(c["passes"] for c in site.get("checks", []) if c["kind"] == "normative")
    paving = checks.get("front_paving_fraction")
    obs.append({"code": "passed", "severity": "ok", "hard_pairs": len(satisfied_hard),
                "site_normative_ok": normative_ok, "paving": None if paving is None else paving["value"],
                "paving_limit": None if paving is None else paving["limit"]})

    patio_doors = {d["a"] for d in doors if d["b"] == "@patio"} | {d["b"] for d in doors if d["a"] == "@patio"}
    roles_spaces: dict[str, list[str]] = {}
    for sid, sp in spaces.items():
        for r in sp.get("roles", []):
            roles_spaces.setdefault(r, []).append(sid)
    for m in scheme.get("matrix", []):
        if m["type"] != "D" or not m["satisfied"] or not m["applicable"] or m["pair"].startswith("group:"):
            continue
        a, b = m["pair"][2:].split("-", 1)
        if b != "patio":
            continue
        own = roles_spaces.get(a, [])
        if own and not any(sid in patio_doors for sid in own):
            obs.append({"code": "weak_patio_link", "severity": "review", "role": a, "spaces": own,
                        "weight": m["weight"]})

    for d in doors:
        if d["kind"] != "open":
            continue
        for x, y in ((d["a"], d["b"]), (d["b"], d["a"])):
            hall_private = x.startswith("hall_private")
            room_private = x in spaces and spaces[x]["zone"] == "private"
            if (hall_private or room_private) and y in spaces and spaces[y]["zone"] in ROOMS_SOCIAL:
                obs.append({"code": "private_through_social", "severity": "review", "via": y, "private": x})

    for sid in sorted(patio_doors):
        sp = spaces.get(sid)
        if sp and sp["zone"] == "private" and sp["space_type"] in ("walk_in_closet", "closet", "bedroom", "primary_suite"):
            obs.append({"code": "patio_door_private", "severity": "review", "space": sid})

    fp = scheme["footprint_local"]
    kitchen = [sid for sid, sp in spaces.items() if sp["space_type"] == "kitchen"]
    if kitchen and not any(_touches_rear(spaces[k]["rect_local"], fp) for k in kitchen):
        blocker = [sid for sid, sp in spaces.items() if _touches_rear(sp["rect_local"], fp)
                   and sp["rect_local"][0] < spaces[kitchen[0]]["rect_local"][2]
                   and sp["rect_local"][2] > spaces[kitchen[0]]["rect_local"][0]]
        obs.append({"code": "kitchen_no_garden", "severity": "review", "blocked_by": blocker})
    suite = [sid for sid, sp in spaces.items() if sp["space_type"] == "primary_suite"]
    if suite and not _touches_rear(spaces[suite[0]]["rect_local"], fp):
        taken = [sid for sid, sp in spaces.items() if sp["space_type"] in ("primary_bath", "walk_in_closet")
                 and _touches_rear(sp["rect_local"], fp)]
        if taken:
            obs.append({"code": "suite_no_garden", "severity": "review", "taken_by": taken})

    for sid, sp in spaces.items():
        t = targets.get(sid)
        if not t:
            continue
        got = sp["net_area_sqft"]
        if got < t["min_area_sqft"] - 0.5:
            obs.append({"code": "below_minimum", "severity": "issue", "space": sid, "achieved": got,
                        "minimum": t["min_area_sqft"]})
        elif got < t["target_area_sqft"] * 0.9:
            obs.append({"code": "below_target", "severity": "review", "space": sid, "achieved": got,
                        "target": t["target_area_sqft"]})

    circ = scheme.get("circulation") or {}
    if circ.get("fraction") is not None and circ["fraction"] > circ.get("target_fraction", 1):
        obs.append({"code": "circulation_high", "severity": "review", "fraction": circ["fraction"],
                    "target": circ["target_fraction"]})
    garden = checks.get("garden_area")
    if garden and garden["value"] is not None and garden["limit"] and garden["value"] < garden["limit"]:
        obs.append({"code": "garden_short", "severity": "review", "area": garden["value"], "preference": garden["limit"]})
    for el in (site.get("backyard") or {}).get("elements", []):
        if el["status"] == "excluded":
            obs.append({"code": "backyard_excluded", "severity": "info", "element": el["element"],
                        "reason": el["reason"]})
    if scheme.get("satellites"):
        obs.append({"code": "satellites", "severity": "info", "satellites": scheme["satellites"]})
    return obs


def render_observations(observations: list[dict], templates: dict, label) -> list[str]:
    """Text lines from the catalog templates; `label(space_id_or_type)` gives display names."""
    lines = []
    for o in observations:
        code = o["code"]
        tpl = templates.get(code)
        if tpl is None:
            continue
        values = dict(o)
        for key in ("spaces", "blocked_by", "taken_by"):
            if key in values:
                values[key] = ", ".join(label(x) for x in values[key]) or "-"
        for key in ("space", "via", "private", "element", "role"):
            if key in values:
                values[key] = label(values[key])
        if code == "satellites":
            values["satellites"] = ", ".join(f"{label(s)} ({label(h)})" for s, h in o["satellites"].items())
        if code == "passed":
            values["paving"] = "-" if o["paving"] is None else f"{o['paving']:.0%}"
            values["paving_limit"] = "-" if o["paving_limit"] is None else f"{o['paving_limit']:.0%}"
            values["site"] = templates["yes"] if o["site_normative_ok"] else templates["no"]
        for key in ("fraction", "target") if code == "circulation_high" else ():
            values[key] = f"{o[key]:.0%}"
        lines.append(templates["prefix"][o["severity"]] + tpl.format(**{k: (f"{v:.0f}" if isinstance(v, float)
                                                                              else v) for k, v in values.items()}))
    return lines
