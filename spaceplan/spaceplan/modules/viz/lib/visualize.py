"""Debug plot of the capacity layer: lot lines by class, setbacks, envelope and strategy A."""

from __future__ import annotations

from pathlib import Path

from spaceplan.modules.lotcap.lib.boundaries import BoundaryModel
from spaceplan.modules.lotcap.lib.lot import Lot
from spaceplan.core.lib_aux.geometry import polygon_parts

CLASS_COLORS = {"front": "#d1495b", "side": "#00798c", "street_side": "#edae49", "rear": "#30638e"}


def plot_capacity(lot: Lot, boundaries: BoundaryModel, edge_setbacks: dict, package: dict, out_path: str | Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from shapely.geometry import shape

    cap = package["capacity"]
    fig, ax = plt.subplots(figsize=(7, 8))
    env = cap["envelope"]["polygon"]
    if env:
        for part in polygon_parts(shape(env)):
            xs, ys = part.exterior.xy
            ax.fill(xs, ys, color="#cfe8d5", label="envelope")
    rect = package["realizable_capacity"][0]["polygon"]
    if rect:
        xs, ys = shape(rect).exterior.xy
        ax.plot(xs, ys, "--", color="#6a4c93", lw=1.6, label="strategy A")
    for edge in lot.edges:
        cls = boundaries.assignments[edge.edge_id].boundary_class
        xs, ys = zip(*edge.points)
        ax.plot(xs, ys, color=CLASS_COLORS[cls], lw=3)
        mx, my = edge.chord_midpoint
        ax.annotate(f"{edge.edge_id} {cls}\n{edge_setbacks[edge.edge_id]:.2f} ft", (mx, my),
                    fontsize=8, ha="center", va="center",
                    bbox={"boxstyle": "round", "fc": "white", "ec": CLASS_COLORS[cls], "alpha": 0.9})
    ac = cap["active_constraint_effective"]
    text = (
        f"lot {package['lot_metrics']['area_sqft']:.0f} sq ft\n"
        f"envelope {cap['envelope']['area']['value']:.0f} ({cap['envelope']['area']['status']})\n"
        f"FAR {cap['far_ratio']['value']:.2f} -> {cap['gross_area_max']['value']:.0f}\n"
        f"strategy A {package['realizable_capacity'][0]['area']['value']:.0f} "
        f"({package['realizable_capacity'][0]['utilization']['value']:.0%})\n"
        f"active (effective): {ac['constraint']}"
    )
    ax.text(0.02, 0.02, text, transform=ax.transAxes, fontsize=8, va="bottom",
            bbox={"boxstyle": "round", "fc": "white", "alpha": 0.9})
    ax.set_aspect("equal")
    ax.set_title(package["meta"]["brief_id"])
    handles, labels = ax.get_legend_handles_labels()
    unique = dict(zip(labels, handles))
    ax.legend(unique.values(), unique.keys(), loc="upper right", fontsize=8)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_path, dpi=130)
    plt.close(fig)


ZONE_STYLE = {
    "garden": ("#9ccc65", "garden"),
    "front_green": ("#c5e1a5", "front green"),
    "side_yards": ("#f1f8e9", "side yards"),
    "driveway": ("#9e9e9e", "driveway"),
    "walkway": ("#616161", "walkway"),
    "entry_deck": ("#a1887f", "entry deck"),
    "footprint": ("#90caf9", "footprint"),
}


