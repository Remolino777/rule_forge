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
BOTTOM_EDGE, TOP_EDGE, HALF_BATH_FILL, VESTIBULE_EDGE = "#008300", "#a8467a", "#2a78d6", "#2a78d6"
DOOR_FILL, ENTRY_EDGE, VOID_EDGE = "#d03b3b", "#d03b3b", "#52514e"
SLIDER_EDGE, DECK_FILL, DRIVE_FILL, WALK_FILL, GREEN_FILL = "#2a78d6", "#d9b98c", "#bdbbb4", "#e6e2d6", "#cfe3c4"
WORDS = {
    "es": {"title": "Plantas apiladas (6.7a S1)", "ground": "Planta baja", "upper": "Planta alta",
           "garage": "Garaje", "stair": "Escalera", "envelope": "Envolvente de retiros", "roof": "techo",
           "default": "por defecto", "rotated": "cumbrera girada", "flat": "plano", "None": "plano manda",
           "rear": "atrás", "front": "adelante", "over_garage": "sobre garaje", "compact": "compacta", "compact_bands": "dos bandas", "more": "celdas más no mostradas",
           "bottom": "Arranque", "top": "Llegada", "half_bath": "Medio baño bajo escalera",
           "hall": "pasillo", "upper_vestibule": "vestíbulo", "straight": "recta", "straight_landing": "recta c/descanso",
           "l_turn": "L", "u_turn": "U", "u_well": "U c/vacío", "door": "Puerta principal y vestíbulo",
           "void": "Vacío", "strategy": "estrategia"},
    "en": {"title": "Stacked plans (6.7a S1)", "ground": "Ground floor", "upper": "Upper floor",
           "garage": "Garage", "stair": "Stair", "envelope": "Setback envelope", "roof": "roof",
           "default": "default", "rotated": "ridge turned", "flat": "flat", "None": "plane governs",
           "rear": "rear", "front": "front", "over_garage": "over garage", "compact": "compact", "compact_bands": "two bands", "more": "more cells not shown",
           "bottom": "Stair start", "top": "Stair arrival", "half_bath": "Half bath under stair",
           "hall": "hall", "upper_vestibule": "vestibule", "straight": "straight", "straight_landing": "straight+landing",
           "l_turn": "L", "u_turn": "U", "u_well": "U with void", "door": "Main door and vestibule",
           "void": "Void", "strategy": "strategy"},
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


def _access(ax, s1: dict, level: int) -> None:
    """Stage S1.2 access core: main door, swing and vestibule on the ground floor; the void on the upper floor."""
    acc = s1.get("access_core") or {}
    if level == 0:
        _line(ax, acc.get("vestibule"), color=ENTRY_EDGE, lw=0.6, ls="--")
        _line(ax, acc.get("swing"), color=ENTRY_EDGE, lw=0.4, ls=":")
        _fill(ax, acc.get("door"), color=DOOR_FILL, ec=DOOR_FILL, lw=0.8)
    _fill(ax, acc.get("void"), color="#ffffff", ec=VOID_EDGE, lw=0.6, hatch="xx")


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
        _access(ax, s1, 0)
        _access(ax, s1, 1)
        core = s1.get("stair_core")
        if core:
            us = core["under_stair"]
            _fill(ax, us.get("half_bath"), color=HALF_BATH_FILL, alpha=0.55, ec=HALF_BATH_FILL, lw=0.6)
            _line(ax, us.get("vestibule"), color=VESTIBULE_EDGE, lw=0.6, ls=":")
            _line(ax, core["bottom_end"]["zone"], color=BOTTOM_EDGE, lw=1.0)
            _line(ax, core["top_end"]["zone"], color=TOP_EDGE, lw=1.0, ls="--")
            (b0, b1), (t0, t1) = core["bottom_end"]["edge"], core["top_end"]["edge"]
            bx, by = (b0[0] + b1[0]) / 2, (b0[1] + b1[1]) / 2
            tx, ty = (t0[0] + t1[0]) / 2, (t0[1] + t1[1]) / 2
            ax.annotate("", xy=(tx, ty), xytext=(bx, by),
                        arrowprops={"arrowstyle": "->", "color": "#ffffff", "lw": 0.8})
        kept = s1["roof"]["kept"]
        top_rec = w.get(core["top_end"]["receiving"]["receiving"], "") if core else ""
        acc = s1.get("access_core") or {}
        if acc.get("strategy"):
            top_rec += f" · {w['strategy']} {acc['strategy']}{' *' if acc.get('provisional') else ''}"
        ax.set_title(f"{c['household_id']}\n{c['profile']} · {c['scheme_id']} · {w[s1['upper_placement']]}\n"
                     f"{w['roof']}: {w[str(kept)]} · {w.get(s1['stair']['stair_id'], s1['stair']['stair_id'])} "
                     f"→ {top_rec}", fontsize=6.5, color=INK, loc="left")
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
               Patch(color=UPPER_FILL, alpha=0.45, label=w["upper"]), Patch(color=STAIR_FILL, label=w["stair"]),
               Patch(fill=False, ec=BOTTOM_EDGE, label=w["bottom"]), Patch(fill=False, ec=TOP_EDGE, ls="--", label=w["top"]),
               Patch(color=HALF_BATH_FILL, alpha=0.55, label=w["half_bath"]),
               Patch(fill=False, ec=DOOR_FILL, ls="--", label=w["door"]),
               Patch(fill=False, ec=VOID_EDGE, hatch="xx", label=w["void"])]
    fig.legend(handles=handles, loc="lower center", ncol=9, fontsize=7, frameon=False)
    fig.tight_layout(rect=(0, 0.03, 1, 0.97))
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=150, facecolor=SURFACE)
    plt.close(fig)
    return out


