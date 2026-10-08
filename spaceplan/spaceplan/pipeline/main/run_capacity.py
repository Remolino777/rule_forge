"""Workflow for steps 1-6.

House:     brief -> validation -> program review -> scope -> lot -> boundaries -> rule variants -> envelope
           -> capacity (layer 0, strategies A and B) -> strategy selection -> site partition (layer 1)
           -> one-floor zoning (layer 1c) -> multivariable correction if it does not zone -> backyard (1d)
           -> package -> validation.
Apartment: brief -> validation -> program review -> unit -> zoning with the apartment profile -> package.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from spaceplan.modules.site.lib.backyard import backyard_for_site
from spaceplan.modules.lotcap.lib.boundaries import classify_boundaries
from spaceplan.modules.lotcap.lib.capacity import (
    auto_strategy,
    compute_capacity,
    envelope_sensitivity,
    evaluate_setbacks,
    realizable_strategy_b,
)
from spaceplan.core.lib.catalog import load_catalog
from spaceplan.core.lib.enums import Strategy
from spaceplan.modules.lotcap.lib.flag_lot import resolve_flag_lot
from spaceplan.modules.lotcap.lib.lot import build_lot
from spaceplan.pipeline.lib.package import PackageInputs, assemble_package
from spaceplan.modules.household.lib.program_review import review_program
from spaceplan.modules.zoning.lib.realization import get_strategy
from spaceplan.modules.lotcap.lib.rule_variants import lot_conformity
from spaceplan.core.lib.rules import CRC_RULESET, load_ruleset, load_ruleset_resource
from spaceplan.core.lib.schema_validation import validate_brief, validate_package
from spaceplan.modules.lotcap.lib.scope import check_scope
from spaceplan.modules.site.lib.site_partition import build_site_partition
from spaceplan.modules.zoning.lib.unit import build_unit
from spaceplan.modules.zoning.lib.zoning import zone_site_options, zone_unit
from spaceplan.core.lib_aux.json_io import dump_json, load_json
from spaceplan.core.lib_aux.quantity import PROVISIONAL, VERIFIED
from spaceplan.core.lib_aux.section import profile_of_largest
from spaceplan.modules.zoning.main.run_corrections import search_corrections
from spaceplan.modules.cost.main.run_cost import package_cost
from spaceplan.modules.household.main.run_household import resolve_brief_household


def _measurement_methods(brief: dict, rs) -> tuple[str, str]:
    chosen = brief.get("measurement", {})
    width = chosen.get("width_method") or rs.measurement["default_width_method"]
    depth = chosen.get("depth_method") or rs.measurement["default_depth_method"]
    return width, depth


@dataclass
class LotSetup:
    """Layer-0 objects of a house lot shared by the capacity pipeline and the area analysis (step 6.6)."""

    lot: object
    boundaries: object
    evaluation: object
    sensitivity: object
    capacity: object
    conformity: object
    frame: object
    envelope_local: object
    profile: object


def prepare_lot(brief: dict, rs, catalog) -> LotSetup:
    """Lot, boundaries, setbacks, capacity and realizable capacity (A plus B when the envelope allows)."""
    lot = build_lot(brief["lot"])
    boundaries = classify_boundaries(lot, brief["streets"])
    width_method, depth_method = _measurement_methods(brief, rs)
    evaluation = evaluate_setbacks(rs, brief, lot, boundaries, width_method, depth_method)
    sensitivity = envelope_sensitivity(rs, brief, lot, boundaries)
    capacity = compute_capacity(rs, brief, lot, boundaries, evaluation, sensitivity)

    widths = evaluation.metrics.widths_ft.values()
    depths = evaluation.metrics.depths_ft.values()
    ambiguous = (max(widths) - min(widths) > 1e-6) or (max(depths) - min(depths) > 1e-6)
    conformity = lot_conformity(
        rs,
        evaluation.metrics.area_sqft,
        evaluation.lot_width,
        evaluation.lot_depth,
        evaluation.metrics.frontage_ft,
        boundaries.is_corner,
        boundaries.primary_street["curve_radius_ft"],
        PROVISIONAL if ambiguous else VERIFIED,
    )
    frame = boundaries.frame
    envelope_local = frame.to_local(evaluation.envelope)
    try:
        profile = profile_of_largest(envelope_local) if not evaluation.envelope.is_empty else None
    except ValueError:  # envelope not horizontally convex: strategy B is not available
        profile = None
    realization = catalog.data["realization"]
    if profile is not None:
        capacity.realizable.extend(realizable_strategy_b(envelope_local, frame, realization["steps_reported"],
                                                         capacity.realizable[0]["area"].value))
    return LotSetup(lot, boundaries, evaluation, sensitivity, capacity, conformity, frame, envelope_local, profile)


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
    brief, flag = resolve_flag_lot(brief)
    package = _run_capacity_resolved(brief, rules_path, plot_path, catalog_path, site_plot_path, zoning_plot_path,
                                     strategy, corrections)
    if household_block is not None:
        package["household"] = household_block
    if flag is not None:
        package["warnings"].append(
            f"flag lot (provisional): planned on the {flag['body_area_sqft']:.0f} sq ft body; access strip "
            f"{flag['access_strip_area_sqft']:.0f} sq ft is exterior paving; street frontage {flag['street_frontage_ft']:.0f} ft")
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
    lot, boundaries, evaluation, sensitivity = setup.lot, setup.boundaries, setup.evaluation, setup.sensitivity
    capacity, conformity, frame, profile = setup.capacity, setup.conformity, setup.frame, setup.profile
    realization = catalog.data["realization"]
    requested = strategy or realization["default"]
    if requested == "auto":
        strategy_name, why = auto_strategy(realization, capacity.realizable[0])
    else:
        strategy_name, why = requested, "requested"
    if profile is None and strategy_name != Strategy.A_INSCRIBED_RECTANGLE.value:
        strategy_name, why = Strategy.A_INSCRIBED_RECTANGLE.value, "no envelope profile; strategy A"
    selection = {"requested": requested, "strategy": strategy_name, "reason": why}

    site, site_warnings = build_site_partition(rs, catalog, brief, lot, boundaries, evaluation, capacity,
                                               strategy_name)
    zoning = zone_site_options(catalog, brief, frame, site, get_strategy(strategy_name), profile)
    zoning["selection"] = selection
    correction = None
    if corrections and profile is not None:
        rect = capacity.realizable[0]
        correction = search_corrections(brief, rs, catalog, lot, boundaries, evaluation, capacity, profile,
                                        rect["width_ft"], strategy_name, site, zoning)
    backyard_for_site(catalog, rs, brief, lot, boundaries, site, zoning)
    package = assemble_package(
        PackageInputs(brief, rs, scope, review, lot, boundaries, evaluation, capacity, sensitivity, conformity,
                      site, tuple(site_warnings), zoning, corrections=correction, strategy=strategy_name)
    )
    validate_package(package)
    if plot_path:
        from spaceplan.modules.viz.lib.visualize import plot_capacity

        plot_capacity(lot, boundaries, evaluation.edge_setbacks, package, plot_path)
    if site_plot_path:
        from spaceplan.modules.viz.lib.visualize import plot_site

        plot_site(lot, package, site_plot_path)
    if zoning_plot_path:
        from spaceplan.modules.viz.lib.visualize import plot_zoning

        plot_zoning(lot, package, zoning_plot_path)
    return package


def run_apartment(brief: dict, rs, catalog, zoning_plot_path: str | Path | None = None) -> dict:
    """Apartments: space planning inside the unit; the normative capacity layer is out of the pilot scope."""
    from spaceplan.modules.lotcap.lib.scope import ScopeResult

    review = review_program(catalog, load_ruleset_resource(*CRC_RULESET), brief["program"])
    unit = build_unit(brief["unit"])
    zoning = zone_unit(catalog, brief, unit, get_strategy(Strategy.A_INSCRIBED_RECTANGLE))
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
        from spaceplan.modules.viz.lib.visualize import plot_zoning

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
