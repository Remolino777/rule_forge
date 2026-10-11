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
    the master's spaces, then the baths); without slack the allowance is reserved inside the floor.
"""

from __future__ import annotations

import copy
from typing import Any

BEDROOM, SUITE = "bedroom", "primary_suite"


def _row(space_id: str, space_type: str, zone: str, floor: int, area: float, host: str | None = None,
         **extra) -> dict[str, Any]:
    return {"space_id": space_id, "space_type": space_type, "zone": zone, "household_role": "general",
            "host_space_id": host, "floor": floor, "area_sqft": round(float(area), 1), **extra}


def adjust_program(cell: dict[str, Any], far_max_sqft: float | None, catalog, scat, client_rs) -> tuple[dict, dict]:
    """(adjusted copy of the cell, report). Cells with one floor or without a space split come back unchanged."""
    if cell.get("floors", 1) < 2 or not cell.get("space_split"):
        return cell, {"applied": False}
    prog = scat.s21["program"]
    k10 = client_rs.params("K10-BATHS-PER-BEDROOM")
    out = copy.deepcopy(cell)
    rows: list[dict[str, Any]] = out["space_split"]
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

    # 3. a bath per bedroom while the FAR allows, then the assignment (en suite, or shared by two bedrooms)
    bath = prog["bath_type"]
    for f in floors:
        beds = sorted(r["space_id"] for r in rows if r["floor"] == f and r["space_type"] == BEDROOM)
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
