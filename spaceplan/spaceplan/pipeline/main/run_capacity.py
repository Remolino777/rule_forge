"""Workflow for steps 1-6.

House:     brief -> validation -> program review -> scope -> lot -> boundaries -> rule variants -> envelope
           -> capacity (layer 0, strategies A and B) -> strategy selection -> site partition (layer 1)
           -> one-floor zoning (layer 1c) -> multivariable correction if it does not zone -> backyard (1d)
           -> package -> validation.
Apartment: brief -> validation -> program review -> unit -> zoning with the apartment profile -> package.

Refactor tanda 3: thin orchestrator. Each stage is a module workflow (household, lotcap, site, zoning, cost);
this file only composes them, assembles and validates the package and draws the optional figures.
Refactor tanda 4: the stages hand over contracts. Every module output becomes its contract (to_contract,
validated against contracts/schemas); the package is assembled from the contracts, cost reads the lot_capacity,
site_plan and program contracts, and viz draws from the contracts. `run_capacity_contracts` returns them.
"""

from __future__ import annotations

from pathlib import Path

from spaceplan.core.lib.catalog import load_catalog
from spaceplan.core.lib.enums import Strategy
from spaceplan.core.lib.rules import CRC_RULESET, load_ruleset, load_ruleset_resource
from spaceplan.core.lib.schema_validation import validate_brief, validate_package
from spaceplan.core.lib_aux.json_io import dump_json, load_json
from spaceplan.modules.cost.main.contract import cost_from_contracts
from spaceplan.modules.cost.main.contract import from_contract as read_cost_report
from spaceplan.modules.household.lib.program_review import review_program
from spaceplan.modules.household.main.contract import from_contract as read_program
from spaceplan.modules.household.main.contract import to_contract as program_contract
from spaceplan.modules.household.main.run_household import resolve_brief_household
from spaceplan.modules.lotcap.lib.scope import ScopeResult, check_scope
from spaceplan.modules.lotcap.main.contract import to_contract as lot_capacity_contract
from spaceplan.modules.lotcap.main.run_lotcap import (  # noqa: F401  (LotSetup re-exported)
    LotSetup,
    flag_lot_body,
    flag_lot_warning,
    prepare_lot,
    select_strategy,
)
from spaceplan.modules.site.main.contract import to_contract as site_plan_contract
from spaceplan.modules.site.main.run_site import plan_site, plan_site_backyard
from spaceplan.modules.zoning.main.contract import to_contract as zoning_scheme_contract
from spaceplan.modules.zoning.main.run_zoning import unit_record, zone_apartment, zone_house
from spaceplan.pipeline.lib.package import package_from_contracts


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
    return run_capacity_contracts(brief, rules_path, plot_path, catalog_path, site_plot_path, zoning_plot_path,
                                  strategy, corrections, household_catalog_path, cost_model, budget)[0]


def run_capacity_contracts(
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
) -> tuple[dict, dict[str, dict]]:
    """(package, module contracts by name). The package is assembled from the contracts: program (household),
    lot_capacity (lotcap), site_plan (site), zoning_scheme (zoning) and cost_report (cost, which reads the
    lot_capacity, site_plan and program contracts)."""
    brief, household_block, tier_programs = resolve_brief_household(brief, catalog_path, household_catalog_path)
    validate_brief(brief)
    brief, flag = flag_lot_body(brief)
    package, contracts = _run_capacity_resolved(brief, rules_path, plot_path, catalog_path, site_plot_path,
                                                zoning_plot_path, strategy, corrections, flag)
    if household_block is not None:
        contracts["program"] = program_contract(brief, read_program(contracts["program"])["program_review"],
                                                household_block)
        package["household"] = read_program(contracts["program"])["household"]
    if flag is not None:
        package["warnings"].append(flag_lot_warning(flag))
    if "lot_capacity" in contracts and "site_plan" in contracts:
        report = cost_from_contracts(load_catalog(catalog_path), contracts["lot_capacity"], contracts["site_plan"],
                                     contracts["program"], tier_programs, cost_model,
                                     budget if budget is not None else brief.get("budget"))
        if report is not None:
            contracts["cost_report"] = report
            package["cost"] = read_cost_report(report)["cost"]
    if household_block is not None or "cost" in package:
        validate_package(package)
    return package, contracts


