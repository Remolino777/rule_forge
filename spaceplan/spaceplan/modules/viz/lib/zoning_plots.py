"""Zoning figure of one floor (layer 1c): zones, spaces, circulation and backyard.

Split from visualize.py in refactor tanda 3 without changes.
"""

from __future__ import annotations

from pathlib import Path

from spaceplan.core.lib_aux.geometry import polygon_parts
from spaceplan.modules.lotcap.lib.lot import Lot

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