def plot_site(lot: Lot, package: dict, out_path: str | Path) -> None:
    """One panel per floor option: site zones, paving share and garden."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from shapely.geometry import shape

    site = package["site_partition"]
    options = site["options"]
    fig, axes = plt.subplots(1, len(options), figsize=(5.2 * len(options), 7.5), squeeze=False)
    for ax, option in zip(axes[0], options):
        xs, ys = lot.polygon.exterior.xy
        ax.plot(xs, ys, color="black", lw=2)
        if "zones" not in option:
            ax.set_title(f"{option['option_id']}: not feasible", fontsize=10)
            ax.text(0.5, 0.5, "\n".join(option["reasons"]), transform=ax.transAxes, ha="center", fontsize=8, wrap=True)
            ax.set_aspect("equal")
            continue
        for key, (color, label) in ZONE_STYLE.items():
            geom = option["zones"][key]["polygon"]
            if not geom:
                continue
            for part in polygon_parts(shape(geom)):
                px, py = part.exterior.xy
                ax.fill(px, py, color=color, ec="#455a64" if key == "footprint" else "none", lw=1.2, label=label)
        paving = next(c for c in option["checks"] if c["check_id"] == "front_paving_fraction")
        selected = " (selected)" if option["option_id"] == site["selected_option_id"] else ""
        ax.set_title(
            f"{option['option_id']}{selected}: {option['floors']} floor(s), footprint {option['footprint_area_sqft']:.0f}\n"
            f"garden {option['zones']['garden']['area_sqft']:.0f} sq ft | paving {paving['value']:.0%} "
            f"(limit {paving['limit']:.0%}) {'OK' if paving['passes'] else 'FAIL'}",
            fontsize=9,
        )
        ax.set_aspect("equal")
        ax.grid(alpha=0.25)
    handles, labels = axes[0][-1].get_legend_handles_labels()
    if not handles:
        handles, labels = axes[0][0].get_legend_handles_labels()
    unique = dict(zip(labels, handles))
    fig.legend(unique.values(), unique.keys(), loc="lower center", ncol=7, fontsize=8)
    fig.suptitle(package["meta"]["brief_id"] + " - site protodistribution", fontsize=11)
    fig.tight_layout(rect=(0, 0.05, 1, 0.97))
    fig.savefig(out_path, dpi=120)
    plt.close(fig)


ZONE_COLORS = {
    "social": "#ffb74d", "private": "#7986cb", "kitchen": "#e57373", "service": "#a1887f",
    "circulation": "#e0e0e0", "garage": "#90a4ae",
}


BACKYARD_COLORS = {"rear_deck": "#8d6e63", "covered_terrace": "#a1887f", "outdoor_kitchen": "#d84315", "pool": "#4fc3f7", "spa": "#29b6f6", "bbq": "#ef6c00",
                   "shed": "#6d4c41", "garden_beds": "#689f38"}


def plot_zoning(lot: Lot | None, package: dict, out_path: str | Path, outline=None) -> None:
    """Catalog of zoning schemes (houses: with site and backyard; apartments: inside the unit)."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from shapely.geometry import shape

    site = {o["option_id"]: o for o in (package.get("site_partition") or {}).get("options", [])}
    panels = [(opt, sch) for opt in package["zoning"]["options"] if opt["status"] == "zoned" for sch in opt["schemes"]]
    corrected = None
    correction = package.get("corrections") or {}
    if not panels and correction.get("applied"):
        # the one-floor option did not zone: draw the minimal correction instead
        applied = correction["applied"]
        corrected = applied["combo"]
        site = {applied["site_option"]["option_id"]: applied["site_option"]}
        panels = [(applied["zoning_option"], sch) for sch in applied["zoning_option"]["schemes"]]
    if not panels:
        fig, ax = plt.subplots(figsize=(6, 3))
        ax.axis("off")
        msg = "no zoned one-floor option"
        for opt in package["zoning"]["options"]:
            if opt["status"] == "no_valid_scheme":
                msg += f"\n{opt['option_id']}: no topology satisfies the hard constraints"
        ax.text(0.5, 0.5, msg, ha="center", fontsize=9)
        fig.savefig(out_path, dpi=110)
        plt.close(fig)
        return
    boundary = outline if outline is not None else lot.polygon
    cols = min(3, len(panels))
    rows = (len(panels) + cols - 1) // cols
    fig, axes = plt.subplots(rows, cols, figsize=(4.8 * cols, 5.6 * rows), squeeze=False)
    for ax in axes.ravel():
        ax.axis("off")
    for ax, (opt, scheme) in zip(axes.ravel(), panels):
        ax.axis("on")
        xs, ys = boundary.exterior.xy
        ax.plot(xs, ys, color="black", lw=1.5)
        option = site.get(opt["option_id"])
        if option:
            zones = option["zones"]
            for key, color in (("driveway", "#9e9e9e"), ("entry_deck", "#a1887f"), ("walkway", "#616161")):
                if zones[key]["polygon"]:
                    for part in polygon_parts(shape(zones[key]["polygon"])):
                        px, py = part.exterior.xy
                        ax.fill(px, py, color=color, alpha=0.6)
            by = option.get("backyard")
            if by and scheme["rank"] == 1:
                yx, yy = shape(by["yard_polygon"]).exterior.xy
                ax.fill(yx, yy, color="#dcedc8")
                for el in by["elements"]:
                    if el["polygon"]:
                        poly = shape(el["polygon"])
                        px, py = poly.exterior.xy
                        ax.fill(px, py, color=BACKYARD_COLORS[el["element"]], alpha=0.85)
                        ax.text(poly.centroid.x, poly.centroid.y, el["element"].replace("_", " "), fontsize=6,
                                ha="center", va="center", color="white")
        real = scheme.get("realization") or {}
        for w in real.get("wedges", []):  # stepped mode: polygonal reserve
            if w.get("polygon"):
                for part in polygon_parts(shape(w["polygon"])):
                    px, py = part.exterior.xy
                    ax.fill(px, py, facecolor="none", edgecolor="#8d6e63", hatch="..", lw=0.6, ls="--")
        for res in (real.get("polygonal_extension") or {}).get("residual", []):  # polygonal mode: residual
            if res.get("polygon"):
                for part in polygon_parts(shape(res["polygon"])):
                    px, py = part.exterior.xy
                    ax.fill(px, py, color="#bdbdbd", alpha=0.7, hatch="xx", lw=0.4)
        if scheme.get("spaces"):
            for sid, sp in scheme["spaces"].items():
                poly = shape(sp["polygon"])
                px, py = poly.exterior.xy
                ax.fill(px, py, color=ZONE_COLORS.get(sp["zone"], "#eeeeee"), ec="white", lw=1.2)
                c = poly.centroid
                ax.text(c.x, c.y, f"{sid}\n{sp['net_area_sqft']:.0f} [{sp['depth_from_entry']}]", ha="center",
                        va="center", fontsize=5.5)
            for hall in scheme["halls"]:
                poly = shape(hall["polygon"])
                px, py = poly.exterior.xy
                ax.fill(px, py, color="#cfd8dc", ec="#90a4ae", lw=0.8, hatch="///")
            for door in scheme["doors"]:
                if door["segment"] and door["kind"] != "open":
                    (dx0, dy0), (dx1, dy1) = door["segment"]
                    mx, my = (dx0 + dx1) / 2, (dy0 + dy1) / 2
                    horizontal = abs(dy1 - dy0) < 1e-6
                    half = 1.5
                    xs_d = [mx - half, mx + half] if horizontal else [mx, mx]
                    ys_d = [my, my] if horizontal else [my - half, my + half]
                    color = {"entry": "#d32f2f", "patio": "#2e7d32", "ensuite": "#6a1b9a"}.get(door["kind"], "#212121")
                    ax.plot(xs_d, ys_d, color=color, lw=3.5, solid_capstyle="butt")
        else:
            for cell_id, cell in scheme["cells"].items():
                poly = shape(cell["polygon"])
                px, py = poly.exterior.xy
                ax.fill(px, py, color=ZONE_COLORS[cell["zone"]], ec="white", lw=1.5)
                c = poly.centroid
                ax.text(c.x, c.y, f"{cell_id.replace('_', chr(10), 1)}\n{cell['area_sqft']:.0f}", ha="center",
                        va="center", fontsize=6.5)
        unit = package.get("unit")
        if unit:
            from shapely.geometry import LineString

            for edge, (a, b) in zip(unit["edges"], zip(boundary.exterior.coords[:-1], boundary.exterior.coords[1:])):
                style = {"access": ("#d32f2f", 4), "exterior": ("#1976d2", 4), "party_wall": ("#424242", 6)}[edge["role"]]
                ax.plot(*LineString([a, b]).xy, color=style[0], lw=style[1], solid_capstyle="butt")
        s = scheme["scores"]
        circ = scheme.get("circulation")
        extra = (f"\nmatrix {scheme['space_scores']['matrix']:.2f} | circulation {circ['fraction']:.0%}"
                 if circ else "")
        mode = f" [{real.get('mode')}{', joint ' + real['joint'] if real.get('joint') else ''}]" if real else ""
        ax.set_title(f"{opt['option_id']} #{scheme['rank']} ({scheme['footprint_variant']}){mode}  score {s['total']:.2f}\n"
                     f"rel {s['relations']:.2f} | orient {s['orientation']:.2f} | shape {s['shape']:.2f}{extra}",
                     fontsize=7.5)
        ax.set_aspect("equal")
        ax.set_xticks([])
        ax.set_yticks([])
    kind = package["meta"]["dwelling_type"]
    strategy = corrected["strategy"] if corrected else package["meta"]["realization_strategy"]
    note = f" | minimal correction: {', '.join(corrected['labels'])}" if corrected else ""
    fig.suptitle(f"{package['meta']['brief_id']} - {kind} schemes ({strategy}{note}): net sq ft [depth from entry]; "
                 "doors: red entry, green patio, purple en-suite, black door; hatched = carved hall; "
                 "dotted = wedge reserve; grey x = residual"
                 + ("  |  red: corridor/entrance, blue: exterior, black: party wall" if kind == "apartment" else ""),
                 fontsize=10)
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(out_path, dpi=110)
    plt.close(fig)


# ------------------------------------------------------------------------------ review sheets (6.5d)

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


# =============================================================================== step 6.6: area matrix

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
