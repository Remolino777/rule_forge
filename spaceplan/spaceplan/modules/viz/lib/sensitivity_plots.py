"""Figure of the normative sensitivity (2026-10-09): two single-hue heat maps, lots x FOS and lots x FOT.

Left: share of the households' complete programs that do not fit one floor (two floors or more), as the design FOS
changes (SDMC FOT).
Right: share of complete programs that no two-floor house holds (beyond the maximum, or no balanced split inside the
footprint, step 9a), as a fixed FOT changes (base FOS); the SDMC FOT of each lot is marked. Magnitude is sequential (one hue, light to dark); values are written in the cells.
"""

from __future__ import annotations

import math
from pathlib import Path

INK, INK2, MUTED, SURFACE = "#0b0b0b", "#52514e", "#898781", "#fcfcfb"
WORDS = {
    "es": {"title": "Sensibilidad normativa: FOS de diseño y FOT", "left": "Programas completos que no caben en 1 piso",
           "right": "Programas completos que no caben en 2 pisos", "fos": "FOS de diseño (sobre {base}, FOT del SDMC)",
           "fot": "FOT fijo (FOS {fos:g} sobre {base}); | = FOT del SDMC del lote", "envelope": "envolvente",
           "lot": "lote"},
    "en": {"title": "Normative sensitivity: design FOS and FOT", "left": "Complete programs that do not fit one floor",
           "right": "Complete programs no two-floor house holds", "fos": "design FOS (on {base}, SDMC FOT)",
           "fot": "fixed FOT (FOS {fos:g} on {base}); | = SDMC FOT of the lot", "envelope": "envelope", "lot": "lot"},
}


def _matrix(rows, lots, key, xs, value):
    return [[next((r[value] for r in rows if r["lot_id"] == lot and abs(r[key] - x) < 1e-9), float("nan"))
             for x in xs] for lot in lots]


def plot_sensitivity(result: dict, out_path: str | Path, lang: str = "es") -> Path:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    w = WORDS.get(lang, WORDS["en"])
    dv = result["meta"]["design_variables"]
    lots = result["meta"]["lots"]
    fos_rows = [r for r in result["rows"] if r["sweep"] == "fos"]
    fot_rows = [r for r in result["rows"] if r["sweep"] == "fot"]
    fos_x = sorted({r["fos"] for r in fos_rows})
    fot_x = sorted({r["fot"] for r in fot_rows})
    left = [[None if math.isnan(v) else round(1.0 - v, 4) for v in row]
            for row in _matrix(fos_rows, lots, "fos", fos_x, "complete_one_floor_share")]
    right = [[a + b for a, b in zip(ra, rb)]  # step 9a: no area, or no balanced split
             for ra, rb in zip(_matrix(fot_rows, lots, "fot", fot_x, "complete_exceeds_share"),
                               _matrix(fot_rows, lots, "fot", fot_x, "complete_split_fails_share"))]
    sdmc = {r["lot_id"]: r["fot"] for r in fos_rows}

    fig, axes = plt.subplots(1, 2, figsize=(15, 0.42 * len(lots) + 2.2),
                             gridspec_kw={"width_ratios": [len(fos_x), len(fot_x)]})
    fig.patch.set_facecolor(SURFACE)
    base = w[dv["fos_base"]]
    for ax, mat, xs, title, xlabel in ((axes[0], left, fos_x, w["left"], w["fos"].format(base=base)),
                                        (axes[1], right, fot_x, w["right"],
                                         w["fot"].format(fos=dv["fos"], base=base))):
        ax.imshow(mat, cmap="Blues", vmin=0.0, vmax=1.0, aspect="auto")
        ax.set_xticks(range(len(xs)), [f"{x:.2f}" for x in xs], fontsize=7, color=INK2, rotation=90)
        ax.set_yticks(range(len(lots)), lots, fontsize=8, color=INK2)
        ax.set_title(title, fontsize=10, color=INK, loc="left")
        ax.set_xlabel(xlabel, fontsize=8, color=INK2)
        for i, row in enumerate(mat):
            for j, v in enumerate(row):
                if v is not None and not math.isnan(v) and v > 0:
                    ax.text(j, i, f"{v:.0%}", ha="center", va="center", fontsize=6,
                            color=SURFACE if v > 0.55 else INK)
        for spine in ax.spines.values():
            spine.set_visible(False)
        ax.tick_params(length=0)
    for i, lot in enumerate(lots):
        f = sdmc.get(lot)
        if f is not None and fot_x:
            j = (f - fot_x[0]) / ((fot_x[-1] - fot_x[0]) / max(1, len(fot_x) - 1))
            axes[1].plot([j, j], [i - 0.45, i + 0.45], color=INK, lw=1.5)
    fig.suptitle(w["title"], x=0.01, ha="left", fontsize=12, color=INK)
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=140, facecolor=SURFACE)
    plt.close(fig)
    return out


__all__ = ["WORDS", "plot_sensitivity"]