# ------------------------------------------------------------------ stage S2: zones around the stair core

S2_WORDS = {
    "es": {"title": "Zonificación alrededor de la escalera (6.7a S2)", "ground": "Planta baja", "upper": "Planta alta",
           "option": "arranque", "arrival": "llegada", "family_room": "family room", "hall": "pasillo",
           "upper_vestibule": "vestíbulo", "relocated": "medio baño reubicado", "under_stair": "medio baño bajo escalera",
           "None": "sin medio baño", "strategy": "estrategia", "more": "celdas más no mostradas", "stair": "Escalera",
           "garage": "Garaje", "start": "Arranque", "top": "Llegada"},
    "en": {"title": "Zoning around the stair core (6.7a S2)", "ground": "Ground floor", "upper": "Upper floor",
           "option": "start", "arrival": "arrival", "family_room": "family room", "hall": "hall",
           "upper_vestibule": "vestibule", "relocated": "half bath relocated", "under_stair": "half bath under stair",
           "None": "no half bath", "strategy": "strategy", "more": "more cells not shown", "stair": "Stair",
           "garage": "Garage", "start": "Stair start", "top": "Stair arrival"},
}


def _zone_panel(ax, floor_poly, units, colors, stair, landing, garage=None, extra=None):
    _fill(ax, floor_poly, color="#ffffff", ec=INK2, lw=0.6)
    for u in units:
        _fill(ax, u["polygon"], color=colors.get(u["zone"], "#eeeeee"), ec="#ffffff", lw=1.0)
        ring = _rings(u["polygon"])
        if ring:
            xs, ys = zip(*ring[0])
            ax.text(sum(xs[:-1]) / (len(xs) - 1), sum(ys[:-1]) / (len(ys) - 1), u["unit_id"].replace(":", " "),
                    fontsize=4.5, color=INK, ha="center", va="center")
    if garage:
        _fill(ax, garage, color=GARAGE_FILL, ec=INK2, lw=0.5, hatch="///")
    for poly in extra or []:
        _fill(ax, poly, color=HALF_BATH_FILL, alpha=0.7, ec=HALF_BATH_FILL, lw=0.5)
    _fill(ax, stair, color=STAIR_FILL, ec=STAIR_FILL)
    _line(ax, landing[0], color=landing[1], lw=1.1)
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_color(GRID)


