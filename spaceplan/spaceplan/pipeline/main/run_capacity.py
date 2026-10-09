"""Workflow for steps 1-6.

House:     brief -> validation -> program review -> scope -> lot -> boundaries -> rule variants -> envelope
           -> capacity (layer 0, strategies A and B) -> strategy selection -> site partition (layer 1)
           -> one-floor zoning (layer 1c) -> multivariable correction if it does not zone -> backyard (1d)
           -> package -> validation.
Apartment: brief -> validation -> program review -> unit -> zoning with the apartment profile -> package.

Refactor tanda 3: thin orchestrator. Each stage is a module workflow (household, lotcap, site, zoning, cost);
this file only composes them, assembles and validates the package and draws the optional figures.
"""

from __future__ import annotations

from pathlib import Path

from spaceplan.core.lib.catalog import load_catalog
from spaceplan.core.lib.rules import CRC_RULESET, load_ruleset, load_ruleset_resource
from spaceplan.core.lib.schema_validation import validate_brief, validate_package
from spaceplan.core.lib_aux.json_io import dump_json, load_json
from spaceplan.modules.cost.main.run_cost import package_cost
from spaceplan.modules.household.lib.program_review import review_program
from spaceplan.modules.household.main.run_household import resolve_brief_household
from spaceplan.modules.lotcap.lib.scope import ScopeResult, check_scope
from spaceplan.modules.lotcap.main.run_lotcap import (  # noqa: F401  (LotSetup re-exported)
    LotSetup,
    flag_lot_body,
    flag_lot_warning,
    prepare_lot,
    select_strategy,
)
from spaceplan.modules.site.main.run_site import plan_site, plan_site_backyard
from spaceplan.modules.zoning.main.run_zoning import zone_apartment, zone_house
from spaceplan.pipeline.lib.package import PackageInputs, assemble_package


def run_capacity(
    brief: dict,
    rules_path: str | Path | None = None,
    plot_path: str | Path | None = None,
    catalog_path: str | Path | None = None,
    site_plot_path: str | Path | None = None,
    zoning_plot_path: str | Path | None = None,
    strategy: str | None = None,
    corrections: bool = True,
    household_catalog_path: str | Path | None = None,
    cost_model: str | None = None,
    budget: dict | None = None,
) -> dict:
    """Entry point. A brief with a household block gets its program derived (step 6.5a) when it has none;
    the package then carries a 'household' block (privacy-minimized) and, for houses in scope, a relative
    'cost' block (step 6.5b; `budget` overrides brief.budget)."""
    brief, household_block, tier_programs = resolve_brief_household(brief, catalog_path, household_catalog_path)
    validate_brief(brief)
    brief, flag = flag_lot_body(brief)
    package = _run_capacity_resolved(brief, rules_path, plot_path, catalog_path, site_plot_path, zoning_plot_path,
                                     strategy, corrections)
    if household_block is not None:
        package["household"] = household_block
    if flag is not None:
        package["warnings"].append(flag_lot_warning(flag))
    cost = package_cost(load_catalog(catalog_path), brief, package, tier_programs, cost_model,
                        budget if budget is not None else brief.get("budget"))
    if cost is not None:
        package["cost"] = cost
    if household_block is not None or cost is not None:
        validate_package(package)
    return package


