"""Stacked-plan sheets of stage S1 (step 6.7a): one sheet per lot, one panel per drawn cell.

Each panel shows the lot, the setback envelope, the ground floor with the stand-in garage, the upper floor and
the stair (same rectangle on both levels), with the roof the plane check kept. Drawn from the stack_plan
contract alone.
"""

from __future__ import annotations

import math
from pathlib import Path

INK, INK2, MUTED, GRID, SURFACE = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#fcfcfb"
GROUND_FILL, UPPER_FILL, GARAGE_FILL, STAIR_FILL = "#d7e6f5", "#eb6834", "#c9c7c0", "#0b0b0b"
WORDS = {
    "es": {"title": "Plantas apiladas (6.7a S1)", "ground": "Planta baja", "upper": "Planta alta",
           "garage": "Garaje", "stair": "Escalera", "envelope": "Envolvente de retiros", "roof": "techo",
           "default": "por defecto", "rotated": "cumbrera girada", "flat": "plano", "None": "plano manda",
           "rear": "atrás", "front": "adelante", "over_garage": "sobre garaje", "more": "celdas más no mostradas"},
    "en": {"title": "Stacked plans (6.7a S1)", "ground": "Ground floor", "upper": "Upper floor",
           "garage": "Garage", "stair": "Stair", "envelope": "Setback envelope", "roof": "roof",
           "default": "default", "rotated": "ridge turned", "flat": "flat", "None": "plane governs",
           "rear": "rear", "front": "front", "over_garage": "over garage", "more": "more cells not shown"},
}


def _rings(poly: dict | None) -> list[list[list[float]]]:
    if not poly:
        return []
    if poly["type"] == "Polygon":
        return [poly["coordinates"][0]]
    return [p[0] for p in poly["coordinates"]]


def _fill(ax, poly, **kw):
    for ring in _rings(poly):
        xs, ys = zip(*ring)
        ax.fill(xs, ys, **kw)


def _line(ax, poly, **kw):
    for ring in _rings(poly):
        xs, ys = zip(*ring)
        ax.plot(xs, ys, **kw)


def plot_stack_sheet(lot: dict, cells: list[dict], out_path: str | Path, lang: str = "es",
                     max_panels: int = 24) -> Path:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch

    w = WORDS.get(lang, WORDS["en"])
    shown = cells[:max_panels]
    ncol = min(6, max(1, len(shown)))
    nrow = max(1, math.ceil(len(shown) / ncol))
    fig, axes = plt.subplots(nrow, ncol, figsize=(2.6 * ncol, 3.4 * nrow + 0.9), squeeze=False)
    fig.patch.set_facecolor(SURFACE)
    plan = lot.get("plan") or {}
    for ax in axes.flat:
        ax.set_axis_off()
    for ax, c in zip(axes.flat, shown):
        s1 = c["s1"]
        ax.set_aspect("equal")
        _line(ax, plan.get("lot_polygon"), color=INK2, lw=0.8)
        _line(ax, plan.get("envelope_polygon"), color=MUTED, lw=0.6, ls="--")
        _fill(ax, s1["levels"][0]["polygon"], color=GROUND_FILL, ec=INK2, lw=0.6)
        _fill(ax, s1["ground"].get("garage_polygon"), color=GARAGE_FILL, ec=INK2, lw=0.5, hatch="///")
        _fill(ax, s1["levels"][1]["polygon"], color=UPPER_FILL, alpha=0.45, ec=UPPER_FILL, lw=0.9)
        _fill(ax, s1["stair"]["polygon"], color=STAIR_FILL, ec=STAIR_FILL)
        kept = s1["roof"]["kept"]
        ax.set_title(f"{c['household_id']}\n{c['profile']} · {c['scheme_id']} · {w[s1['upper_placement']]}\n"
                     f"{w['roof']}: {w[str(kept)]} · {s1['stair']['stair_id']} {s1['stair']['area_sqft']:.0f} sq ft",
                     fontsize=6.5, color=INK, loc="left")
        ax.set_axis_on()
        ax.tick_params(labelsize=5, colors=MUTED)
        for spine in ax.spines.values():
            spine.set_color(GRID)
    s = lot["summary"].get("s1", {})
    header = f"{w['title']} — {lot['lot_id']}   {s.get('status_counts', {})}   {s.get('roof_kept_counts', {})}"
    if len(cells) > len(shown):
        header += f"   (+{len(cells) - len(shown)} {w['more']})"
    fig.text(0.01, 0.995, header, fontsize=9, color=INK, va="top")
    handles = [Patch(color=GROUND_FILL, label=w["ground"]), Patch(color=GARAGE_FILL, label=w["garage"]),
               Patch(color=UPPER_FILL, alpha=0.45, label=w["upper"]), Patch(color=STAIR_FILL, label=w["stair"])]
    fig.legend(handles=handles, loc="lower center", ncol=4, fontsize=7, frameon=False)
    fig.tight_layout(rect=(0, 0.03, 1, 0.97))
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=150, facecolor=SURFACE)
    plt.close(fig)
    return out


__all__ = ["WORDS", "plot_stack_sheet"]
