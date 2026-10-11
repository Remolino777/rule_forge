"""Front yard and main entry of a drawn cell (step 6.7a S2.1b), from the S1.2 geometry and the zoning rules.

Client decisions 2026-10-11: the front yard is laid out with the norm and shows what is circulation (driveway,
walkway, entry deck) and what is garden, for the main door and for the parking; the main door is the typical
San Diego tract-house entry (one side-hinged leaf with a fixed sidelight, recessed under the eave) with a covered
deck outside to wait.

  * driveway: in front of the garage, as wide as the garage, from the garage to the front lot line;
  * entry deck: in front of the main door, depth = the porch projection allowed in the front setback (Z11,
    131.0461(a)(6)) and never under the exterior landing (O05, R311.3); area toward the catalog target; it does not
    run into the driveway;
  * walkway: from the deck to the driveway (along the facade) or straight to the street; the variant with less
    paving is kept (a broken walkway counts against the catalog's maximum breaks);
  * garden: the front of the lot (street to facade) less the paving;
  * checks: front paving fraction (Z10, 131.0447, the deck counted per the rule variant), deck projection (Z11),
    egress door (O04, R311.2) and landing (O05, R311.3).
Only reads contract blocks, the lot polygon and the catalogs / rulesets.
"""

from __future__ import annotations

from typing import Any

from shapely.geometry import LineString, box, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from spaceplan.core.lib.catalog import site_parameters
from spaceplan.core.lib_aux.geometry import clip_y
from spaceplan.modules.lotcap.lib import rule_variants as rv
from spaceplan.modules.stacking.lib.lot_plan import LotPlan
from spaceplan.modules.stacking.lib_aux.plan_geometry import polygon_json

INCH_FT = 1.0 / 12.0
EGRESS_RULE, LANDING_RULE = "O04-EGRESS-DOOR", "O05-EXTERIOR-LANDING"
EMPTY = box(0, 0, 0, 0)


def _local(plan: LotPlan, geo: dict | None) -> BaseGeometry | None:
    return None if not geo else plan.frame.to_local(shape(geo))


def _area(g: BaseGeometry | None) -> float:
    return 0.0 if g is None or g.is_empty else g.area


def main_entry(door_local: BaseGeometry, vestibule_local: BaseGeometry | None, front_y: float,
               types: dict[str, Any], openings, leaf_over_clear_in: float) -> dict[str, Any]:
    """Leaf and sidelight on the front wall of the vestibule (local frame): the sidelight goes on the side of the
    door with more vestibule wall left."""
    t = types["main_entry"]
    leaf, side = float(t["leaf_in"]) * INCH_FT, float(t["sidelight_in"]) * INCH_FT
    cx = door_local.centroid.x
    vx0, vx1 = (vestibule_local.bounds[0], vestibule_local.bounds[2]) if vestibule_local is not None else \
        (cx - leaf, cx + leaf)
    a0, a1 = cx - leaf / 2, cx + leaf / 2
    right = (vx1 - a1) >= (a0 - vx0)
    s0, s1 = (a1, a1 + side) if right else (a0 - side, a0)
    fits = (s1 <= vx1 + 1e-6) and (s0 >= vx0 - 1e-6)
    o4 = openings.params(EGRESS_RULE)
    clear_in = float(t["leaf_in"]) - float(leaf_over_clear_in)      # stops and hinge
    return {"type": "single_with_sidelight" if not t["double_variant"]["enabled"] else "double",
            "leaf_in": t["leaf_in"], "sidelight_in": t["sidelight_in"], "height_in": t["height_in"],
            "swing": t["swing"], "clear_width_in": clear_in, "sidelight_fits_vestibule": fits,
            "egress_ok": clear_in >= float(o4["min_clear_width_in"]) and float(t["height_in"]) >= float(
                o4["min_clear_height_in"]),
            "_leaf": LineString([(a0, front_y), (a1, front_y)]), "_sidelight": LineString([(s0, front_y), (s1, front_y)])}


