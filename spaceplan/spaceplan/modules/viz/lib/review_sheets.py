"""Review sheets of a zoned option (step 6.5d): plan with doors and backyard, header and notes.

Split from visualize.py in refactor tanda 3 without changes.
"""

from __future__ import annotations

from pathlib import Path

from spaceplan.core.lib_aux.geometry import polygon_parts

REVIEW_ZONE_COLORS = {"social": "#f6c177", "private": "#9aa7e0", "kitchen": "#ec8f8f", "service": "#c9b18f",
                      "circulation": "#e4e7ea", "garage": "#a9b4bd"}
REVIEW_YARD_COLORS = {"rear_deck": "#a1887f", "covered_terrace": "#8d6e63", "outdoor_kitchen": "#d0643b",
                      "pool": "#6cc3ec", "spa": "#4fb2e3", "bbq": "#e07b39", "shed": "#7b5e57", "garden_beds": "#7cb342"}
REVIEW_DOOR_COLORS = {"entry": "#c62828", "patio": "#2e7d32", "ensuite": "#6a1b9a", "door": "#212121"}


def space_label_fn(labels: dict, program: dict):
    """Display label for a space id (type label + household role + number) or a bare space type/role."""
    by_id = {s["space_id"]: s for s in program["spaces"]}
    types, roles = labels["space_types"], labels["household_roles"]
    matrix_roles, yard = labels.get("matrix_roles", {}), labels.get("backyard", {})

    def label(key: str) -> str:
        s = by_id.get(key)
        if s is None:
            if key.startswith("hall_"):
                return types.get("hall", "hall")
            return types.get(key) or matrix_roles.get(key) or yard.get(key) or key.replace("_", " ")
        text = types.get(s["space_type"], s["space_type"])
        role = roles.get(s.get("household_role", "general"), "")
        if role and role.lower() not in text.lower():
            text = f"{text} {role}"
        suffix = key.rsplit("_", 1)[-1]
        return f"{text} {suffix}" if suffix.isdigit() else text

    return label


