"""Program adjustment of stage S2.1 (step 6.7a S2.1b): corridor allowance of the private zones and baths per bedroom.

Runs on a copy of an area-matrix cell before S0/S1, so the area matrix and the golden snapshot stay unchanged:

  * K10 (client decision 2026-10-11): the master gets its private bath and walk-in closet first (when the program
    lacks them and the FAR allows), then each other bedroom of the floor its own bath while the FAR allows; the baths
    of a floor are assigned en suite (host = the bedroom) one per bedroom; when there are fewer baths than bedrooms,
    a bath is shared by two bedrooms (`shared_by`), sits between them and opens onto the hall;
  * corridor allowance: a private zone serving the catalog's minimum number of rooms gets hall width x the least
    sides of its rooms as part of its zone target (a row flagged `allowance`, not a space), so stage S2 sizes the
    zone with its corridor and stage S2.1 does not take it from the rooms;
  * the gross area of each floor grows by what was added, within the FAR slack of the lot (the allowance first, then
    the master's spaces, then the baths); without slack the allowance is reserved inside the floor;
  * main bedroom (step 6.7a S2.2i, client 2026-10-13): an upper floor with two or more bedrooms and no primary suite
    (even when the suite is downstairs) makes its largest bedroom the main one (`master`): space.master_bedroom
    extra_share more area (taken from the floor's other bedrooms down to their catalog minimum) and a walk-in closet
    en suite; the floor's gross, and so stage S1, stay as they are (stage S2 scales the targets to the floor); the
    main bedroom (the one named primary first, else the largest) gets the floor's first en-suite bath.

Area criteria (step 6.7a S2.2e, client decision 2026-10-12 10:18; design module area_criteria), when enabled:

  0. every space with design criteria is cut to its effective maximum (absolute cap, hierarchy, share of the net
     program area; never below its recommended size) and carries it as `area_cap_sqft` for stage S2.1; the freed
     area leaves the floor (`freed_area` "unbuilt": net and gross shrink by the freed area times the floor's
     gross/net ratio, the ground floor never below the upper one) or stays in it ("keep");
  3b. the whole primary suite (bedroom + walk-in + its bath) is brought within its cap relative to the garage,
     each part down to its floor (recommended / catalog minimum);
  3c. extra room: when the FAR slack left holds the extra package (bedroom + bath at their recommended sizes plus
     the overhead) on the top floor, "propose" reports it and "auto" adds it (the bath en suite); "never" does
     nothing. The program never changes without this explicit rule.
"""

from __future__ import annotations

import copy
from typing import Any

from spaceplan.modules.design.lib import area_criteria as ac

BEDROOM, SUITE, WALK_IN = "bedroom", "primary_suite", "walk_in_closet"
GARAGE_PREFIX = "garage"


def _row(space_id: str, space_type: str, zone: str, floor: int, area: float, host: str | None = None,
         **extra) -> dict[str, Any]:
    return {"space_id": space_id, "space_type": space_type, "zone": zone, "household_role": "general",
            "host_space_id": host, "floor": floor, "area_sqft": round(float(area), 1), **extra}


def _house_net(rows: list[dict[str, Any]]) -> float:
    """Net program area of the house (garage and corridor allowances excluded)."""
    return sum(float(r["area_sqft"]) for r in rows
               if not r.get("allowance") and not str(r["space_type"]).startswith(GARAGE_PREFIX))