def front_yard(s1: dict[str, Any], plan: LotPlan, lot_local: BaseGeometry, capacity_rs, openings, catalog,
               scat) -> dict[str, Any]:
    """Driveway, entry deck, walkway and garden of the front of the lot, with the Z10 / Z11 / O04 / O05 checks."""
    ground = _local(plan, s1["levels"][0]["polygon"])
    garage = _local(plan, s1["ground"].get("garage_polygon"))
    acc = s1.get("access_core") or {}
    door = _local(plan, acc.get("door"))
    vest = _local(plan, acc.get("vestibule"))
    if ground is None or door is None:
        return {"status": "not_evaluated", "reason": "no ground floor or main door"}
    fy = ground.bounds[1]                                 # street facade of the ground floor
    street_y = lot_local.bounds[1]
    setback = min((sl.setback_ft for sl in plan.front_lines), default=fy - street_y)
    front_line_y = max((sl.line.bounds[3] for sl in plan.front_lines), default=street_y)
    yard = clip_y(lot_local, y_max=front_line_y + setback)
    front = clip_y(lot_local, y_max=fy)
    pav = rv.front_pavement_limits(capacity_rs)
    porch = rv.porch_projection_limit(capacity_rs, setback)
    walk = site_parameters(catalog, "walkway")
    deck_cfg = site_parameters(catalog, "entry_deck")
    landing_ft = float(openings.params(LANDING_RULE)["min_depth_in"]) * INCH_FT
    types = scat.s21["doors"]["types"]

    # driveway in front of the garage
    driveway = None
    if garage is not None and not garage.is_empty:
        gx0, gy0, gx1, _ = garage.bounds
        driveway = box(gx0, street_y - 1.0, gx1, gy0).intersection(lot_local)

    # entry deck in front of the door, kept off the driveway
    entry = main_entry(door, vest, fy, types, openings, scat.s21["doors"]["leaf_over_clear_in"])
    depth = max(min(float(porch["max_projection_ft"]), fy - street_y), landing_ft)
    width = max(float(deck_cfg["area_target"]) / depth, float(types["main_entry"]["leaf_in"] + types["main_entry"]
                                                                  ["sidelight_in"]) * INCH_FT)
    cx = door.centroid.x
    dx0, dx1 = cx - width / 2, cx + width / 2
    fx0, fx1 = ground.bounds[0], ground.bounds[2]
    if driveway is not None and not driveway.is_empty:
        rx0, _, rx1, _ = driveway.bounds
        if dx1 > rx0 and dx0 < rx1:                       # slide the deck off the driveway
            dx0, dx1 = (rx1, rx1 + width) if cx >= 0.5 * (rx0 + rx1) else (rx0 - width, rx0)
    dx0, dx1 = max(dx0, fx0), min(dx1, fx1)
    deck = box(dx0, fy - depth, dx1, fy).intersection(lot_local)

    # walkway: to the driveway along the facade, or straight to the street
    ww = float(walk["width_ft"])
    variants = []
    if driveway is not None and not driveway.is_empty:
        rx0, _, rx1, _ = driveway.bounds
        a, b = (rx1, dx0) if dx0 >= rx1 else (dx1, rx0)
        w = box(min(a, b), fy - depth, max(a, b), fy - depth + ww).intersection(lot_local) if abs(b - a) > 1e-6 \
            else EMPTY
        variants.append(("from_driveway", w, 1 if abs(b - a) > 1e-6 else 0))
    mid = 0.5 * (dx0 + dx1)
    variants.append(("independent", box(mid - ww / 2, street_y - 1.0, mid + ww / 2, fy - depth).intersection(
        lot_local), 0))

    def paving_of(wk):
        parts = [g for g in (driveway, wk) if g is not None and not g.is_empty]
        if pav["deck_counts"]:
            parts.append(deck)
        return unary_union(parts).intersection(yard).area if parts else 0.0

    scored = sorted(variants, key=lambda v: (v[2] > int(walk["max_breaks"]), paving_of(v[1])))
    kind, walkway, breaks = scored[0]
    paved = paving_of(walkway)
    fraction = paved / yard.area if yard.area else 0.0
    circulation = unary_union([g for g in (driveway, walkway, deck) if g is not None and not g.is_empty])
    garden = front.difference(circulation)
    projection = max(0.0, (front_line_y + setback) - (fy - depth))
    checks = [
        {"rule_id": "Z10-FRONT-PAVEMENT", "value": round(fraction, 3), "limit": pav["max_fraction"],
         "passes": fraction <= pav["max_fraction"] + 1e-9, "status": pav["status"], "source": pav["source"]},
        {"rule_id": "Z11-PROJECTIONS", "value": round(projection, 2), "limit": round(porch["max_projection_ft"], 2),
         "passes": projection <= porch["max_projection_ft"] + 1e-6, "status": porch["status"],
         "source": porch["source"]},
        {"rule_id": EGRESS_RULE, "value": entry["clear_width_in"], "limit": openings.params(EGRESS_RULE)
         ["min_clear_width_in"], "passes": entry["egress_ok"], "status": openings.status(EGRESS_RULE),
         "source": openings.source_tag(EGRESS_RULE)},
        {"rule_id": LANDING_RULE, "value": round(depth, 2), "limit": round(landing_ft, 2),
         "passes": depth >= landing_ft - 1e-9 and (dx1 - dx0) >= float(types["main_entry"]["leaf_in"]) * INCH_FT,
         "status": openings.status(LANDING_RULE), "source": openings.source_tag(LANDING_RULE)}]
    nd = int(scat.geometry["round_ft"])

    def world(g):
        return None if g is None or g.is_empty else polygon_json(plan.to_world(g), nd)

    def line(g):
        return [[round(c, nd) for c in xy] for xy in plan.to_world(g).coords]

    return {
        "status": "laid_out",
        "main_entry": {**{k: v for k, v in entry.items() if not k.startswith("_")},
                       "leaf": line(entry["_leaf"]), "sidelight": line(entry["_sidelight"]),
                       "covered_deck": True},
        "driveway": world(driveway), "walkway": world(walkway), "walkway_variant": kind, "walkway_breaks": breaks,
        "entry_deck": world(deck), "deck_depth_ft": round(depth, 2), "deck_width_ft": round(dx1 - dx0, 2),
        "garden": world(garden),
        "areas_sqft": {"front_yard": round(yard.area, 1), "front": round(front.area, 1),
                       "driveway": round(_area(driveway), 1), "walkway": round(_area(walkway), 1),
                       "entry_deck": round(_area(deck), 1), "garden": round(_area(garden), 1),
                       "paved_in_front_yard": round(paved, 1)},
        "paving_fraction": round(fraction, 3),
        "checks": checks,
    }


__all__ = ["front_yard", "main_entry"]