def plot_review_sheet(lot_polygon, package: dict, program: dict, out_path: str | Path, header: list[str],
                      notes: list[str], display: dict, lang: str, option_id: str = "n1", rank: int = 1) -> None:
    """One-page review sheet: scaled plan with dimensions and doors, area schedule, legend, observations."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyArrow, Rectangle
    from shapely.geometry import shape

    words, labels = display["sheet"][lang], display["labels"][lang]
    label = space_label_fn(labels, program)
    targets = {s["space_id"]: s for s in program["spaces"]}
    opt = next(o for o in package["zoning"]["options"] if o["option_id"] == option_id)
    sch = next(s for s in opt["schemes"] if s["rank"] == rank)
    site = next(o for o in package["site_partition"]["options"] if o["option_id"] == option_id)

    fig = plt.figure(figsize=(16.5, 11.7))
    ax = fig.add_axes([0.03, 0.06, 0.47, 0.86])
    if site.get("backyard"):
        ax.fill(*shape(site["backyard"]["yard_polygon"]).exterior.xy, color="#e6f0d6", zorder=0)
    for key, color in (("front_green", "#e6f0d6"), ("driveway", "#cfcfcf"), ("entry_deck", "#c4b5ad"),
                       ("walkway", "#9e9e9e")):
        z = site["zones"].get(key)
        if z and z.get("polygon"):
            for part in polygon_parts(shape(z["polygon"])):
                ax.fill(*part.exterior.xy, color=color, zorder=1)
    env = package["capacity"]["envelope"].get("polygon")
    if env:
        for part in polygon_parts(shape(env)):
            ax.plot(*part.exterior.xy, color="#b71c1c", lw=0.9, ls=(0, (6, 3)), zorder=2)
    ax.plot(*lot_polygon.exterior.xy, color="black", lw=2.2, zorder=3)
    for el in (site.get("backyard") or {}).get("elements", []):
        if el["status"] == "placed" and el["polygon"]:
            g = shape(el["polygon"])
            ax.fill(*g.exterior.xy, color=REVIEW_YARD_COLORS.get(el["element"], "#999"), alpha=0.9, zorder=2)
            b = g.bounds
            ax.text(g.centroid.x, g.centroid.y, f"{labels['backyard'].get(el['element'], el['element'])}\n"
                    f"{b[2] - b[0]:.0f}×{b[3] - b[1]:.0f}", ha="center", va="center", fontsize=6.5, color="white",
                    zorder=3)
    rows = []
    for sid, sp in sch["spaces"].items():
        g = shape(sp["polygon"])
        x0, y0, x1, y1 = g.bounds
        ax.fill(*g.exterior.xy, color=REVIEW_ZONE_COLORS.get(sp["zone"], "#eee"), ec="#37474f", lw=1.6, zorder=4)
        w, d = x1 - x0, y1 - y0
        small = min(w, d) < 7
        ax.text(g.centroid.x, g.centroid.y, f"{label(sid)}\n{sp['net_area_sqft']:.0f} ft²\n{w:.1f}×{d:.1f}",
                ha="center", va="center", fontsize=6.3 if small else 8, zorder=6,
                rotation=90 if (small and d > w) else 0)
        t = targets.get(sid, {})
        rows.append((label(sid), t.get("target_area_sqft"), t.get("min_area_sqft"), sp["net_area_sqft"], w, d,
                     sp["depth_from_entry"]))
    for hall in sch["halls"]:
        g = shape(hall["polygon"])
        ax.fill(*g.exterior.xy, color="#eceff1", ec="#90a4ae", lw=0.8, zorder=4)
    for door in sch["doors"]:
        if not door.get("segment") or door["kind"] == "open":
            continue
        (a0, b0), (a1, b1) = door["segment"]
        mx, my = (a0 + a1) / 2, (b0 + b1) / 2
        hor, h = abs(b1 - b0) < 1e-6, 1.4
        ax.plot([mx - h, mx + h] if hor else [mx, mx], [my, my] if hor else [my - h, my + h],
                color=REVIEW_DOOR_COLORS.get(door["kind"], "#212121"), lw=5, solid_capstyle="butt", zorder=7)
    lx0, ly0, lx1, ly1 = lot_polygon.bounds
    fp = shape(site["zones"]["footprint"]["polygon"]).bounds

    def dim(x0, y0, x1, y1, text, off):
        if abs(y1 - y0) < 1e-6:
            ax.annotate("", (x0, y0 + off), (x1, y1 + off), arrowprops=dict(arrowstyle="<->", lw=0.8), zorder=8)
            ax.text((x0 + x1) / 2, y0 + off - 1.2, text, ha="center", va="top", fontsize=8)
        else:
            ax.annotate("", (x0 + off, y0), (x1 + off, y1), arrowprops=dict(arrowstyle="<->", lw=0.8), zorder=8)
            ax.text(x0 + off + (1.0 if off > 0 else -1.0), (y0 + y1) / 2, text, ha="left" if off > 0 else "right",
                    va="center", fontsize=8, rotation=90)

    dim(fp[0], fp[1], fp[2], fp[1], f"{fp[2] - fp[0]:.1f} ft", -5.5)
    dim(fp[2], fp[1], fp[2], fp[3], f"{fp[3] - fp[1]:.1f} ft", lx1 - fp[2] + 3.0)
    dim(lx0, ly0, lx1, ly0, f"{lx1 - lx0:.0f} ft ({words['front']})", -9.0)
    dim(lx0, ly0, lx0, ly1, f"{ly1 - ly0:.0f} ft", -3.5)
    cx = (lx0 + lx1) / 2
    ax.text(cx, ly0 - 16.0, words["street"], ha="center", fontsize=10, weight="bold")
    ax.text(cx, ly1 + 2.5, words["rear"], ha="center", fontsize=8, color="#555")
    ax.add_patch(FancyArrow(lx1 + 5.5, ly1 - 12, 0, 7, width=0.9, head_width=3, head_length=3, color="black",
                            clip_on=False))
    ax.text(lx1 + 5.5, ly1 - 0.5, "N", ha="center", fontsize=12, weight="bold")
    for i in range(2):
        ax.add_patch(Rectangle((lx1 + 2 + 5 * i, ly0 - 12), 5, 1.2, color="black" if i == 0 else "white", ec="black",
                               clip_on=False))
    ax.text(lx1 + 7, ly0 - 14.3, "0      5     10 ft", ha="center", fontsize=7)
    ax.set_xlim(lx0 - 8, lx1 + 12)
    ax.set_ylim(ly0 - 18, ly1 + 6)
    ax.set_aspect("equal")
    ax.axis("off")

    tx = fig.add_axes([0.52, 0.06, 0.46, 0.86])
    tx.axis("off")
    tx.set_xlim(0, 1)
    tx.set_ylim(0, 1)
    tx.set_autoscale_on(False)
    tx.text(0, 1.0, header[0], fontsize=15, weight="bold", va="top")
    y = 0.965
    for line in header[1:]:
        tx.text(0, y, line, fontsize=9.3, va="top", color="#333")
        y -= 0.025
    y -= 0.015
    tx.text(0, y, words["areas"], fontsize=11, weight="bold", va="top")
    y -= 0.03
    xs = [0, 0.33, 0.45, 0.57, 0.70, 0.90]
    for x, h_ in zip(xs, words["cols"]):
        tx.text(x, y, h_, fontsize=8.5, weight="bold", va="top")
    y -= 0.022
    for name, tgt, mn, got, w, d, depth in sorted(rows, key=lambda r: (r[6], r[0])):
        low = mn is not None and got < mn - 0.5
        vals = [name, f"{tgt:.0f}" if tgt else "–", f"{mn:.0f}" if mn else "–", f"{got:.0f}" + (" ✖" if low else ""),
                f"{w:.1f} × {d:.1f}", str(depth)]
        for x, v in zip(xs, vals):
            tx.text(x, y, v, fontsize=8.5, va="top", color="#b71c1c" if low and x == xs[3] else "black")
        y -= 0.02
    y -= 0.012
    tx.text(0, y, words["legend"], fontsize=11, weight="bold", va="top")
    y -= 0.03
    for i, (z, color) in enumerate(REVIEW_ZONE_COLORS.items()):
        tx.add_patch(Rectangle((0.16 * i, y - 0.018), 0.025, 0.016, color=color))
        tx.text(0.03 + 0.16 * i, y - 0.01, labels["zones"][z], fontsize=8.5, va="center")
    y -= 0.032
    for i, (kind, color) in enumerate(REVIEW_DOOR_COLORS.items()):
        tx.plot([0.24 * i, 0.03 + 0.24 * i], [y - 0.01] * 2, color=color, lw=5)
        tx.text(0.04 + 0.24 * i, y - 0.01, words["doors"][kind], fontsize=8.5, va="center")
    y -= 0.028
    tx.text(0, y, words["legend_note"], fontsize=8, va="top", color="#444")
    y -= 0.04
    tx.text(0, y, words["observations"], fontsize=11, weight="bold", va="top")
    y -= 0.028
    import textwrap

    for note in notes:
        for k, line in enumerate(textwrap.wrap(note, 112)):
            tx.text(0.0 if k == 0 else 0.015, y, line, fontsize=8.6, va="top")
            y -= 0.022
        if y < 0.04:
            break
    tx.text(0, 0.0, words["footer"], fontsize=7.5, color="#777")
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
