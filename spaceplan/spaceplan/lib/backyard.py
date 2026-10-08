"""Backyard program (layer 1d): rear deck, pool or spa, barbecue, shed and garden beds behind the house.

Not every element has to fit. Elements enter by priority while respecting:
  1. a minimum green fraction of the yard reserved first (catalog default, brief override);
  2. each element's minimum area and minimum dimension (catalog), with the remaining budget
     shared up to the target area;
  3. groups (one water element: pool or spa) and dependencies (barbecue needs the deck);
  4. geometric placement with clearances to lot lines and to the dwelling (ruleset values,
     several still placeholders pending verification).
The result lists what was placed, what was left out and why, and the green that remains.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass

import shapely
from shapely.geometry import Polygon, box
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from spaceplan.lib.catalog import Catalog
from spaceplan.lib.rules import RuleSet
from spaceplan.lib_aux.quantity import PROVISIONAL, VERIFIED, worst_status

Rect = tuple[float, float, float, float]


@dataclass(frozen=True)
class Request:
    element: str
    priority: int
    spec: dict


def requests_from_brief(catalog: Catalog, program: dict) -> list[Request]:
    specs = {e["element"]: e for e in catalog.data["backyard_elements"]}
    order = [e["element"] for e in catalog.data["backyard_elements"]]
    out = [Request(r["element"], r.get("priority") or specs[r["element"]]["priority"], specs[r["element"]])
           for r in program["elements"]]
    return sorted(out, key=lambda r: (r.priority, order.index(r.element)))


def rect_dims(area: float, aspect: float, min_dim: float) -> tuple[float, float]:
    """(short, long) sides for an area and a long/short ratio, never below the minimum dimension."""
    short = math.sqrt(area / aspect)
    if short < min_dim:
        short = min_dim
    return short, area / short


def clearance(rs: RuleSet, spec: dict, kind: str) -> tuple[float, str | None, str | None]:
    ref = spec["clearances"].get(kind)
    if not ref:
        return 0.0, None, None
    value = float(rs.rule(ref["rule_id"])["parameters"][ref["param"]])
    return value, rs.status(ref["rule_id"]), rs.source_tag(ref["rule_id"])


Placer = Callable[[Request, float], tuple[BaseGeometry | None, str | None]]


def priority_filter(requests: list[Request], yard_area: float, min_green: float, groups: dict,
                    placer: Placer | None = None) -> dict:
    """Area/priority logic shared by the geometric planner and the pure area filter (placer=None)."""
    budget = yard_area * (1.0 - min_green)
    used = 0.0
    group_count: Counter = Counter()
    placed: dict[str, dict] = {}
    rows = []
    for req in requests:
        spec = req.spec
        row = {"element": req.element, "priority": req.priority, "status": "excluded", "area_sqft": 0.0,
               "reason": None, "polygon": None}
        group = spec["group"]
        if group and group_count[group] >= groups[group]["max"]:
            row["reason"] = f"group '{group}' already has {groups[group]['max']} element(s)"
        elif any(dep not in placed for dep in spec["requires"]):
            row["reason"] = f"requires {', '.join(spec['requires'])}"
        else:
            left = budget - used
            if not spec["counts_as_green"] and spec["area"]["min"] > left + 1e-9:
                row["reason"] = f"area: needs {spec['area']['min']:g} sq ft, {max(left, 0):.0f} left after the green reserve"
            else:
                sizes = [spec["area"]["target"]] if spec["counts_as_green"] else [
                    min(spec["area"]["target"], left), spec["area"]["min"]]
                sizes = [s for i, s in enumerate(sizes) if s >= spec["area"]["min"] - 1e-9 and s not in sizes[:i]]
                geom, why = None, None
                for size in sizes:
                    if placer is None:
                        geom, why, area = None, None, size
                        break
                    geom, why = placer(req, size)
                    if geom is not None:
                        area = geom.area
                        break
                if placer is not None and geom is None:
                    row["reason"] = f"geometry: {why}"
                else:
                    row.update(status="placed", area_sqft=area, polygon=geom, reason=None)
                    placed[req.element] = row
                    if group:
                        group_count[group] += 1
                    if not spec["counts_as_green"]:
                        used += area
        rows.append(row)
    return {"budget_sqft": budget, "used_sqft": used, "elements": rows}


@dataclass
class YardContext:
    yard: BaseGeometry                 # local frame, behind the footprint
    footprint: Rect
    lot_lines: list[BaseGeometry]      # local lines that bound the yard (sides and rear)
    deck_anchor_x: float
    step: float


def _candidates(ctx: YardContext, w: float, d: float, y_fixed: float | None):
    x0, y0, x1, y1 = ctx.yard.bounds
    xs = [x0 + i * ctx.step for i in range(int((x1 - x0 - w) / ctx.step) + 1)]
    ys = [y_fixed] if y_fixed is not None else [y0 + j * ctx.step for j in range(int((y1 - y0 - d) / ctx.step) + 1)]
    for x in xs:
        for y in ys:
            yield box(x, y, x + w, y + d)


def make_placer(ctx: YardContext, rs: RuleSet, placed_geoms: dict[str, BaseGeometry]) -> Placer:
    fp = box(*ctx.footprint)
    lines = unary_union(ctx.lot_lines) if ctx.lot_lines else None

    def place(req: Request, area: float):
        spec = req.spec
        lot_gap, _, _ = clearance(rs, spec, "lot_line")
        dwelling_gap, _, _ = clearance(rs, spec, "dwelling")
        allowed = ctx.yard
        if lines is not None and lot_gap > 0:
            allowed = allowed.difference(lines.buffer(lot_gap, cap_style="flat"))
        if dwelling_gap > 0:
            allowed = allowed.difference(fp.buffer(dwelling_gap))
        others = [g for k, g in placed_geoms.items() if k != req.element]
        if others:
            allowed = allowed.difference(unary_union(others))
        allowed = allowed.buffer(1e-6)
        shapely.prepare(allowed)
        short, long = rect_dims(area, spec["aspect"], spec["min_dim_ft"])
        deck = placed_geoms.get(spec["requires"][0] if spec["requires"] else "rear_deck")
        best, best_score = None, -math.inf
        orientations = [(long, short)] if spec["placement"] == "attach_rear" else [(long, short), (short, long)]
        fx0, _, fx1, fy1 = ctx.footprint
        if spec["placement"] == "attach_rear" and long > fx1 - fx0:
            long = fx1 - fx0
            short = max(spec["min_dim_ft"], area / long)
            orientations = [(long, short)]
        for w, d in orientations:
            y_fixed = fy1 if spec["placement"] == "attach_rear" else None
            for rect in _candidates(ctx, w, d, y_fixed):
                if not allowed.covers(rect):
                    continue
                cx, cy = rect.centroid.x, rect.centroid.y
                p = spec["placement"]
                if p == "attach_rear":
                    if rect.bounds[0] < fx0 - 1e-9 or rect.bounds[2] > fx1 + 1e-9:
                        continue
                    s = -abs(cx - ctx.deck_anchor_x)
                elif p == "touch_deck":
                    if deck is None or rect.distance(deck) > 1e-6:
                        continue
                    s = -abs(cy - deck.centroid.y) - 0.1 * abs(cx - deck.centroid.x)
                elif p == "near_deck" and deck is not None:
                    s = -rect.distance(deck)
                elif p in ("visible_center", "near_deck"):
                    s = -abs(cx - 0.5 * (fx0 + fx1)) - 0.3 * (rect.bounds[1] - fy1)
                elif p == "rear_corner":
                    s = rect.bounds[3] + 0.5 * abs(cx - 0.5 * (fx0 + fx1))
                else:  # along_side
                    s = -min((ln.distance(rect) for ln in ctx.lot_lines), default=0.0)
                if s > best_score + 1e-9:
                    best, best_score = rect, s
        if best is None:
            return None, f"no position for {w:.1f} x {d:.1f} ft respecting clearances (lot line {lot_gap:g} ft, " \
                         f"dwelling {dwelling_gap:g} ft)"
        placed_geoms[req.element] = best
        return best, None

    return place


def plan_backyard(catalog: Catalog, rs: RuleSet, program: dict, ctx: YardContext, frame) -> dict:
    policy = catalog.data["backyard_policy"]
    min_green = program.get("min_green_fraction")
    min_green = policy["min_green_fraction"] if min_green is None else min_green
    requests = requests_from_brief(catalog, program)
    placed_geoms: dict[str, BaseGeometry] = {}
    result = priority_filter(requests, ctx.yard.area, min_green, policy["groups"], make_placer(ctx, rs, placed_geoms))
    non_green = sum(r["area_sqft"] for r in result["elements"]
                    if r["status"] == "placed" and not next(q for q in requests if q.element == r["element"]).spec["counts_as_green"])
    green = ctx.yard.area - non_green
    checks = [{"check_id": "green_fraction", "kind": "preference", "value": green / ctx.yard.area if ctx.yard.area else 0.0,
               "limit": min_green, "passes": green >= min_green * ctx.yard.area - 1e-6, "status": VERIFIED,
               "source": "catalog:backyard_policy.min_green_fraction / brief:backyard_program", "note": None}]
    statuses = []
    for r in result["elements"]:
        spec = next(q for q in requests if q.element == r["element"]).spec
        gaps = {}
        for kind in ("lot_line", "dwelling"):
            value, status, source = clearance(rs, spec, kind)
            if status:
                gaps[kind] = {"ft": value, "status": status, "source": source}
                statuses.append(status)
        r["clearances"] = gaps
        if r["polygon"] is not None:
            x0, y0, x1, y1 = r["polygon"].bounds
            r["dims_ft"] = [x1 - x0, y1 - y0]
            r["polygon"] = frame.to_world(r["polygon"])
        else:
            r["dims_ft"] = None
    pool_placed = any(r["element"] == "pool" and r["status"] == "placed" for r in result["elements"])
    if pool_placed:
        barrier = rs.rule("Z13-POOL-SPA")["parameters"]["safety_barrier_required"]
        checks.append({"check_id": "pool_safety_barrier", "kind": "deferred", "value": None, "limit": None,
                       "passes": None, "status": rs.status("Z13-POOL-SPA"), "source": rs.source_tag("Z13-POOL-SPA"),
                       "note": "barrier required" if barrier else "no barrier rule"})
    return {
        "yard_area_sqft": ctx.yard.area,
        "min_green_fraction": min_green,
        "budget_sqft": result["budget_sqft"],
        "used_sqft": result["used_sqft"],
        "green_area_sqft": green,
        "green_fraction": green / ctx.yard.area if ctx.yard.area else 0.0,
        "status": worst_status(*statuses) if statuses else VERIFIED,
        "elements": result["elements"],
        "checks": checks,
        "yard_polygon": frame.to_world(ctx.yard),
    }


__all__ = ["Request", "YardContext", "plan_backyard", "priority_filter", "rect_dims", "requests_from_brief",
           "PROVISIONAL"]


def backyard_for_site(catalog: Catalog, rs: RuleSet, brief: dict, lot, boundaries, site: dict, zoning: dict) -> None:
    """Plan the backyard of every buildable site option (in place). Uses the best zoning scheme when there is one."""
    from shapely.geometry import LineString, shape

    from spaceplan.lib_aux.geometry import clip_y

    program = brief.get("backyard_program")
    if not program:
        return
    frame = boundaries.frame
    lot_local = frame.to_local(lot.polygon)
    lines = [frame.to_local(LineString(e.points)) for e in lot.edges if e.edge_id not in boundaries.front_edge_ids]
    zoned = {o["option_id"]: o for o in zoning["options"] if o["status"] == "zoned"}
    step = catalog.data["backyard_policy"]["search_step_ft"]
    for option in site["options"]:
        if "zones" not in option:
            continue
        scheme = zoned[option["option_id"]]["schemes"][0] if option["option_id"] in zoned else None
        if scheme:
            fp = tuple(scheme["footprint_local"])
            rear_cells = [c for c in scheme["cells"].values() if "rear" in c["facades"]
                          and c["zone"] in ("social", "kitchen")]
            rear_cells.sort(key=lambda c: (0 if "dining_room" in c["spaces"] else 1 if c["zone"] == "kitchen" else 2))
            anchor = 0.5 * (rear_cells[0]["rect_local"][0] + rear_cells[0]["rect_local"][2]) if rear_cells \
                else 0.5 * (fp[0] + fp[2])
            source = f"zoning {option['option_id']} #1 ({scheme['footprint_variant']})"
        else:
            fp = tuple(frame.to_local(shape(option["zones"]["footprint"]["polygon"])).bounds)
            anchor, source = 0.5 * (fp[0] + fp[2]), f"site {option['option_id']} footprint (no one-floor zoning)"
        yard = clip_y(lot_local, y_min=fp[3])
        ctx = YardContext(yard=yard, footprint=fp, lot_lines=lines, deck_anchor_x=anchor, step=step)
        option["backyard"] = {"source": source, **plan_backyard(catalog, rs, program, ctx, frame)}
