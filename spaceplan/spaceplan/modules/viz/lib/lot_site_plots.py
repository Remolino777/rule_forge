"""Lot and site figures: capacity layer (lot lines by class, setbacks, envelope, strategy A) and
site partition (layer 1).

Split from visualize.py in refactor tanda 3 without changes.
"""

from __future__ import annotations

from pathlib import Path

from spaceplan.core.lib_aux.geometry import polygon_parts
from spaceplan.modules.lotcap.lib.boundaries import BoundaryModel
from spaceplan.modules.lotcap.lib.lot import Lot

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