def _run_capacity_resolved(
    brief: dict,
    rules_path: str | Path | None = None,
    plot_path: str | Path | None = None,
    catalog_path: str | Path | None = None,
    site_plot_path: str | Path | None = None,
    zoning_plot_path: str | Path | None = None,
    strategy: str | None = None,
    corrections: bool = True,
) -> dict:
    """strategy: 'auto' (catalog default), or a strategy name; corrections: run the multivariable
    minimal correction when the one-floor option does not zone."""
    validate_brief(brief)
    rs = load_ruleset(rules_path)
    catalog = load_catalog(catalog_path)
    if brief["dwelling_type"] == "apartment":
        return run_apartment(brief, rs, catalog, zoning_plot_path)
    review = review_program(catalog, load_ruleset_resource(*CRC_RULESET), brief["program"])
    scope = check_scope(brief, rs)
    if not scope.in_scope:
        package = assemble_package(PackageInputs(brief, rs, scope, review))
        validate_package(package)
        return package

    setup = prepare_lot(brief, rs, catalog)
    strategy_name, selection = select_strategy(catalog, setup, strategy)
    site, site_warnings = plan_site(rs, catalog, brief, setup, strategy_name)
    zoning, correction = zone_house(brief, rs, catalog, setup, site, strategy_name, selection, corrections)
    plan_site_backyard(catalog, rs, brief, setup, site, zoning)
    lot, boundaries, evaluation = setup.lot, setup.boundaries, setup.evaluation
    package = assemble_package(
        PackageInputs(brief, rs, scope, review, lot, boundaries, evaluation, setup.capacity, setup.sensitivity,
                      setup.conformity, site, tuple(site_warnings), zoning, corrections=correction,
                      strategy=strategy_name)
    )
    validate_package(package)
    if plot_path:
        from spaceplan.modules.viz.lib.lot_site_plots import plot_capacity

        plot_capacity(lot, boundaries, evaluation.edge_setbacks, package, plot_path)
    if site_plot_path:
        from spaceplan.modules.viz.lib.lot_site_plots import plot_site

        plot_site(lot, package, site_plot_path)
    if zoning_plot_path:
        from spaceplan.modules.viz.lib.zoning_plots import plot_zoning

        plot_zoning(lot, package, zoning_plot_path)
    return package


def run_apartment(brief: dict, rs, catalog, zoning_plot_path: str | Path | None = None) -> dict:
    """Apartments: space planning inside the unit; the normative capacity layer is out of the pilot scope."""
    review = review_program(catalog, load_ruleset_resource(*CRC_RULESET), brief["program"])
    unit, zoning = zone_apartment(brief, catalog)
    scope = ScopeResult(False, (
        "apartment: normative capacity not modelled (multifamily zones and CBC R-2 are outside the RS-1-7 pilot); "
        "space planning only",))
    net = review["summary"]["net_area_sqft"]
    unit_info = {
        "area_sqft": unit.polygon.area,
        "rect_area_sqft": unit.rect_area,
        "polygon": unit.polygon,
        "edges": [{"edge_id": e["edge_id"], "role": e["role"]} for e in unit.edges],
        "entrance_interval_ft": list(unit.entrance_interval),
        "facade_roles": {f: sorted(r) for f, r in unit.facade_roles.items()},
        "program_fill_ratio": net / unit.rect_area,
    }
    package = assemble_package(PackageInputs(brief, rs, scope, review, zoning=zoning, unit=unit_info))
    if net > unit.rect_area:
        package["warnings"].append(f"net program {net:.0f} sq ft exceeds the unit rectangle {unit.rect_area:.0f} sq ft")
    validate_package(package)
    if zoning_plot_path:
        from spaceplan.modules.viz.lib.zoning_plots import plot_zoning

        plot_zoning(None, package, zoning_plot_path, outline=unit.polygon)
    return package


def run_capacity_file(
    brief_path: str | Path,
    out_path: str | Path | None = None,
    rules_path: str | Path | None = None,
    plot_path: str | Path | None = None,
    catalog_path: str | Path | None = None,
    site_plot_path: str | Path | None = None,
    zoning_plot_path: str | Path | None = None,
    strategy: str | None = None,
    corrections: bool = True,
    cost_model: str | None = None,
    budget: dict | None = None,
) -> dict:
    package = run_capacity(load_json(brief_path), rules_path, plot_path, catalog_path, site_plot_path,
                           zoning_plot_path, strategy, corrections, cost_model=cost_model, budget=budget)
    if out_path:
        dump_json(package, out_path)
    return package
