"""Layer 0 - capacity: what fits on the lot before any space is drawn.

Separates normative capacity (what the code allows inside the setback envelope) from
realizable capacity (what a geometric strategy can actually occupy), so irregular lots do not
produce false infeasibles. Every magnitude is a traceable Quantity with a status.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from shapely.geometry.base import BaseGeometry

from spaceplan.core.lib.enums import (
    DEFAULT_FLOOR_TO_FLOOR_FT,
    DEFAULT_GROSS_FACTOR,
    BoundaryClass,
    Constraint,
    FeasibilityLevel,
    Strategy,
)
from spaceplan.core.lib.rules import RuleSet
from spaceplan.core.lib_aux.geometry import (
    clip_y,
    halfplane_envelope,
    max_inscribed_rect,
    setback_envelope,
)
from spaceplan.core.lib_aux.quantity import PROVISIONAL, VERIFIED, Quantity, worst_status
from spaceplan.core.lib_aux.tolerances import (
    AREA_TIE_TOL_SQFT,
    BISECTION_ITERS,
    SEMANTICS_AREA_TOL_SQFT,
    SENSITIVITY_AREA_TOL_SQFT,
)
from spaceplan.modules.lotcap.lib import rule_variants as rv
from spaceplan.modules.lotcap.lib.boundaries import BoundaryModel
from spaceplan.modules.lotcap.lib.lot import Lot
from spaceplan.modules.lotcap.lib.lot_metrics import LotMetrics, measure_lot

MEASUREMENT_NOTE = "variant depends on the lot width/depth measurement method (SDMC Ch. 11 pending)"
UTILIZATION_WARNING_BELOW = 0.80


# --------------------------------------------------------------------------- setbacks & envelope


@dataclass(frozen=True)
class SetbackEvaluation:
    width_method: str
    depth_method: str
    metrics: LotMetrics
    decisions: dict[str, rv.VariantDecision]
    reassignment_allowed: bool
    edge_setbacks: dict[str, float]
    envelope: BaseGeometry

    @property
    def lot_width(self) -> float:
        return self.metrics.widths_ft[self.width_method]

    @property
    def lot_depth(self) -> float:
        return self.metrics.depths_ft[self.depth_method]


def evaluate_setbacks(
    rs: RuleSet, brief: dict, lot: Lot, boundaries: BoundaryModel, width_method: str, depth_method: str
) -> SetbackEvaluation:
    primary = boundaries.primary_street
    front = rv.front_setback(rs, primary["street_type"], brief["terrain"]["front_steep_fraction"])
    metrics = measure_lot(lot, boundaries, front.value, primary["curve_radius_ft"])
    width, depth = metrics.widths_ft[width_method], metrics.depths_ft[depth_method]
    side, reassignment = rv.side_setback(rs, width, boundaries.is_corner)
    alley = max((lot.edge(i).alley_width_ft for i in boundaries.edges_of(BoundaryClass.REAR)), default=0.0)
    decisions = {
        BoundaryClass.FRONT.value: front,
        BoundaryClass.SIDE.value: side,
        BoundaryClass.STREET_SIDE.value: rv.street_side_setback(rs),
        BoundaryClass.REAR.value: rv.rear_setback(rs, depth, alley),
    }
    edge_setbacks = {
        e.edge_id: decisions[boundaries.assignments[e.edge_id].boundary_class].value for e in lot.edges
    }
    envelope = setback_envelope(lot.polygon, [(e.points, edge_setbacks[e.edge_id]) for e in lot.edges])
    return SetbackEvaluation(
        width_method, depth_method, metrics, decisions, reassignment, edge_setbacks, envelope
    )


def envelope_sensitivity(rs: RuleSet, brief: dict, lot: Lot, boundaries: BoundaryModel) -> dict:
    """Recompute setbacks and envelope under every width/depth measurement method."""
    rows = []
    for wm in rs.measurement["width_methods"]:
        for dm in rs.measurement["depth_methods"]:
            ev = evaluate_setbacks(rs, brief, lot, boundaries, wm, dm)
            rows.append(
                {
                    "width_method": wm,
                    "depth_method": dm,
                    "lot_width_ft": ev.lot_width,
                    "lot_depth_ft": ev.lot_depth,
                    "front_setback_ft": ev.decisions["front"].value,
                    "side_setback_ft": ev.decisions["side"].value,
                    "street_side_setback_ft": ev.decisions["street_side"].value,
                    "rear_setback_ft": ev.decisions["rear"].value,
                    "envelope_area_sqft": ev.envelope.area,
                }
            )
    areas = [r["envelope_area_sqft"] for r in rows]
    return {
        "rows": rows,
        "envelope_area_min_sqft": min(areas),
        "envelope_area_max_sqft": max(areas),
        "varies": max(areas) - min(areas) > SENSITIVITY_AREA_TOL_SQFT,
        "side_setback_varies": len({round(r["side_setback_ft"], 6) for r in rows}) > 1,
        "rear_setback_varies": len({round(r["rear_setback_ft"], 6) for r in rows}) > 1,
    }


def distance_semantics_check(lot: Lot, ev: SetbackEvaluation) -> tuple[str, str | None]:
    """Is the envelope independent of how 'distance to the lot line' is read?"""
    if not lot.is_convex:
        return PROVISIONAL, "concave lot: euclidean distance to the lot line assumed at reflex corners"
    items = [(e.points, ev.edge_setbacks[e.edge_id]) for e in lot.edges]
    gap = abs(halfplane_envelope(lot.polygon, items).area - ev.envelope.area)
    if gap <= SEMANTICS_AREA_TOL_SQFT:
        return VERIFIED, None
    return PROVISIONAL, f"perpendicular-band and euclidean setback readings differ by {gap:.1f} sq ft"


# --------------------------------------------------------------------------- helpers


def _min_quantity(quantities: list[Quantity | None]) -> Quantity:
    valid = [q for q in quantities if q is not None and q.value is not None]
    best = valid[0]
    for q in valid[1:]:
        if q.value < best.value - AREA_TIE_TOL_SQFT:
            best = q
    return Quantity.derived(best.value, best.unit, valid, note=best.note)


def _argmin_constraint(candidates: list[tuple[Constraint, Quantity | None]]) -> dict:
    valid = [(c, q) for c, q in candidates if q is not None and q.value is not None]
    best = valid[0]
    for c, q in valid[1:]:
        if q.value < best[1].value - AREA_TIE_TOL_SQFT:
            best = (c, q)
    return {"constraint": best[0].value, "value": best[1]}


def garden_footprint_limit(
    lot_local: BaseGeometry, envelope_local: BaseGeometry, y_start: float, min_garden_sqft: float
) -> float:
    """Largest front-anchored footprint (spanning the envelope width) that leaves the garden.

    Garden = lot area behind the footprint's back line (spaceplan v1.1, section 5 model).
    """

    def garden(t: float) -> float:
        return clip_y(lot_local, y_min=y_start + t).area

    def footprint(t: float) -> float:
        return clip_y(envelope_local, y_max=y_start + t).area

    if garden(0.0) < min_garden_sqft:
        return 0.0
    lo, hi = 0.0, lot_local.bounds[3] - y_start
    if garden(hi) >= min_garden_sqft:
        return footprint(hi)
    for _ in range(BISECTION_ITERS):
        mid = 0.5 * (lo + hi)
        if garden(mid) >= min_garden_sqft:
            lo = mid
        else:
            hi = mid
    return footprint(lo)


def _feasibility(
    level: FeasibilityLevel,
    footprint: Quantity,
    floors_cap: int,
    floors_q: Quantity,
    required: Quantity,
    gross_max: Quantity,
) -> dict:
    reasons = []
    if required.value > gross_max.value + AREA_TIE_TOL_SQFT:
        reasons.append(
            f"required gross area {required.value:.0f} sq ft exceeds FAR limit {gross_max.value:.0f} sq ft"
        )
    floors_min = math.ceil(required.value / footprint.value - 1e-9) if footprint.value > 0 else None
    if floors_min is None:
        reasons.append("no buildable footprint")
    elif floors_min > floors_cap:
        reasons.append(
            f"needs {floors_min} floors on a {footprint.value:.0f} sq ft footprint; cap is {floors_cap}"
        )
    return {
        "level": level.value,
        "footprint": footprint,
        "floors_min": floors_min,
        "floors_cap": floors_cap,
        "feasible": not reasons,
        "reasons": reasons,
        "status": worst_status(footprint.status, required.status, gross_max.status, floors_q.status),
    }


def required_gross_area(program: dict) -> Quantity:
    declared = program.get("required_gross_area_sqft")
    if declared is not None:
        return Quantity(float(declared), "sq_ft", VERIFIED, ("brief:program.required_gross_area_sqft",))
    net = sum(s["target_area_sqft"] for s in program["spaces"])
    factor = program.get("gross_factor", DEFAULT_GROSS_FACTOR)
    return Quantity(
        net * factor, "sq_ft", PROVISIONAL, ("brief:program.spaces", "assumption:gross_factor"),
        f"net program {net:.0f} sq ft x gross factor {factor}",
    )


# --------------------------------------------------------------------------- capacity


@dataclass(frozen=True)
class CapacityResult:
    decisions: dict[str, rv.VariantDecision]
    capacity: dict
    realizable: list[dict]
    warnings: list[str]


def compute_capacity(
    rs: RuleSet,
    brief: dict,
    lot: Lot,
    boundaries: BoundaryModel,
    ev: SetbackEvaluation,
    sensitivity: dict,
) -> CapacityResult:
    warnings: list[str] = []
    decisions = dict(ev.decisions)
    if sensitivity["side_setback_varies"]:
        decisions["side"] = decisions["side"].with_status(PROVISIONAL, MEASUREMENT_NOTE)
    if sensitivity["rear_setback_varies"]:
        decisions["rear"] = decisions["rear"].with_status(PROVISIONAL, MEASUREMENT_NOTE)

    # Envelope ------------------------------------------------------------------------------
    semantics_status, semantics_note = distance_semantics_check(lot, ev)
    env_note = semantics_note
    env_status = semantics_status
    if sensitivity["varies"]:
        env_status = PROVISIONAL
        env_note = (
            f"range {sensitivity['envelope_area_min_sqft']:.0f}-{sensitivity['envelope_area_max_sqft']:.0f}"
            f" sq ft across measurement methods" + (f"; {semantics_note}" if semantics_note else "")
        )
    used = [decisions[a.boundary_class] for a in boundaries.assignments.values()]
    envelope_area = Quantity.derived(
        ev.envelope.area, "sq_ft", [d.quantity for d in used], ("geometry:setback_envelope",),
        env_status, env_note,
    )

    # Intensity -----------------------------------------------------------------------------
    area = ev.metrics.area_sqft
    steep = brief["terrain"]["steep_hillside_fraction"]
    coverage = rv.hillside_coverage(rs, steep)
    coverage_footprint = (
        Quantity.derived(coverage.value * area, "sq_ft", [coverage.quantity], note="coverage x lot area")
        if coverage.value is not None
        else None
    )
    footprint_normative = _min_quantity([envelope_area, coverage_footprint])
    far, far_base = rv.floor_area_ratio(rs, area, steep)
    gross_max = Quantity.derived(far.value * far_base.value, "sq_ft", [far.quantity, far_base])

    # Height and floors ---------------------------------------------------------------------
    height = rv.height_limit(rs, brief["overlays"]["height_map_limit_ft"])
    f2f = brief.get("massing_assumptions", {}).get("floor_to_floor_ft", DEFAULT_FLOOR_TO_FLOOR_FT)
    floors_height = max(1, math.floor(height.value / f2f + 1e-9))
    floors_max = Quantity.derived(
        floors_height, "floors", [height.quantity], ("assumption:floor_to_floor_ft",),
        note=f"floor-to-floor {f2f:g} ft; angled plane not applied",
    )
    third = rv.third_floor_limits(rs, ev.lot_width, ev.lot_depth)
    plane = rv.angled_plane(rs, ev.lot_width)

    # Realization (strategy A) --------------------------------------------------------------
    rect = max_inscribed_rect(ev.envelope, boundaries.frame)
    rect_area = Quantity.derived(
        rect.area if rect else 0.0, "sq_ft", [envelope_area], (f"strategy:{Strategy.A_INSCRIBED_RECTANGLE}",)
    )
    utilization = Quantity.derived(
        rect_area.value / envelope_area.value if envelope_area.value else None,
        "ratio", [envelope_area, rect_area],
    )
    if utilization.value is not None and utilization.value < UTILIZATION_WARNING_BELOW:
        warnings.append(
            f"strategy A uses {utilization.value:.0%} of the envelope; a stepped footprint "
            f"(strategy B, step 6) is recommended for this lot shape"
        )

    # Preferences ---------------------------------------------------------------------------
    prefs = brief["preferences"]
    garden_limit = None
    if prefs.get("min_garden_area_sqft") is not None:
        frame = boundaries.frame
        value = garden_footprint_limit(
            frame.to_local(lot.polygon), frame.to_local(ev.envelope),
            decisions["front"].value, prefs["min_garden_area_sqft"],
        )
        garden_limit = Quantity.derived(
            value, "sq_ft", [envelope_area],
            ("preference:min_garden_area_sqft", "model:front_anchored_full_width_footprint"),
            PROVISIONAL,
            "upper bound with a front-anchored footprint spanning the envelope; exact site partition in step 4",
        )

    # Feasibility ---------------------------------------------------------------------------
    required = required_gross_area(brief["program"])
    pref_cap = prefs.get("max_floors")
    cap_with_prefs = min(floors_height, pref_cap) if pref_cap else floors_height
    levels = [
        _feasibility(FeasibilityLevel.NORMATIVE, footprint_normative, floors_height, floors_max, required, gross_max),
        _feasibility(
            FeasibilityLevel.NORMATIVE_WITH_PREFERENCES,
            _min_quantity([footprint_normative, garden_limit]),
            cap_with_prefs, floors_max, required, gross_max,
        ),
        _feasibility(
            FeasibilityLevel.STRATEGY_A_WITH_PREFERENCES,
            _min_quantity([footprint_normative, garden_limit, rect_area]),
            cap_with_prefs, floors_max, required, gross_max,
        ),
    ]
    false_infeasible = levels[1]["feasible"] and not levels[2]["feasible"]
    if false_infeasible:
        warnings.append(
            "false-infeasible risk: the program fits the code but not strategy A; "
            "do not report it as infeasible"
        )

    normative_candidates = [
        (Constraint.FAR, gross_max),
        (Constraint.ENVELOPE, envelope_area),
        (Constraint.OCCUPANCY_HILLSIDE, coverage_footprint),
    ]
    effective_candidates = normative_candidates + [
        (Constraint.GARDEN_PREFERENCE, garden_limit),
        (Constraint.REALIZATION, rect_area),
    ]

    capacity = {
        "setbacks": {k: d.quantity for k, d in decisions.items()},
        "envelope": {
            "area": envelope_area,
            "polygon": ev.envelope if not ev.envelope.is_empty else None,
            "distance_semantics": rs.measurement["setback_distance_semantics"],
        },
        "coverage_max": coverage.quantity,
        "footprint_max_normative": footprint_normative,
        "far_ratio": far.quantity,
        "far_base_area": far_base,
        "gross_area_max": gross_max,
        "height_max": height.quantity,
        "floors_max_height": floors_max,
        "third_floor": {"applicable": floors_height >= 3, **third},
        "envelope_plane": plane,
        "garden_footprint_limit": garden_limit,
        "required_gross_area": required,
        "active_constraint_normative": _argmin_constraint(normative_candidates),
        "active_constraint_effective": _argmin_constraint(effective_candidates),
        "feasibility": {"levels": levels, "false_infeasible_risk": false_infeasible},
    }
    realizable = [
        {
            "strategy": Strategy.A_INSCRIBED_RECTANGLE.value,
            "area": rect_area,
            "utilization": utilization,
            "width_ft": rect.width if rect else None,
            "depth_ft": rect.depth if rect else None,
            "polygon": rect.polygon if rect else None,
        }
    ]
    all_decisions = {
        **decisions,
        "coverage": coverage,
        "far": far,
        "height": height,
    }
    return CapacityResult(all_decisions, capacity, realizable, warnings)


# --------------------------------------------------------------------------- strategy B capacity (step 6)


def realizable_strategy_b(envelope_local, frame, steps: list[int], area_a: float | None) -> list[dict]:
    """Realizable footprint with strategy B: k stepped rectangles from the envelope front, and the
    polygonal footprint (the whole envelope). Utilization is over the envelope area."""
    from shapely.geometry import box
    from shapely.ops import unary_union

    from spaceplan.core.lib.enums import Strategy
    from spaceplan.core.lib_aux.section import profile_of_largest

    profile = profile_of_largest(envelope_local)
    env_area = profile.area
    out = []
    for k in steps:
        area, rects = profile.best_steps(profile.ymin, k)
        geom = unary_union([box(*r) for r in rects]) if rects else None
        out.append({
            "strategy": Strategy.B_STEPPED_FOOTPRINT.value,
            "steps": k,
            "area": Quantity.derived(area, "sq_ft", [], ("geometry:setback_envelope", f"strategy:B_steps_{k}"),
                                     PROVISIONAL, "best break positions by grid + pattern search"),
            "utilization": Quantity.derived(area / env_area if env_area else None, "ratio", [],
                                            ("geometry:setback_envelope",), PROVISIONAL, None),
            "width_ft": max((r[2] - r[0]) for r in rects) if rects else None,
            "depth_ft": (rects[-1][3] - rects[0][1]) if rects else None,
            "polygon": frame.to_world(geom) if geom is not None else None,
        })
    out.append({
        "strategy": Strategy.B_POLYGONAL_FOOTPRINT.value,
        "steps": None,
        "area": Quantity.derived(env_area, "sq_ft", [], ("geometry:setback_envelope",), PROVISIONAL,
                                 "edge cells follow the oblique lot lines; cores govern minimum dimensions"),
        "utilization": Quantity.derived(1.0 if env_area else None, "ratio", [], ("geometry:setback_envelope",),
                                        PROVISIONAL, None),
        "width_ft": max(profile.width(profile.ymin), profile.width(profile.ymax)),
        "depth_ft": profile.ymax - profile.ymin,
        "polygon": frame.to_world(envelope_local),
    })
    return out


def auto_strategy(catalog_realization: dict, realizable_a: dict) -> tuple[str, str]:
    """Strategy for 'auto': A when its rectangle uses enough of the envelope, else the fallback."""
    from spaceplan.core.lib.enums import Strategy

    util = realizable_a["utilization"].value
    threshold = catalog_realization["auto_min_utilization_A"]
    if util is not None and util >= threshold - 1e-9:
        return Strategy.A_INSCRIBED_RECTANGLE.value, f"strategy A uses {util:.0%} of the envelope (>= {threshold:.0%})"
    shown = "n/a" if util is None else f"{util:.0%}"
    return catalog_realization["auto_fallback"], f"strategy A uses {shown} of the envelope (< {threshold:.0%})"
