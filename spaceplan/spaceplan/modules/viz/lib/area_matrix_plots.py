"""Figures of the area analysis per lot (step 6.6): decision map, area budget per floor, IC-IO chart,
best scheme per household.

Split from visualize.py in refactor tanda 3 without changes.
"""

from __future__ import annotations

from pathlib import Path

SCHEME_ORDER = ("V0", "V1", "V2", "V3", "V4", "V5")
SCHEME_COLORS = {"V0": "#2a78d6", "V1": "#eb6834", "V2": "#1baf7a", "V3": "#eda100", "V4": "#e87ba4",
                 "V5": "#008300"}  # categorical slots 1-6 in fixed order (validated, light surface)
SCHEME_MARKERS = {"V0": "o", "V1": "s", "V2": "^", "V3": "D", "V4": "v", "V5": "P"}
STATUS_FILL = {"fits": "#0ca30c", "fits_small_garden": "#fab219", "exceeds_far": "#d03b3b",
               "exceeds_coverage": "#d03b3b", "upper_exceeds_ground": "#ec835a", "exceeds_strategy": "#ec835a",
               "frontage_short": "#ec835a", "site_fails": "#ec835a"}
STATUS_CODE = {"fits": "", "fits_small_garden": "J", "exceeds_far": "IC", "exceeds_coverage": "IO",
               "upper_exceeds_ground": "PA", "exceeds_strategy": "H", "frontage_short": "Fr", "site_fails": "S"}
INK, INK2, MUTED, GRID, SURFACE = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#fcfcfb"
EMPTY_FILL = "#f0efec"


def _fig_text(fig, lines, y0=0.975, size=12):
    for i, (text, kw) in enumerate(lines):
        fig.text(0.02, y0 - i * 0.03, text, color=kw.get("color", INK), fontsize=kw.get("size", size),
                 fontweight=kw.get("weight", "normal"), va="top")


def _lot_line(lot: dict, words: dict) -> str:
    b = lot["budget"]
    io = f"{b['io_max']:.2f}" if b["io_max"] is not None else "—"
    return (f"{words['lot']} {b['lot_area_sqft']:.0f} ft² · {words['ic']} máx. {b['ic_max']:.2f} "
            f"({b['far_gross_max_sqft']:.0f} ft²) · {words['io']} máx. {io} · "
            f"estrategias {'iguales' if b['strategies_equal'] else ', '.join(s['strategy_id'] + ' ' + format(s['area_sqft'], '.0f') for s in b['strategies'])}")


