"""Quality indicators of the drawn spaces (step 6.7a S2.2a): the "before" measure of step S2.2 and the yardstick of
its later steps.

Reads the `s21` block of stack_plan cells and the effective design values (registry baseline or a profile):

  per space   bounding box (the S2.1 spaces are axis-aligned), long/short ratio, rectangularity (area / box),
              fragments (pieces of a space), least side against the catalog, longest side, ratio against the
              preferred and the maximum of its type, clear furniture rectangle that fits, light category (N / P / M,
              upper-floor override), exterior wall length, mean depth from the facade against the daylight depth;
  per house   circulation fraction per floor, longest hall run, halls and foyers that are not one rectangle,
              fragmented spaces, M spaces holding facade while some N space of the floor has less than its share;
  summary     per space type and overall, plus the coverage of the stage (cells with a drawn floor plan).

Values come from the design registry ids (space.<type>.aspect_max, light.category.<type>...), never literals.
"""

from __future__ import annotations

import statistics as st
from collections import defaultdict
from typing import Any

import numpy as np
import shapely
from shapely.geometry import shape

GRID_FT = 0.5            # raster step of the furniture test (the S2 grid)
SPACED = "spaced"
CIRCULATION_TYPES = ("hall", "foyer")


def _value(values: dict[str, Any], pid: str) -> Any:
    return values.get(pid)


def category(values: dict[str, Any], space_type: str, level: int) -> str | None:
    if level > 0 and f"light.category.{space_type}__upper" in values:
        return values[f"light.category.{space_type}__upper"]
    return values.get(f"light.category.{space_type}")


def furniture_options(values: dict[str, Any], space_type: str) -> list[tuple[float, float]]:
    """Clear furniture rectangles of a type (the kitchen: any allowed template)."""
    allowed = values.get(f"space.{space_type}.templates_allowed")
    if allowed:
        return [(values[f"space.{space_type}.template_{t}_w_ft"], values[f"space.{space_type}.template_{t}_d_ft"])
                for t in allowed if f"space.{space_type}.template_{t}_w_ft" in values]
    w, d = values.get(f"space.{space_type}.furniture_w_ft"), values.get(f"space.{space_type}.furniture_d_ft")
    return [] if w is None or d is None else [(w, d)]


def closet_role(sp: dict[str, Any]) -> str:
    """linen / bath_closet / closet (reach-in, leftover or program closet), from the id the layout gives."""
    sid = sp["space_id"]
    for role in ("linen", "bath_closet"):
        if f"_{role}" in sid:
            return role
    return "closet"


def fits_rectangle(geom, w_ft: float, d_ft: float, step: float = GRID_FT) -> bool:
    """True when an axis-aligned w x d rectangle (either orientation) fits inside the geometry."""
    x0, y0, x1, y1 = geom.bounds
    nx, ny = round((x1 - x0) / step), round((y1 - y0) / step)
    if nx <= 0 or ny <= 0:
        return False
    xs = x0 + (np.arange(nx) + 0.5) * step
    ys = y0 + (np.arange(ny) + 0.5) * step
    gx, gy = np.meshgrid(xs, ys)
    mask = shapely.contains_xy(geom, gx, gy).astype(np.int32)
    integral = np.pad(mask.cumsum(0).cumsum(1), ((1, 0), (1, 0)))
    for a, b in ((w_ft, d_ft), (d_ft, w_ft)):
        kx, ky = int(np.ceil(a / step - 1e-9)), int(np.ceil(b / step - 1e-9))
        if kx > nx or ky > ny:
            continue
        s = integral[ky:, kx:] - integral[:-ky, kx:] - integral[ky:, :-kx] + integral[:-ky, :-kx]
        if (s == kx * ky).any():
            return True
    return False