def plot_zoning_sheet(lot: dict, cells: list[dict], out_path: str | Path, colors: dict[str, str], lang: str = "es",
                      max_cells: int = 12) -> Path:
    """One sheet per lot: for each zoned cell, the ground floor of the chosen start option and the upper floor."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch

    w = S2_WORDS.get(lang, S2_WORDS["en"])
    shown = cells[:max_cells]
    ncol = 4                                     # two cells per row, two panels each
    nrow = max(1, math.ceil(len(shown) / 2))
    fig, axes = plt.subplots(nrow, ncol, figsize=(2.4 * ncol, 2.9 * nrow + 0.8), squeeze=False)
    fig.patch.set_facecolor(SURFACE)
    for ax in axes.flat:
        ax.set_axis_off()
    for k, c in enumerate(shown):
        s1, s2 = c["s1"], c["s2"]
        opt = s2["options"][s2["chosen_option"]]
        core = s1["stair_core"]
        ax_g, ax_u = axes.flat[2 * k], axes.flat[2 * k + 1]
        for ax in (ax_g, ax_u):
            ax.set_axis_on()
        hb = [core["under_stair"].get("half_bath"), core["under_stair"].get("vestibule")] \
            if opt.get("half_bath") == "under_stair" else []
        _zone_panel(ax_g, s1["levels"][0]["polygon"], opt["ground"]["units"], colors, s1["stair"]["polygon"],
                    (core["bottom_end"]["zone"], BOTTOM_EDGE), s1["ground"].get("garage_polygon"), hb)
        _zone_panel(ax_u, s1["levels"][1]["polygon"], s2["upper"]["units"], colors, s1["stair"]["polygon"],
                    (core["top_end"]["zone"], TOP_EDGE))
        _access(ax_g, s1, 0)
        _access(ax_u, s1, 1)
        chosen = (s2.get("stair_choice") or {}).get("chosen") or {}
        tag = f" · {w['strategy']} {chosen['strategy']} ({chosen.get('light')})" if chosen else ""
        ax_g.set_title(f"{c['household_id']} · {c['profile']} · {c['scheme_id']}\n{w['ground']}: {w['option']} "
                       f"{s2['chosen_option']} ({'/'.join(s2['feasible_options'])}) · {w[str(opt.get('half_bath'))]}",
                       fontsize=5.5, color=INK, loc="left")
        ax_u.set_title(f"score {s2['score']:.2f}{tag}\n{w['upper']}: {w['arrival']} "
                       f"{w[s2['arrival']['receiving']]}", fontsize=5.5, color=INK, loc="left")
    s = lot["summary"].get("s2", {})
    header = f"{w['title']} — {lot['lot_id']}   {s.get('status_counts', {})}   {s.get('chosen_option_counts', {})}"
    if len(cells) > len(shown):
        header += f"   (+{len(cells) - len(shown)} {w['more']})"
    fig.text(0.01, 0.995, header, fontsize=8, color=INK, va="top")
    zones = sorted({u["zone"] for c in shown for f in (c["s2"]["upper"], c["s2"]["options"][c["s2"]["chosen_option"]]["ground"])
                    for u in f["units"]})
    handles = [Patch(color=colors.get(z, "#eeeeee"), label=z) for z in zones]
    handles += [Patch(color=STAIR_FILL, label=w["stair"]), Patch(color=GARAGE_FILL, label=w["garage"]),
                Patch(fill=False, ec=BOTTOM_EDGE, label=w["start"]), Patch(fill=False, ec=TOP_EDGE, label=w["top"])]
    fig.legend(handles=handles, loc="lower center", ncol=len(handles), fontsize=6.5, frameon=False)
    fig.tight_layout(rect=(0, 0.03, 1, 0.97))
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=170, facecolor=SURFACE)
    plt.close(fig)
    return out


S21_WORDS = {
    "es": {"title": "Espacios y puertas (6.7a S2.1)", "ground": "Planta baja", "upper": "Planta alta",
           "stair": "Escalera", "garage": "Garaje", "door": "Puerta (giro)", "opening": "Vano",
           "closet": "Clóset de sobrante", "more": "celdas más no mostradas", "rank": "escalera n.º",
           "built_in": "clósets integrados", "slider": "Corrediza / vidrio", "deck": "Deck y rellano",
           "driveway": "Entrada vehicular", "walkway": "Sendero", "garden": "Jardín",
           "cantilever": "voladizo"},
    "en": {"title": "Spaces and doors (6.7a S2.1)", "ground": "Ground floor", "upper": "Upper floor",
           "stair": "Stair", "garage": "Garage", "door": "Door (swing)", "opening": "Opening",
           "closet": "Leftover closet", "more": "more cells not shown", "rank": "stair rank",
           "built_in": "built-in closets", "slider": "Slider / glass", "deck": "Deck and landing",
           "driveway": "Driveway", "walkway": "Walkway", "garden": "Garden", "cantilever": "cantilever"},
}
SHORT = {"primary_suite": "suite", "primary_bath": "bath P", "walk_in_closet": "w-i cl", "bedroom": "bed",
         "bathroom": "bath", "living_room": "living", "dining_room": "dining", "family_room": "family",
         "breakfast_nook": "nook", "laundry_closet": "laundry cl", "half_bath": "½ bath", "entry_vestibule": "entry",
         "vestibule": "vest", "flex_room": "flex", "mechanical": "mech", "living_dining": "liv-din"}


def _site_panel(ax, site: dict | None) -> None:
    """Front yard of stage S2.1b: garden, driveway, walkway and the covered entry deck; main door and sidelight."""
    if not site or site.get("status") != "laid_out":
        return
    _fill(ax, site.get("garden"), color=GREEN_FILL, ec="none")
    _fill(ax, site.get("driveway"), color=DRIVE_FILL, ec="none")
    _fill(ax, site.get("walkway"), color=WALK_FILL, ec="none")
    _fill(ax, site.get("entry_deck"), color=DECK_FILL, ec=INK2, lw=0.4)
    me = site.get("main_entry") or {}
    for key, color, lw in (("leaf", DOOR_FILL, 1.4), ("sidelight", SLIDER_EDGE, 1.4)):
        if me.get(key):
            xs, ys = zip(*me[key])
            ax.plot(xs, ys, color=color, lw=lw, solid_capstyle="butt")


def _space_panel(ax, floor_poly, block, colors, stair, s1, level, garage=None, site=None):
    if level == 0:
        _site_panel(ax, site)
    _fill(ax, floor_poly, color="#ffffff", ec=INK2, lw=0.6)
    for oa in block.get("open_air") or []:               # S2.2d: lower roof (hatched) and terrace (deck)
        if oa["kind"] == "terrace":
            _fill(ax, oa["polygon"], color=DECK_FILL, ec=INK2, lw=0.4)
        else:
            _fill(ax, oa["polygon"], color="#e7e5df", ec=INK2, lw=0.4, hatch="\\\\\\")
    for sp in block["spaces"]:
        if sp["space_type"].startswith("garage"):
            _fill(ax, sp["polygon"], color=GARAGE_FILL, ec=INK2, lw=0.5, hatch="///")
            continue
        color = colors.get(sp["zone"], "#eeeeee") if not sp["fixed"] else "#f3f2ee"
        hatch = "...." if sp["synthetic"] and sp["space_type"] == "closet" else None
        _fill(ax, sp["polygon"], color=color, ec=INK, lw=0.5, hatch=hatch)
        ring = _rings(sp["polygon"])
        if ring and sp["area_sqft"] >= 20:
            xs, ys = zip(*ring[0])
            ax.text(sum(xs[:-1]) / (len(xs) - 1), sum(ys[:-1]) / (len(ys) - 1),
                    f"{SHORT.get(sp['space_type'], sp['space_type'])}\n{sp['area_sqft']:.0f}", fontsize=3.6,
                    color=INK, ha="center", va="center")
    _fill(ax, stair, color=STAIR_FILL, ec=STAIR_FILL)
    _access(ax, s1, level)
    for d in block["doors"]:
        seg = d.get("segment")
        if not seg:
            continue
        xs, ys = zip(*seg)
        ax.plot(xs, ys, color="#ffffff", lw=1.6, solid_capstyle="butt")
        if d["kind"] == "opening":                     # a cased opening: dashed, so it reads between two halls
            ax.plot(xs, ys, color=INK2, lw=0.5, ls=(0, (1.2, 1.2)))
        elif d["kind"] in ("closet_slider", "patio_slider"):
            ax.plot(xs, ys, color=SLIDER_EDGE, lw=0.9 if d["kind"] == "patio_slider" else 0.6)
        else:
            _line(ax, d.get("swing"), color=DOOR_FILL, lw=0.45)
    ex = block.get("patio_exit")
    if ex:
        _fill(ax, ex.get("landing"), color=DECK_FILL, ec=INK2, lw=0.4)
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_color(GRID)


def plot_space_sheet(lot: dict, cells: list[dict], out_path: str | Path, colors: dict[str, str], lang: str = "es",
                     max_cells: int = 8) -> Path:
    """One sheet per lot: for each spaced cell (stage S2.1), both floors with spaces, doors and swings."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch

    w = S21_WORDS.get(lang, S21_WORDS["en"])
    shown = cells[:max_cells]
    ncol = 4
    nrow = max(1, math.ceil(len(shown) / 2))
    fig, axes = plt.subplots(nrow, ncol, figsize=(3.2 * ncol, 3.6 * nrow + 0.8), squeeze=False)
    fig.patch.set_facecolor(SURFACE)
    for ax in axes.flat:
        ax.set_axis_off()
    for k, c in enumerate(shown):
        s1, s21 = c["s1"], c["s21"]
        ax_g, ax_u = axes.flat[2 * k], axes.flat[2 * k + 1]
        for ax in (ax_g, ax_u):
            ax.set_axis_on()
        _space_panel(ax_g, s1["levels"][0]["polygon"], s21["ground"], colors, s1["stair"]["polygon"], s1, 0,
                     site=s21.get("site"))
        _space_panel(ax_u, s1["levels"][1]["polygon"], s21["upper"], colors, s1["stair"]["polygon"], s1, 1)
        built = len(s21["ground"].get("closets_in_rooms", [])) + len(s21["upper"].get("closets_in_rooms", []))
        ax_g.set_title(f"{c['household_id']} · {c['profile']} · {c['scheme_id']}\n{w['ground']} · "
                       f"{w['rank']} {s21.get('stair_rank', 0)}", fontsize=6, color=INK, loc="left")
        cant = f" · {w['cantilever']}" if s1.get("upper_placement") == "cantilever_rear" else ""
        ax_u.set_title(f"score {s21['score']:.2f} · {w['built_in']} {built}{cant}\n{w['upper']}", fontsize=6,
                       color=INK, loc="left")
    s = lot["summary"].get("s21", {})
    header = f"{w['title']} — {lot['lot_id']}   {s.get('status_counts', {})}"
    if len(cells) > len(shown):
        header += f"   (+{len(cells) - len(shown)} {w['more']})"
    fig.text(0.01, 0.995, header, fontsize=8, color=INK, va="top")
    zones = sorted({sp["zone"] for c in shown for f in ("ground", "upper") for sp in c["s21"][f]["spaces"]
                    if not sp["fixed"]})
    handles = [Patch(color=colors.get(z, "#eeeeee"), label=z) for z in zones]
    handles += [Patch(color=STAIR_FILL, label=w["stair"]), Patch(color=GARAGE_FILL, label=w["garage"]),
                Patch(fill=False, hatch="....", label=w["closet"]),
                Line2D([0], [0], color=DOOR_FILL, lw=0.8, label=w["door"]),
                Line2D([0], [0], color=SLIDER_EDGE, lw=0.9, label=w["slider"]),
                Line2D([0], [0], color=INK2, lw=0.6, ls=(0, (1.2, 1.2)), label=w["opening"]),
                Patch(color=DECK_FILL, label=w["deck"]), Patch(color=DRIVE_FILL, label=w["driveway"]),
                Patch(color=WALK_FILL, label=w["walkway"]), Patch(color=GREEN_FILL, label=w["garden"])]
    fig.legend(handles=handles, loc="lower center", ncol=min(len(handles), 9), fontsize=6.5, frameon=False)
    fig.tight_layout(rect=(0, 0.05, 1, 0.97))
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=200, facecolor=SURFACE)
    plt.close(fig)
    return out


__all__ = ["S21_WORDS", "S2_WORDS", "WORDS", "plot_space_sheet", "plot_stack_sheet", "plot_zoning_sheet"]