def _run_capacity_resolved(
    brief: dict,
    rules_path: str | Path | None = None,
    plot_path: str | Path | None = None,
    catalog_path: str | Path | None = None,
    site_plot_path: str | Path | None = None,
    zoning_plot_path: str | Path | None = None,
    strategy: str | None = None,
    corrections: bool = True,
    flag: dict | None = None,
) -> tuple[dict, dict[str, dict]]:
    """strategy: 'auto' (catalog default), or a strategy name; corrections: run the multivariable
    minimal correction when the one-floor option does not zone."""
    validate_brief(brief)
    rs = load_ruleset(rules_path)
    catalog = load_catalog(catalog_path)
    if brief["dwelling_type"] == "apartment":
        return run_apartment(brief, rs, catalog, zoning_plot_path)
    review = review_program(catalog, load_ruleset_resource(*CRC_RULESET), brief["program"])
    contracts = {"program": program_contract(brief, review)}
    scope = check_scope(brief, rs)
    if not scope.in_scope:
        package = package_from_contracts(brief, rs, scope.to_dict(), contracts["program"])
        validate_package(package)
        return package, contracts

    setup = prepare_lot(brief, rs, catalog)
    strategy_name, selection = select_strategy(catalog, setup, strategy)
    site, site_warnings = plan_site(rs, catalog, brief, setup, strategy_name)
    zoning, correction = zone_house(brief, rs, catalog, setup, site, strategy_name, selection, corrections)
    plan_site_backyard(catalog, rs, brief, setup, site, zoning)
    contracts["lot_capacity"] = lot_capacity_contract(brief, scope, setup, strategy_name, flag)
    contracts["site_plan"] = site_plan_contract(brief, site, site_warnings)
    contracts["zoning_scheme"] = zoning_scheme_contract(brief, zoning, None, correction, strategy_name)
    package = package_from_contracts(brief, rs, contracts["lot_capacity"]["scope"], contracts["program"],
                                     strategy_name, contracts["lot_capacity"], contracts["site_plan"],
                                     contracts["zoning_scheme"])
    validate_package(package)
    if plot_path or site_plot_path or zoning_plot_path:
        from spaceplan.modules.viz.main.run_viz import draw_capacity, draw_site, draw_zoning

        if plot_path:
            draw_capacity(contracts["lot_capacity"], plot_path)
        if site_plot_path:
            draw_site(contracts["lot_capacity"], contracts["site_plan"], site_plot_path)
        if zoning_plot_path:
            draw_zoning(contracts["zoning_scheme"], zoning_plot_path, contracts["lot_capacity"], contracts["site_plan"])
    return package, contracts


def run_apartment(brief: dict, rs, catalog, zoning_plot_path: str | Path | None = None) -> tuple[dict, dict]:
    """Apartments: space planning inside the unit; the normative capacity layer is out of the pilot scope."""
    review = review_program(catalog, load_ruleset_resource(*CRC_RULESET), brief["program"])
    unit, zoning = zone_apartment(brief, catalog)
    scope = ScopeResult(False, (
        "apartment: normative capacity not modelled (multifamily zones and CBC R-2 are outside the RS-1-7 pilot); "
        "space planning only",))
    net = review["summary"]["net_area_sqft"]
    contracts = {"program": program_contract(brief, review),
                 "zoning_scheme": zoning_scheme_contract(brief, zoning, unit_record(unit, net), None,
                                                         Strategy.A_INSCRIBED_RECTANGLE.value)}
    package = package_from_contracts(brief, rs, scope.to_dict(), contracts["program"],
                                     zoning_scheme=contracts["zoning_scheme"])
    if net > unit.rect_area:
        package["warnings"].append(f"net program {net:.0f} sq ft exceeds the unit rectangle {unit.rect_area:.0f} sq ft")
    validate_package(package)
    if zoning_plot_path:
        from spaceplan.modules.viz.main.run_viz import draw_zoning

        draw_zoning(contracts["zoning_scheme"], zoning_plot_path)
    return package, contracts


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
