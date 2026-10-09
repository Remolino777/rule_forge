"""Workflow of the viz module: figures drawn from the module contracts (refactor tanda 4).

    draw_capacity(lot_capacity, out)                       lot lines by class, setbacks, envelope, strategy A
    draw_site(lot_capacity, site_plan, out)                site partition per number of floors
    draw_zoning(zoning_scheme, out, lot_capacity, site_plan)  zoning schemes (house with site; apartment in its unit)
    draw_area_matrix(area_matrix, out_dir, lang)           decision maps, area budgets, IC-IO and best schemes

viz reads contracts and never computes domain results: the lot geometry is rebuilt from the brief lot block the
lot_capacity contract carries (lotcap types are allowed to draw the lot), everything else is read as it is.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from spaceplan.core.lib.catalog import load_catalog
from spaceplan.core.lib.contracts import read_contract
from spaceplan.modules.lotcap.lib.lot import build_lot

LOT_BLOCKS = ("lot_metrics", "boundaries", "rule_variants", "lot_conformity", "capacity", "realizable_capacity",
              "sensitivity")


def package_view(lot_capacity: dict | None = None, site_plan: dict | None = None,
                 zoning_scheme: dict | None = None) -> dict:
    """The package-shaped dictionary the figure functions read, assembled from the contracts that are given."""
    lot = read_contract(lot_capacity, "lot_capacity") if lot_capacity is not None else {}
    site = read_contract(site_plan, "site_plan") if site_plan is not None else {}
    zoning = read_contract(zoning_scheme, "zoning_scheme") if zoning_scheme is not None else {}
    brief_id = next((c.get("brief_id") for c in (lot, site, zoning) if c.get("brief_id")), None)
    view = {"meta": {"brief_id": brief_id, "dwelling_type": zoning.get("dwelling_type", "house"),
                     "realization_strategy": zoning.get("realization_strategy") or lot.get("realization_strategy")}}
    view.update({k: lot.get(k) for k in LOT_BLOCKS})
    view.update(site_partition=site.get("site_partition"), zoning=zoning.get("zoning"), unit=zoning.get("unit"),
                corrections=zoning.get("corrections"))
    return view


def _lot(lot_capacity: dict):
    return build_lot(read_contract(lot_capacity, "lot_capacity")["lot"]["lot_block"])


def draw_capacity(lot_capacity: dict, out_path: str | Path) -> Path:
    from spaceplan.modules.viz.lib.lot_site_plots import plot_capacity

    view = package_view(lot_capacity)
    classes = SimpleNamespace(assignments={r["edge_id"]: SimpleNamespace(boundary_class=r["boundary_class"])
                                           for r in view["boundaries"]})
    setbacks = {r["edge_id"]: r["setback_ft"] for r in view["boundaries"]}
    plot_capacity(_lot(lot_capacity), classes, setbacks, view, out_path)
    return Path(out_path)


def draw_site(lot_capacity: dict, site_plan: dict, out_path: str | Path) -> Path:
    from spaceplan.modules.viz.lib.lot_site_plots import plot_site

    plot_site(_lot(lot_capacity), package_view(lot_capacity, site_plan), out_path)
    return Path(out_path)


def draw_zoning(zoning_scheme: dict, out_path: str | Path, lot_capacity: dict | None = None,
                site_plan: dict | None = None) -> Path:
    from shapely.geometry import shape

    from spaceplan.modules.viz.lib.zoning_plots import plot_zoning

    view = package_view(lot_capacity, site_plan, zoning_scheme)
    if view["unit"] is not None:
        plot_zoning(None, view, out_path, outline=shape(view["unit"]["polygon"]))
    else:
        plot_zoning(_lot(lot_capacity), view, out_path)
    return Path(out_path)


def area_matrix_figures(result: dict, out_dir: str | Path, display: dict, lang: str) -> list[Path]:
    """Per lot: decision map, area budget and IC-IO; for the pilot: best scheme per lot and household.
    Moved from the area-analysis pipeline in refactor tanda 4 without changes."""
    from spaceplan.modules.viz.lib.area_matrix_plots import (
        plot_area_budget,
        plot_decision_map,
        plot_ic_io,
        plot_scheme_matrix,
    )

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    figures = []
    for lot in result["lots"]:
        lid = lot["budget"]["lot_id"]
        lot_cells = [c for c in result["cells"] if c["lot_id"] == lid]
        figures.append(plot_decision_map(lot, lot_cells, out / f"{lid}_decision_map.png", display, lang))
        figures.append(plot_area_budget(lot, lot_cells, out / f"{lid}_area_budget.png", display, lang))
        figures.append(plot_ic_io(lot, lot_cells, out / f"{lid}_ic_io.png", display, lang))
    figures.append(plot_scheme_matrix(result, out / "pilot_best_schemes.png", display, lang))
    return figures


def draw_area_matrix(area_matrix: dict, out_dir: str | Path, lang: str | None = None,
                     catalog_path: str | Path | None = None) -> list[Path]:
    display = load_catalog(catalog_path).data["display"]
    return area_matrix_figures(read_contract(area_matrix, "area_matrix"), out_dir, display,
                               lang or display["default_lang"])


def stack_plan_sheets(stack_plan: dict, out_dir: str | Path, lang: str = "es",
                      profiles: tuple[str, ...] = ("optimum",)) -> list[Path]:
    """Stage S1 (step 6.7a): one stacked-plan sheet per lot with the drawn cells of the given profiles (all
    drawn cells when none of those profiles was drawn)."""
    from spaceplan.modules.viz.lib.stack_plan_plots import plot_stack_sheet

    plan = read_contract(stack_plan, "stack_plan")
    out = Path(out_dir)
    figures = []
    for lot in plan["lots"]:
        drawn = [c for c in plan["cells"] if c["lot_id"] == lot["lot_id"] and (c.get("s1") or {}).get("status") == "drawn"]
        if not drawn:
            continue
        chosen = [c for c in drawn if c["profile"] in profiles] or drawn
        figures.append(plot_stack_sheet(lot, chosen, out / f"{lot['lot_id']}_stack_plan.png", lang))
    return figures


__all__ = ["area_matrix_figures", "draw_area_matrix", "draw_capacity", "draw_site", "draw_zoning", "package_view",
           "stack_plan_sheets"]