def space_metrics(sp: dict[str, Any], level: int, values: dict[str, Any]) -> dict[str, Any]:
    t = sp["space_type"]
    g = shape(sp["polygon"])
    x0, y0, x1, y1 = g.bounds
    w, h = x1 - x0, y1 - y0
    short, long_ = min(w, h), max(w, h)
    aspect = long_ / short if short > 0 else float("inf")
    pref, amax = _value(values, f"space.{t}.aspect_pref_max"), _value(values, f"space.{t}.aspect_max")
    min_side, max_side = _value(values, f"space.{t}.min_side_ft"), _value(values, f"space.{t}.max_side_ft")
    furniture = furniture_options(values, t)
    cat = category(values, t, level)
    ext = float(sp.get("exterior_ft") or 0.0)
    head = values.get("light.daylight.window_head_ft")
    factor = values.get("light.daylight.depth_factor")
    depth = g.area / ext if ext > 0 else None
    return {
        "space_id": sp["space_id"], "space_type": t, "level": level, "area_sqft": round(g.area, 1),
        "w_ft": round(w, 2), "h_ft": round(h, 2), "short_ft": round(short, 2), "long_ft": round(long_, 2),
        "aspect": round(aspect, 3), "rectangularity": round(g.area / (w * h), 3) if w * h > 0 else 0.0,
        "fragments": len(getattr(g, "geoms", [g])),
        "aspect_pref_ok": None if pref is None else aspect <= pref + 1e-9,
        "aspect_max_ok": None if amax is None else aspect <= amax + 1e-9,
        "min_side_ok": None if min_side is None else short >= min_side - 1e-9,
        "max_side_ok": None if max_side is None else long_ <= max_side + 1e-9,
        "furniture_fits": None if not furniture else any(fits_rectangle(g, w, d) for w, d in furniture),
        "closet_role": closet_role(sp) if t == "closet" else None,
        "category": cat, "exterior_ft": round(ext, 2),
        "daylight_depth_ft": None if depth is None else round(depth, 2),
        "daylight_ok": None if depth is None or head is None or factor is None or cat != "N"
        else depth <= head * factor + 1e-9,
        "fixed": bool(sp.get("fixed")), "synthetic": bool(sp.get("synthetic")),
    }


def cell_metrics(cell: dict[str, Any], values: dict[str, Any]) -> dict[str, Any] | None:
    s21 = cell.get("s21") or {}
    if s21.get("status") != SPACED:
        return None
    spaces, floors = [], {}
    for key in ("ground", "upper"):
        fl = s21.get(key)
        if not fl:
            continue
        level = int(fl.get("level", 0 if key == "ground" else 1))
        rows = [space_metrics(sp, level, values) for sp in fl["spaces"] if sp.get("polygon") and not sp.get("fixed")]
        spaces += rows
        halls = [r for r in rows if r["space_type"] == "hall"]
        n_rows = [r for r in rows if r["category"] == "N"]
        m_facade = [r for r in rows if r["category"] == "M" and r["exterior_ft"] > 0]
        floors[key] = {
            "circulation_fraction": (s21.get("score_parts") or {}).get(key, {}).get("circulation_fraction"),
            "hall_long_ft": max((r["long_ft"] for r in halls), default=0.0),
            "irregular_circulation": sum(1 for r in rows if r["space_type"] in CIRCULATION_TYPES
                                         and (r["rectangularity"] < 0.999 or r["fragments"] > 1)),
            "fragmented": sum(1 for r in rows if r["fragments"] > 1),
            "n_spaces": len(n_rows), "n_daylit": sum(1 for r in n_rows if r["daylight_ok"]),
            "m_with_facade": len(m_facade), "m_facade_ft": round(sum(r["exterior_ft"] for r in m_facade), 1),
        }
    cid = "/".join(str(cell.get(k)) for k in ("lot_id", "household_id", "profile", "scheme_id", "strategy_used"))
    return {"cell_id": cid, "lot_id": cell.get("lot_id"), "profile": cell.get("profile"), "floors": floors, "spaces": spaces}


def _pct(rows: list[dict], key: str) -> float | None:
    vals = [r[key] for r in rows if r[key] is not None]
    return round(100.0 * sum(1 for v in vals if not v) / len(vals), 1) if vals else None


