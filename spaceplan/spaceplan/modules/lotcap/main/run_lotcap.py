"""Workflow of the lotcap module: layer-0 setup of a house lot.

lot -> boundaries -> rule variants (setbacks) -> envelope -> capacity (strategy A, plus B when the envelope allows)
-> lot conformity. Shared by the capacity pipeline and the area analysis (step 6.6). Moved from
spaceplan.main.run_capacity in refactor tanda 2 without changes.
"""

from __future__ import annotations

from dataclasses import dataclass

from spaceplan.core.lib_aux.quantity import PROVISIONAL, VERIFIED
from spaceplan.core.lib_aux.section import profile_of_largest
from spaceplan.modules.lotcap.lib.boundaries import classify_boundaries
from spaceplan.modules.lotcap.lib.capacity import (
    compute_capacity,
    envelope_sensitivity,
    evaluate_setbacks,
    realizable_strategy_b,
)
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


__all__ = ["LotSetup", "prepare_lot"]