def _shrink_floors(out: dict[str, Any], freed: list[float]) -> list[float]:
    """Take the freed net area out of the floors (net and gross, the gross by the floor's gross/net ratio); the
    ground floor keeps what would leave it smaller than the upper floor. Returns the gross removed per floor."""
    split = out.get("split") or {}
    g = list(split.get("gross_by_floor_sqft") or [])
    n = list(split.get("net_by_floor_sqft") or [])
    removed = [0.0] * len(freed)
    for f in sorted(range(len(freed)), reverse=True):          # upper floors first: the ground floor checks them
        if f >= len(g) or freed[f] <= 0:
            continue
        ratio = g[f] / n[f] if f < len(n) and n[f] > 0 else 1.0
        take = freed[f] * ratio
        if f == 0 and len(g) > 1:
            take = max(0.0, min(take, g[0] - max(g[1:])))
        if take <= 0:
            continue
        g[f] = round(g[f] - take, 1)
        if f < len(n):
            n[f] = round(n[f] - take / ratio, 1)
        removed[f] = take
    if g:
        split["gross_by_floor_sqft"] = g
    if n:
        split["net_by_floor_sqft"] = n
    out["split"] = split
    total = sum(removed)
    out["gross_sqft"] = round(float(out.get("gross_sqft") or 0.0) - total, 1)
    if removed and removed[0]:
        out["ground_sqft"] = round(float(out.get("ground_sqft") or 0.0) - removed[0], 1)
    if len(removed) > 1 and sum(removed[1:]):
        out["upper_sqft"] = round(float(out.get("upper_sqft") or 0.0) - sum(removed[1:]), 1)
    return removed


def _apply_caps(rows: list[dict[str, Any]], values: dict[str, Any], net: float, n_floors: int) -> tuple[list, list]:
    """Step 0: every space at most its effective maximum; (freed net area per floor, report rows)."""
    freed = [0.0] * n_floors
    capped = []
    for r in rows:
        eff = ac.effective_cap(values, r["space_type"], net)
        if eff is None:
            continue
        r["area_cap_sqft"] = eff["cap_sqft"]
        area = float(r["area_sqft"])
        if area > eff["cap_sqft"] + 1e-6:
            freed[r["floor"]] += area - eff["cap_sqft"]
            r["area_sqft"] = eff["cap_sqft"]
            capped.append({"space_id": r["space_id"], "space_type": r["space_type"], "floor": r["floor"],
                           "from_sqft": round(area, 1), "to_sqft": eff["cap_sqft"], "binding": eff["binding"]})
    return freed, capped


def _suite_total(rows: list[dict[str, Any]], values: dict[str, Any], net: float) -> list[dict[str, Any]]:
    """Step 3b: the whole primary suite within its cap, the bedroom first, then its parts, each down to its floor;
    returns one report row per suite (the area taken off is left to the caller)."""
    cap = ac.suite_total_cap(values)
    if cap is None:
        return []
    out = []
    for suite in [r for r in rows if r["space_type"] == SUITE]:
        parts = sorted((r for r in rows if r.get("host_space_id") == suite["space_id"]
                        and r["space_type"] in ac.SUITE_PARTS), key=lambda r: ac.SUITE_PARTS.index(r["space_type"]))
        members = [suite, *parts]
        total = sum(float(r["area_sqft"]) for r in members)
        over = total - cap
        taken = 0.0
        for r in members:
            if over <= 1e-6:
                break
            eff = ac.effective_cap(values, r["space_type"], net)
            floor = eff["floor_sqft"] if eff else float(r["area_sqft"])
            cut = min(over, max(0.0, float(r["area_sqft"]) - floor))
            if cut > 0:
                r["area_sqft"] = round(float(r["area_sqft"]) - cut, 1)
                over -= cut
                taken += cut
        for r in members:
            if taken > 0 and r.get("area_cap_sqft") is not None and float(r["area_sqft"]) < float(r["area_cap_sqft"]):
                r["area_cap_sqft"] = float(r["area_sqft"])     # the suite share now sets the part's cap
        out.append({"suite": suite["space_id"], "cap_sqft": cap, "total_before_sqft": round(total, 1),
                    "total_after_sqft": round(total - taken, 1), "within_cap": over <= 1e-6, "floor": suite["floor"],
                    "taken_sqft": round(taken, 1)})
    return out