def type_summary(spaces: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by = defaultdict(list)
    for r in spaces:
        if not r["synthetic"] or r["space_type"] in CIRCULATION_TYPES:
            by[r["space_type"]].append(r)
    out = []
    for t, rows in sorted(by.items(), key=lambda kv: -len(kv[1])):
        aspects = sorted(r["aspect"] for r in rows)
        out.append({"space_type": t, "n": len(rows), "aspect_median": round(st.median(aspects), 2),
                    "aspect_p90": round(aspects[int(0.9 * (len(aspects) - 1))], 2),
                    "short_median_ft": round(st.median(r["short_ft"] for r in rows), 1),
                    "long_median_ft": round(st.median(r["long_ft"] for r in rows), 1),
                    "pct_over_pref": _pct(rows, "aspect_pref_ok"), "pct_over_max": _pct(rows, "aspect_max_ok"),
                    "pct_under_min_side": _pct(rows, "min_side_ok"), "pct_over_max_side": _pct(rows, "max_side_ok"),
                    "pct_furniture_misfit": _pct(rows, "furniture_fits"),
                    "pct_not_rectangular": round(100.0 * sum(1 for r in rows if r["rectangularity"] < 0.999)
                                                 / len(rows), 1),
                    "pct_fragmented": round(100.0 * sum(1 for r in rows if r["fragments"] > 1) / len(rows), 1),
                    "pct_not_daylit": _pct(rows, "daylight_ok")})
    return out


def quality_report(stack_plans: list[dict[str, Any]], values: dict[str, Any]) -> dict[str, Any]:
    """Indicators over the S2.1 cells of one or more stack_plan contracts."""
    cells, evaluated, zoned = [], 0, 0
    for plan in stack_plans:
        for cell in plan.get("cells", []):
            s21 = cell.get("s21")
            if not s21:
                continue
            evaluated += 1
            zoned += int(s21.get("status") not in (None, "not_evaluated"))
            m = cell_metrics(cell, values)
            if m:
                cells.append(m)
    spaces = [r for c in cells for r in c["spaces"]]
    measured = [r for r in spaces if r["aspect_pref_ok"] is not None and not r["synthetic"]]
    floors = [f for c in cells for f in c["floors"].values()]
    n_rows = [r for r in spaces if r["category"] == "N"]
    overall = {
        "cells_with_s21": evaluated, "cells_zoned": zoned, "cells_spaced": len(cells),
        "spaces": len(spaces),
        "pct_over_pref": _pct(measured, "aspect_pref_ok"), "pct_over_max": _pct(measured, "aspect_max_ok"),
        "pct_under_min_side": _pct([r for r in spaces if r["min_side_ok"] is not None], "min_side_ok"),
        "pct_furniture_misfit": _pct([r for r in spaces if r["furniture_fits"] is not None], "furniture_fits"),
        "fragmented_spaces": sum(1 for r in spaces if r["fragments"] > 1),
        "irregular_circulation": sum(f["irregular_circulation"] for f in floors),
        "circulation_fraction_median": round(st.median(f["circulation_fraction"] for f in floors
                                                       if f["circulation_fraction"] is not None), 3) if floors else None,
        "hall_long_ft_median": round(st.median(f["hall_long_ft"] for f in floors if f["hall_long_ft"] > 0), 1)
        if any(f["hall_long_ft"] > 0 for f in floors) else None,
        "pct_n_not_daylit": _pct(n_rows, "daylight_ok"),
        "closets_by_role": {r: sum(1 for x in spaces if x.get("closet_role") == r) for r in ("closet", "linen",
                                                                                            "bath_closet")},
        "m_spaces_with_facade": sum(f["m_with_facade"] for f in floors),
        "m_facade_ft": round(sum(f["m_facade_ft"] for f in floors), 1),
    }
    return {"overall": overall, "by_type": type_summary(spaces), "cells": cells}


__all__ = ["GRID_FT", "category", "cell_metrics", "closet_role", "fits_rectangle", "furniture_options", "quality_report", "space_metrics",
           "type_summary"]
