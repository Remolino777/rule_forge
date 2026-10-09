"""Portfolio sheet of program profiles (step 6.5d): quality vs relative cost curve and summary table.

Split from visualize.py in refactor tanda 3 without changes.
"""

from __future__ import annotations

from pathlib import Path


def move_label(move: str, labels: dict) -> str:
    """Display text of an expansion move ('add:pantry:general', 'substitute:split_social', 'size:social', 'car:2')."""
    kind, arg = move.split(":", 1)
    moves = labels.get("moves", {})
    if kind == "substitute":
        return moves.get("substitute", {}).get(arg, arg.replace("_", " "))
    if kind == "size":
        return moves.get("size", "{zone}").format(zone=labels["zones"].get(arg, arg).lower())
    if kind == "car":
        return moves.get("car", "{n}").format(n=arg)
    space_type, role = arg.split(":")
    text = labels["space_types"].get(space_type, space_type)
    role_text = labels["household_roles"].get(role, "")
    return f"{text} {role_text}".strip() if role_text and role_text.lower() not in text.lower() else text


def plot_portfolio_sheet(portfolio: dict, out_path: str | Path, display: dict, lang: str) -> None:
    """Quality vs relative cost curve with the profiles marked, ceilings and a summary table."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    words = display["sheet"][lang]
    fig = plt.figure(figsize=(16.5, 8.5))
    ax = fig.add_axes([0.06, 0.12, 0.45, 0.72])
    curve = portfolio["curve"]
    xs, ys = [p["index"] for p in curve], [p["quality"] for p in curve]
    ax.plot(xs, ys, color="#2a78d6", lw=2, marker="o", ms=4, zorder=3)
    marks = {"minimum": ("#6d6d6d", "s"), "optimum": ("#eb6834", "*"), "maximum": ("#1b5e20", "D")}
    for name, (color, marker) in marks.items():
        p = portfolio["profiles"][name]
        ax.scatter([p["index"]], [p["quality"]], s=220 if marker == "*" else 90, color=color, marker=marker, zorder=5,
                   label=words["profiles"][name])
    acc = portfolio["profiles"].get("accessible")
    if acc:
        ax.scatter([acc["index"]], [acc["quality"]], s=90, color="#6a1b9a", marker="^", zorder=5,
                   label=words["profiles"]["accessible"])
    staged = portfolio["profiles"].get("staged")
    if staged:
        ax.scatter([staged["index_total"]], [staged["final"]["quality"] if staged["target_stage"] == "current"
                                             else portfolio["profiles"]["optimum"]["quality"]],
                   s=90, facecolor="none", edgecolor="#e34948", lw=2, marker="o", zorder=5,
                   label=f"{words['profiles']['staged']} (total)")
    ceilings = portfolio["ceilings"]
    if ceilings.get("budget_fraction") is not None:
        ax.axvline(ceilings["budget_fraction"], color="#e34948", ls="--", lw=1.2)
        ax.text(ceilings["budget_fraction"], 0.02, f" {words['budget']} {ceilings['budget_fraction']:g}",
                color="#e34948", fontsize=9)
    if portfolio["reading"] == "lot" and portfolio["model"] == "base":
        ax.axvline(1.0, color="#424242", ls=":", lw=1.2)
        ax.text(1.0, 0.08, " FAR", fontsize=9)
    labels = display["labels"][lang]
    for p in curve[1:]:
        ax.annotate(move_label(p["move"], labels), (p["index"], p["quality"]),
                    textcoords="offset points", xytext=(4, -9), fontsize=6.5, color="#555")
    ax.set_xlabel(words["curve_x"])
    ax.set_ylabel(words["curve_y"])
    ax.set_ylim(-0.02, 1.08)
    ax.grid(color="#e1e0d9", lw=0.8)
    ax.legend(loc="lower right", fontsize=9, frameon=False)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    fig.text(0.06, 0.93, f"{words['portfolio']} — {portfolio['title']}", fontsize=15, weight="bold")
    fig.text(0.06, 0.895, portfolio["subtitle"], fontsize=9.5, color="#333")
    tx = fig.add_axes([0.55, 0.12, 0.43, 0.72])
    tx.axis("off")
    tx.set_xlim(0, 1)
    tx.set_ylim(0, 1)
    cols = [0, 0.2, 0.36, 0.5, 0.62, 0.76]
    head = ["", "ft²", "Índice" if lang == "es" else "Index", "Q", "Cob. sig." if lang == "es" else "Next cov.",
            "Factibilidad" if lang == "es" else "Feasibility"]
    for x, h in zip(cols, head):
        tx.text(x, 0.98, h, fontsize=9.5, weight="bold", va="top")
    y = 0.93
    for name in ("minimum", "optimum", "maximum", "accessible"):
        p = portfolio["profiles"].get(name)
        if not p:
            continue
        feas = words["feasibility"].get(p.get("zoning_status") or p["feasibility"], p["feasibility"])
        cov = "-" if p["next_stage_coverage"] is None else f"{p['next_stage_coverage']:.0%}"
        for x, v in zip(cols, [words["profiles"][name], f"{p['gross_area_sqft']:.0f}", f"{p['index']:.3f}",
                               f"{p['quality']:.2f}", cov, feas]):
            tx.text(x, y, v, fontsize=9.5, va="top")
        y -= 0.05
    if staged:
        y -= 0.02
        tx.text(0, y, words["profiles"]["staged"], fontsize=11, weight="bold", va="top")
        y -= 0.045
        lines = portfolio["staged_lines"]
        for line in lines:
            tx.text(0, y, line, fontsize=9, va="top")
            y -= 0.04
    y -= 0.02
    for line in portfolio["notes"]:
        tx.text(0, y, line, fontsize=9, va="top", color="#333")
        y -= 0.04
    fig.text(0.06, 0.03, words["footer"], fontsize=7.5, color="#777")
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