def _extra_room(rows: list[dict[str, Any]], values: dict[str, Any], catalog, slack: float, added: list[float],
                out: dict[str, Any], new_id) -> dict[str, Any]:
    """Step 3c: the extra package (bedroom + bath by default) on the top floor when the FAR slack holds it and the
    upper floor stays within the ground floor; "propose" reports it, "auto" adds it, "never" does nothing."""
    pol = ac.policy(values, "extra_room_policy", "never")
    types, need = ac.extra_package(values)
    res: dict[str, Any] = {"policy": pol, "package": types, "need_sqft": need, "available_sqft": round(slack, 1),
                           "fits": False, "applied": False}
    if pol == "never" or not types:
        return res
    g = list((out.get("split") or {}).get("gross_by_floor_sqft") or [])
    floor = max(r["floor"] for r in rows)
    res["floor"] = floor
    fits = need <= slack + 1e-9
    if not fits:
        res["reason"] = "far_slack"
    elif floor > 0 and len(g) > floor and g[floor] + added[floor] + need > g[0] + added[0] + 1e-9:
        fits = False
        res["reason"] = "upper_exceeds_ground"
    res["fits"] = fits
    if not (fits and pol == "auto"):
        return res
    host, new = None, []
    for t in types:
        st = catalog.space_type(t)
        area = values.get(f"space.{t}.area_rec_sqft") or st["area"]["target"]
        sid = new_id(f"{t}_extra")
        hosted = host if host and not st.get("habitable") else None
        zone = "private" if hosted or t == BEDROOM else (st.get("zone") or "private")
        row = _row(sid, t, zone, floor, float(area), hosted, extra_room=True)
        eff = ac.effective_cap(values, t, None)
        if eff is not None:
            row["area_cap_sqft"] = eff["cap_sqft"]
        if st.get("habitable") and host is None:
            host = sid
        rows.append(row)
        new.append(sid)
    added[floor] += need
    res.update({"applied": True, "added": new, "added_sqft": need})
    return res