def plot_decision_map(lot: dict, cells: list[dict], out_path: str | Path, display: dict, lang: str) -> Path:
    """Households x (profile, scheme): colour = status, text = rank among feasible schemes or failure code."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch, Rectangle

    words = display["area_matrix"][lang]
    prof_words = display["sheet"][lang]["profiles"]
    households = list(dict.fromkeys(c["household_id"] for c in cells))
    profiles = list(dict.fromkeys(c["profile"] for c in cells))
    index = {(c["household_id"], c["profile"], c["scheme_id"]): c for c in cells}
    equiv = {(c["household_id"], c["profile"], e): c["scheme_id"] for c in cells for e in c["equivalent_schemes"]}
    ncol = len(profiles) * len(SCHEME_ORDER)
    fig = plt.figure(figsize=(3.2 + 0.36 * ncol + 0.3 * (len(profiles) - 1), 2.4 + 0.3 * len(households)))
    ax = fig.add_axes([0.17, 0.12, 0.81, 0.72])
    gap = 0.4
    for j, prof in enumerate(profiles):
        for k, sid in enumerate(SCHEME_ORDER):
            x = j * (len(SCHEME_ORDER) + gap) + k
            for i, hid in enumerate(households):
                c = index.get((hid, prof, sid))
                y = len(households) - 1 - i
                if c is None:
                    eq = equiv.get((hid, prof, sid))
                    ax.add_patch(Rectangle((x + 0.04, y + 0.04), 0.92, 0.92, color=EMPTY_FILL, lw=0))
                    if eq:
                        ax.text(x + 0.5, y + 0.5, f"={eq}", ha="center", va="center", fontsize=6.5, color=MUTED)
                    continue
                fill = STATUS_FILL[c["status"]]
                alpha = 1.0 if c["best"] else 0.45
                ax.add_patch(Rectangle((x + 0.04, y + 0.04), 0.92, 0.92, color=fill, alpha=alpha, lw=0))
                if c["best"]:
                    ax.add_patch(Rectangle((x + 0.04, y + 0.04), 0.92, 0.92, fill=False, ec=INK, lw=1.4))
                label = str(c["rank"]) if c["rank"] else STATUS_CODE[c["status"]]
                if c["status"] == "fits_small_garden" and c["rank"]:
                    label += "J"
                ax.text(x + 0.5, y + 0.5, label, ha="center", va="center", fontsize=7.5, color=INK,
                        fontweight="bold" if c["best"] else "normal")
        x0 = j * (len(SCHEME_ORDER) + gap)
        ax.text(x0 + len(SCHEME_ORDER) / 2, len(households) + 1.15, prof_words.get(prof, prof.replace("_", " ")),
                ha="center", va="bottom", fontsize=10, color=INK, fontweight="bold")
        for k, sid in enumerate(SCHEME_ORDER):
            ax.text(x0 + k + 0.5, len(households) + 0.2, sid, ha="center", va="bottom", fontsize=8, color=INK2)
    for i, hid in enumerate(households):
        ax.text(-0.3, len(households) - 1 - i + 0.5, hid.replace(".", " · "), ha="right", va="center", fontsize=8,
                color=INK)
    ax.set_xlim(-0.2, len(profiles) * (len(SCHEME_ORDER) + gap))
    ax.set_ylim(0, len(households) + 2)
    ax.axis("off")
    b = lot["budget"]
    _fig_text(fig, [(f"{words['decision_title']} · {b['lot_id']}", {"size": 14, "weight": "bold"}),
                    (_lot_line(lot, words), {"color": INK2, "size": 10})])
    st = words["statuses"]
    handles = [Patch(color=STATUS_FILL["fits"], label=st["fits"]),
               Patch(color=STATUS_FILL["fits_small_garden"], label=f"J = {st['fits_small_garden']}"),
               Patch(color=STATUS_FILL["exceeds_far"], label=f"IC / IO = {st['exceeds_far']} / {st['exceeds_coverage']}"),
               Patch(color=STATUS_FILL["site_fails"],
                     label=f"H, PA, Fr, S = {st['exceeds_strategy']}, {st['upper_exceeds_ground']}, "
                           f"{st['frontage_short']}, {st['site_fails']}"),
               Patch(color=EMPTY_FILL, label=f"{st['not_applicable']} (=Vx: equivalente)")]
    fig.legend(handles=handles, loc="lower left", ncol=3, fontsize=8, frameon=False, bbox_to_anchor=(0.02, 0.0))
    fig.text(0.98, 0.015, "número = rango del esquema (borde negro = mejor) · indicador provisional hasta 6.8",
             ha="right", fontsize=7.5, color=MUTED)
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=130, facecolor=SURFACE)
    plt.close(fig)
    return out


FOCUS_HOUSEHOLDS = ("empty_nest.anglo", "multigenerational.latino", "early_childhood.none", "teens_family.anglo")


def plot_area_budget(lot: dict, cells: list[dict], out_path: str | Path, display: dict, lang: str,
                     focus: tuple[str, ...] = FOCUS_HOUSEHOLDS, profiles: tuple[str, ...] = ("optimum", "maximum")
                     ) -> Path:
    """Land use (footprint, paving, open area = lot) and built area per floor against the IC limit."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch

    words = display["area_matrix"][lang]
    prof_words = display["sheet"][lang]["profiles"]
    rows = [c for hid in focus for prof in profiles for c in cells
            if c["household_id"] == hid and c["profile"] == prof and c["score"] is not None]
    rows.sort(key=lambda c: (focus.index(c["household_id"]), profiles.index(c["profile"]),
                             SCHEME_ORDER.index(c["scheme_id"])))
    b = lot["budget"]
    lot_area, gross_max = b["lot_area_sqft"], b["far_gross_max_sqft"]
    n = max(1, len(rows))
    height = 2.0 + 0.32 * n
    top = 1 - 1.15 / height
    fig = plt.figure(figsize=(15, height))
    ax1 = fig.add_axes([0.25, 0.55 / height, 0.36, top - 0.55 / height])
    ax2 = fig.add_axes([0.65, 0.55 / height, 0.30, top - 0.55 / height], sharey=ax1)
    c_ground, c_upper, c_pave, c_open = "#2a78d6", "#86b6ef", "#898781", "#1baf7a"
    ys = list(range(n))[::-1]
    for y, c in zip(ys, rows):
        paving = lot_area - c["ground_sqft"] - c["open_area_sqft"]
        ax1.barh(y, c["ground_sqft"], color=c_ground, height=0.62, edgecolor=SURFACE, lw=1)
        ax1.barh(y, paving, left=c["ground_sqft"], color=c_pave, height=0.62, edgecolor=SURFACE, lw=1)
        ax1.barh(y, c["open_area_sqft"], left=c["ground_sqft"] + paving, color=c_open, height=0.62,
                 edgecolor=SURFACE, lw=1)
        ax1.text(lot_area * 1.01, y, f"IO {c['IO']:.2f}", va="center", fontsize=8, color=INK2)
        ax2.barh(y, c["ground_sqft"], color=c_ground, height=0.62, edgecolor=SURFACE, lw=1)
        ax2.barh(y, c["upper_sqft"], left=c["ground_sqft"], color=c_upper, height=0.62, edgecolor=SURFACE, lw=1)
        tag = "" if c["status"] == "fits" else f" · {STATUS_CODE[c['status']] or c['status']}"
        star = " ★" if c["best"] else ""
        ax2.text(c["gross_sqft"] + gross_max * 0.01, y, f"IC {c['IC']:.2f}{star}{tag}", va="center", fontsize=8,
                 color=INK)
        ax1.text(-lot_area * 0.02, y, f"{c['household_id'].replace('.', ' · ')} · "
                 f"{prof_words.get(c['profile'], c['profile'])} · {c['scheme_id']}",
                 ha="right", va="center", fontsize=8, color=INK)
    ax2.axvline(gross_max, color="#d03b3b", lw=1.2, ls="--")
    ax2.text(gross_max, n - 0.3, f" {words['ic']} máx.", color="#d03b3b", fontsize=8, va="bottom")
    for ax in (ax1, ax2):
        ax.set_yticks([])
        for side in ("top", "right", "left"):
            ax.spines[side].set_visible(False)
        ax.spines["bottom"].set_color("#c3c2b7")
        ax.tick_params(colors=MUTED, labelsize=8)
        ax.grid(axis="x", color=GRID, lw=0.6)
        ax.set_axisbelow(True)
    ax1.set_xlim(0, lot_area * 1.12)
    ax2.set_xlim(0, gross_max * 1.25)
    ax1.set_xlabel(f"{words['lot']} (ft²)", color=INK2, fontsize=9)
    ax2.set_xlabel("ft² construidos" if lang == "es" else "built sq ft", color=INK2, fontsize=9)
    ax1.set_title("Uso del suelo" if lang == "es" else "Land use", fontsize=10, color=INK, loc="left")
    ax2.set_title("Área construida por piso" if lang == "es" else "Built area per floor", fontsize=10, color=INK,
                  loc="left")
    _fig_text(fig, [(f"{words['budget_title']} · {b['lot_id']}", {"size": 14, "weight": "bold"}),
                    (_lot_line(lot, words), {"color": INK2, "size": 10})], y0=0.985)
    fig.legend(handles=[Patch(color=c_ground, label=words["ground"]), Patch(color=c_upper, label=words["upper"]),
                        Patch(color=c_pave, label=words["paving"]), Patch(color=c_open, label=words["open_area"])],
               loc="upper right", ncol=4, fontsize=8.5, frameon=False, bbox_to_anchor=(0.98, 0.99))
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=130, facecolor=SURFACE)
    plt.close(fig)
    return out


