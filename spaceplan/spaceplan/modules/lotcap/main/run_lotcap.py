"""Workflow of the lotcap module: layer-0 setup of a house lot.

lot -> boundaries -> rule variants (setbacks) -> envelope -> capacity (strategy A, plus B when the envelope allows)
-> lot conformity. Shared by the capacity pipeline and the area analysis (step 6.6). Moved from
spaceplan.main.run_capacity in refactor tanda 2 without changes.

Refactor tanda 3: the flag-lot reading (body as lot, access strip as paving) and the realization strategy
selection also live here, moved from the capacity pipeline without changes.
"""

from __future__ import annotations

from dataclasses import dataclass

from spaceplan.core.lib.enums import Strategy
from spaceplan.core.lib_aux.quantity import PROVISIONAL, VERIFIED
from spaceplan.core.lib_aux.section import profile_of_largest
from spaceplan.modules.lotcap.lib.boundaries import classify_boundaries
from spaceplan.modules.lotcap.lib.capacity import (
    auto_strategy,
    compute_capacity,
    envelope_sensitivity,
    evaluate_setbacks,
    realizable_strategy_b,
)
from spaceplan.modules.lotcap.lib.flag_lot import resolve_flag_lot
from spaceplan.modules.lotcap.lib.lot import build_lot
from spaceplan.modules.lotcap.lib.rule_variants import lot_conformity


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



def flag_lot_body(brief: dict) -> tuple[dict, dict | None]:
    """(brief planned on the flag-lot body, flag facts or None); the brief is untouched for other lots."""
    return resolve_flag_lot(brief)


def flag_lot_warning(flag: dict) -> str:
    """Package warning of a flag lot (provisional reading)."""
    return (f"flag lot (provisional): planned on the {flag['body_area_sqft']:.0f} sq ft body; access strip "
            f"{flag['access_strip_area_sqft']:.0f} sq ft is exterior paving; street frontage {flag['street_frontage_ft']:.0f} ft")


def select_strategy(catalog, setup: LotSetup, strategy: str | None = None) -> tuple[str, dict]:
    """Realization strategy of the lot: 'auto' (catalog default) or a strategy name; A without an envelope
    profile. Returns (strategy name, selection record of the package)."""
    realization = catalog.data["realization"]
    requested = strategy or realization["default"]
    if requested == "auto":
        strategy_name, why = auto_strategy(realization, setup.capacity.realizable[0])
    else:
        strategy_name, why = requested, "requested"
    if setup.profile is None and strategy_name != Strategy.A_INSCRIBED_RECTANGLE.value:
        strategy_name, why = Strategy.A_INSCRIBED_RECTANGLE.value, "no envelope profile; strategy A"
    return strategy_name, {"requested": requested, "strategy": strategy_name, "reason": why}


__all__ = ["LotSetup", "flag_lot_body", "flag_lot_warning", "prepare_lot", "select_strategy"]