def adjust_program(cell: dict[str, Any], far_max_sqft: float | None, catalog, scat, client_rs,
                   design_values: dict[str, Any] | None = None) -> tuple[dict, dict]:
    """(adjusted copy of the cell, report). Cells with one floor or without a space split come back unchanged.
    `design_values`: the design registry values (baseline or a client profile) for the area criteria (S2.2e)."""
    if cell.get("floors", 1) < 2 or not cell.get("space_split"):
        return cell, {"applied": False}
    prog = scat.s21["program"]
    k10 = client_rs.params("K10-BATHS-PER-BEDROOM")
    out = copy.deepcopy(cell)
    rows: list[dict[str, Any]] = out["space_split"]
    values = design_values or {}
    caps_on = bool(values) and ac.enabled(values)
    n_floors = 1 + max(r["floor"] for r in rows)
    net0 = _house_net(rows)
    area_report: dict[str, Any] = {"enabled": caps_on}
    if caps_on:                                          # 0. area caps (S2.2e)
        freed, capped = _apply_caps(rows, values, net0, n_floors)
        mode = ac.policy(values, "freed_area", "unbuilt")
        removed = _shrink_floors(out, freed) if mode == "unbuilt" else [0.0] * n_floors
        area_report.update({"house_net_sqft": round(net0, 1), "capped": capped, "freed_area": mode,
                            "freed_net_by_floor_sqft": [round(a, 1) for a in freed],
                            "unbuilt_gross_by_floor_sqft": [round(a, 1) for a in removed]})
    gross = float(out.get("gross_sqft") or 0.0)
    slack = max(0.0, float(far_max_sqft) - gross) if far_max_sqft is not None else 0.0
    slack0 = slack
    hall_w = float(catalog.data["circulation"]["design_width_ft"])
    added_by_floor = [0.0] * (1 + max(r["floor"] for r in rows))
    report: dict[str, Any] = {"applied": True, "far_slack_sqft": round(slack0, 1), "added": [], "allowance": {},
                              "en_suite": {}, "shared": [], "skipped": []}
    ids = {r["space_id"] for r in rows}

    def target(st: str) -> float:
        return float(catalog.space_type(st)["area"]["target"])

    def new_id(base: str) -> str:
        k, sid = 1, base
        while sid in ids:
            k += 1
            sid = f"{base}_{k}"
        ids.add(sid)
        return sid

    def take(area: float) -> bool:
        nonlocal slack
        if area <= slack + 1e-9:
            slack -= area
            return True
        return False

    floors = sorted({r["floor"] for r in rows})
    # 1. corridor allowance (reserved first; it raises the floor only while the FAR allows)
    for f in floors:
        rooms = [r for r in rows if r["floor"] == f and r["space_type"] in prog["corridor_allowance"]["from_types"]
                 and not r.get("host_space_id")]
        if len(rooms) < int(prog["corridor_allowance"]["min_rooms"]):
            continue
        sides = sum(float(catalog.space_type(r["space_type"])["min_side_ft"]) for r in rooms)
        allowance = hall_w * sides
        rows.append(_row(new_id(f"corridor_allowance_{f}"), "hall", "private", f, allowance,
                         allowance="corridor"))
        grown = min(allowance, slack)
        slack -= grown
        added_by_floor[f] += grown
        report["allowance"][str(f)] = {"sqft": round(allowance, 1), "within_far": round(grown, 1)}

    # 2. the master first: private bath and walk-in closet
    for suite in [r for r in rows if r["space_type"] == SUITE]:
        f = suite["floor"]
        for need in k10["master_first"]:
            have = [r for r in rows if r["floor"] == f and r["space_type"] == need]
            if have:
                for r in have:
                    r["host_space_id"] = r.get("host_space_id") or suite["space_id"]
                continue
            area = target(need)
            if take(area):
                rows.append(_row(new_id(f"{need}_k10"), need, "private", f, area, suite["space_id"]))
                added_by_floor[f] += area
                report["added"].append({"space_type": need, "floor": f, "sqft": area, "for": suite["space_id"]})
            else:
                report["skipped"].append({"space_type": need, "floor": f, "reason": "FAR"})

    # 2b. the main bedroom of an upper floor without a suite (S2.2i)
    if values.get("space.master_bedroom.enabled"):
        for f in floors:
            if f == 0 or any(r["floor"] == f and r["space_type"] == SUITE for r in rows):
                continue
            beds = [r for r in rows if r["floor"] == f and r["space_type"] == BEDROOM and not r.get("host_space_id")]
            if len(beds) < 2:
                continue
            main = max(beds, key=lambda r: ("primary" in r["space_id"], float(r["area_sqft"]), r["space_id"]))
            extra = float(main["area_sqft"]) * float(values.get("space.master_bedroom.extra_share") or 0.0)
            walk_in = target(WALK_IN) if values.get("space.master_bedroom.walk_in") else 0.0
            source = "floor"                             # within the floor: the gross (and stage S1) stays as it
            others = [r for r in beds if r is not main]  # is; the other bedrooms give the extra area down to their
            floor_min = float(catalog.space_type(BEDROOM)["area"]["min"])   # minimum; the walk-in is new program
            spare = sum(max(0.0, float(r["area_sqft"]) - floor_min) for r in others)   # that stage S2 fits in the
            extra = min(spare, extra)                    # floor (its targets are scaled to the floor's area)
            for r in others:
                share = max(0.0, float(r["area_sqft"]) - floor_min) / spare if spare > 0 else 0.0
                r["area_sqft"] = round(float(r["area_sqft"]) - extra * share, 1)
            main["area_sqft"] = round(float(main["area_sqft"]) + extra, 1)
            main["master"] = True
            if main.get("area_cap_sqft") is not None:
                main["area_cap_sqft"] = max(float(main["area_cap_sqft"]), main["area_sqft"])
            if walk_in > 0:
                rows.append(_row(new_id(f"{WALK_IN}_main"), WALK_IN, "private", f, walk_in, main["space_id"]))
            report.setdefault("master", []).append({"bedroom": main["space_id"], "floor": f,
                                                    "extra_sqft": round(extra, 1), "walk_in_sqft": round(walk_in, 1),
                                                    "from": source})

    # 3. a bath per bedroom while the FAR allows, then the assignment (en suite, or shared by two bedrooms)
    bath = prog["bath_type"]
    for f in floors:
        beds = [r["space_id"] for r in sorted((r for r in rows if r["floor"] == f and r["space_type"] == BEDROOM),
                                              key=lambda r: (not r.get("master"), r["space_id"]))]   # main first
        if not beds:
            continue
        baths = sorted((r for r in rows if r["floor"] == f and r["space_type"] == bath and not r.get("host_space_id")),
                       key=lambda r: r["space_id"])
        for _ in range(len(beds) - len(baths)):
            area = target(bath)
            if not take(area):
                report["skipped"].append({"space_type": bath, "floor": f, "reason": "FAR"})
                break
            r = _row(new_id(f"{bath}_k10"), bath, "private", f, area)
            rows.append(r)
            baths.append(r)
            added_by_floor[f] += area
            report["added"].append({"space_type": bath, "floor": f, "sqft": area})
        n_b, n_r = len(baths), len(beds)
        shared = 0 if n_b >= n_r else min(n_b, n_r - n_b)
        own = n_b - shared if n_b < n_r else n_r
        k = 0
        for r in baths[:own]:
            r["host_space_id"] = beds[k]
            report["en_suite"][r["space_id"]] = beds[k]
            k += 1
        for r in baths[own:own + shared]:
            pair = beds[k:k + 2]
            if len(pair) == 2:
                r["shared_by"] = pair
                report["shared"].append({"bath": r["space_id"], "bedrooms": pair})
            k += 2

    if caps_on:
        for r in rows:                                   # spaces K10 added get their cap too
            if r.get("area_cap_sqft") is None:
                eff = ac.effective_cap(values, r["space_type"], net0)
                if eff is not None:
                    r["area_cap_sqft"] = eff["cap_sqft"]
        suites = _suite_total(rows, values, net0)        # 3b. the whole suite vs the garage
        taken = [0.0] * n_floors
        for x in suites:
            taken[x["floor"]] += x["taken_sqft"]
        if ac.policy(values, "freed_area", "unbuilt") == "unbuilt":
            for f, a in enumerate(taken):
                if f > 0 and a > 0:                     # the ground floor keeps it (never below the upper one)
                    added_by_floor[f] -= a
                    slack += a
        area_report["suite_total"] = suites
        area_report["extra_room"] = _extra_room(rows, values, catalog, slack, added_by_floor, out, new_id)
        slack -= area_report["extra_room"].get("added_sqft", 0.0)
    report["area_criteria"] = area_report

    # 4. gross areas
    total = sum(added_by_floor)
    split = out.get("split") or {}
    g = list(split.get("gross_by_floor_sqft") or [])
    n = list(split.get("net_by_floor_sqft") or [])
    for f, a in enumerate(added_by_floor):
        if f < len(g):
            g[f] = round(g[f] + a, 1)
        if f < len(n):
            n[f] = round(n[f] + a, 1)
    if g:
        split["gross_by_floor_sqft"] = g
    if n:
        split["net_by_floor_sqft"] = n
    split["upper_spaces"] = sorted({*(split.get("upper_spaces") or []),
                                    *(r["space_id"] for r in rows if r["floor"] > 0 and not r.get("allowance"))})
    out["split"] = split
    out["gross_sqft"] = round(gross + total, 1)
    if added_by_floor[0]:
        out["ground_sqft"] = round(float(out.get("ground_sqft") or 0.0) + added_by_floor[0], 1)
    if len(added_by_floor) > 1:
        out["upper_sqft"] = round(float(out.get("upper_sqft") or 0.0) + sum(added_by_floor[1:]), 1)
    rows.sort(key=lambda r: (r["floor"], r["space_id"]))
    report.update({"gross_added_sqft": round(total, 1), "far_slack_left_sqft": round(slack, 1),
                   "added_by_floor_sqft": [round(a, 1) for a in added_by_floor]})
    return out, report


__all__ = ["adjust_program"]