def plot_ic_io(lot: dict, cells: list[dict], out_path: str | Path, display: dict, lang: str) -> Path:
    """Every cell as a point (IC, IO): the indices' limits as lines; one floor sits on the diagonal."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    words = display["area_matrix"][lang]
    b = lot["budget"]
    fig, ax = plt.subplots(figsize=(9, 7.2))
    fig.subplots_adjust(top=0.84, left=0.1, right=0.97, bottom=0.1)
    hi = max([c["IC"] for c in cells] + [b["ic_max"]]) * 1.08
    ax.plot([0, hi], [0, hi], color="#c3c2b7", lw=1, zorder=1)
    ax.text(hi * 0.97, hi * 0.97, "1 piso (IO = IC)" if lang == "es" else "1 floor (IO = IC)", ha="right",
            va="bottom", fontsize=8, color=MUTED, rotation=37)
    for sid in SCHEME_ORDER:
        sub = [c for c in cells if c["scheme_id"] == sid]
        if not sub:
            continue
        ok = [c for c in sub if c["score"] is not None]
        bad = [c for c in sub if c["score"] is None]
        ax.scatter([c["IC"] for c in ok], [c["IO"] for c in ok], s=34, marker=SCHEME_MARKERS[sid],
                   color=SCHEME_COLORS[sid], edgecolor=SURFACE, lw=0.8, zorder=3, label=f"{sid}")
        ax.scatter([c["IC"] for c in bad], [c["IO"] for c in bad], s=34, marker=SCHEME_MARKERS[sid],
                   facecolor="none", edgecolor=SCHEME_COLORS[sid], lw=1.0, zorder=2)
    ax.axvline(b["ic_max"], color="#d03b3b", lw=1.2, ls="--")
    ax.text(b["ic_max"], hi * 0.02, f" {words['ic']} máx. {b['ic_max']:.2f}", color="#d03b3b", fontsize=8)
    if b["io_max"] is not None:
        ax.axhline(b["io_max"], color="#d03b3b", lw=1.2, ls="--")
        ax.text(hi * 0.02, b["io_max"] + hi * 0.005, f"{words['io']} máx. {b['io_max']:.2f} (131.0445)",
                color="#d03b3b", fontsize=8, va="bottom")
    ax.set_xlim(0, hi)
    ax.set_ylim(0, hi)
    ax.set_xlabel(f"{words['ic']} — índice de construcción (área construida / lote)" if lang == "es"
                  else "IC — construction index", color=INK2)
    ax.set_ylabel(f"{words['io']} — índice de ocupación (huella / lote)" if lang == "es"
                  else "IO — occupancy index", color=INK2)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.grid(color=GRID, lw=0.6)
    ax.set_axisbelow(True)
    ax.tick_params(colors=MUTED, labelsize=8)
    handles, names = ax.get_legend_handles_labels()
    ax.legend(handles, names, title="Esquema (relleno = factible)" if lang == "es" else "Scheme (filled = feasible)",
              fontsize=8, title_fontsize=8, frameon=False, loc="lower right", bbox_to_anchor=(0.9, 0.0))
    fig.text(0.02, 0.97, f"IC vs IO · {b['lot_id']}", fontsize=14, fontweight="bold", color=INK, va="top")
    fig.text(0.02, 0.92, _lot_line(lot, words), fontsize=9, color=INK2, va="top")
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=130, facecolor=SURFACE)
    plt.close(fig)
    return out


METRIC_ABBR = {"open_area": "AL", "stair_independence": "Esc", "supervision": "Sup", "separation": "Sep",
               "upper_efficiency": "PA", "frontage": "Fr", "cost": "Cos", "only_feasible": "único"}


def plot_scheme_matrix(result: dict, out_path: str | Path, display: dict, lang: str,
                       profiles: tuple[str, ...] = ("optimum", "maximum")) -> Path:
    """Best vertical scheme per household (rows) and lot (columns), with the metric that decides it."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch, Rectangle

    words = display["area_matrix"][lang]
    prof_words = display["sheet"][lang]["profiles"]
    lots = [lot["budget"]["lot_id"] for lot in result["lots"]]
    households = list(dict.fromkeys(c["household_id"] for c in result["cells"]))
    best = {(c["lot_id"], c["household_id"], c["profile"]): c for c in result["cells"] if c["best"]}
    fig, axes = plt.subplots(1, len(profiles), figsize=(4 + 1.15 * len(lots) * len(profiles), 2.6 + 0.3 * len(households)))
    fig.subplots_adjust(left=0.13, right=0.99, top=0.86, bottom=0.12, wspace=0.05)
    axes = list(axes) if len(profiles) > 1 else [axes]
    for ax, prof in zip(axes, profiles):
        for j, lid in enumerate(lots):
            for i, hid in enumerate(households):
                y = len(households) - 1 - i
                c = best.get((lid, hid, prof))
                if c is None:
                    ax.add_patch(Rectangle((j + 0.04, y + 0.06), 0.92, 0.88, color=EMPTY_FILL, lw=0))
                    ax.text(j + 0.5, y + 0.5, "—", ha="center", va="center", fontsize=8, color=MUTED)
                    continue
                ax.add_patch(Rectangle((j + 0.04, y + 0.06), 0.92, 0.88, color=SCHEME_COLORS[c["scheme_id"]],
                                       alpha=0.85, lw=0))
                ax.text(j + 0.5, y + 0.5, f"{c['scheme_id']} · {METRIC_ABBR.get(c.get('decisive_metric'), '')}",
                        ha="center", va="center", fontsize=7.5, color=INK)
            ax.text(j + 0.5, len(households) + 0.15, lid.replace("-", "\n", 1), ha="center", va="bottom",
                    fontsize=7, color=INK2)
        ax.set_xlim(0, len(lots))
        ax.set_ylim(0, len(households) + 1.4)
        ax.axis("off")
        ax.set_title(prof_words.get(prof, prof), fontsize=11, color=INK, fontweight="bold", pad=18)
        if ax is axes[0]:
            for i, hid in enumerate(households):
                ax.text(-0.08, len(households) - 1 - i + 0.5, hid.replace(".", " · "), ha="right", va="center",
                        fontsize=8, color=INK)
    fig.text(0.01, 0.975, words["scheme_title"], fontsize=14, fontweight="bold", color=INK, va="top")
    labels = {"V0": "Un piso", "V1": "Privada arriba", "V2": "Suite principal abajo", "V3": "Dos generaciones",
              "V4": "Planta alta parcial", "V5": "Social arriba"}
    fig.legend(handles=[Patch(color=SCHEME_COLORS[s], label=f"{s} {labels[s]}") for s in SCHEME_ORDER],
               loc="lower left", ncol=6, fontsize=8, frameon=False, bbox_to_anchor=(0.01, 0.0))
    fig.text(0.99, 0.02, "texto = esquema · métrica decisiva (AL área libre, Esc escalera, Sup supervisión, "
             "Sep separación, PA planta alta, Cos costo índice)", ha="right", fontsize=7.5, color=MUTED)
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=130, facecolor=SURFACE)
    plt.close(fig)
    return out
