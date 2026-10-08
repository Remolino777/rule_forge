"""Decision table: which variant of each rule applies to this lot, and its value.

All thresholds and values are read from the ruleset (DSL); this module only encodes the
selection logic and records the evaluated predicate for traceability.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from spaceplan.lib.enums import StreetType
from spaceplan.lib.rules import BASE_VARIANT, RuleSet
from spaceplan.lib_aux.quantity import Quantity, worst_status
from spaceplan.lib_aux.tolerances import LENGTH_EQ_TOL_FT

LOT_AREA_MIN = "Z00-LOT-AREA-MIN"
LOT_WIDTH_MIN = "Z00-LOT-WIDTH-MIN"
LOT_DEPTH_MIN = "Z00-LOT-DEPTH-MIN"
FRONTAGE_MIN = "Z00-FRONTAGE-MIN"
FRONT_SETBACK = "Z01-FRONT-SETBACK"
SIDE_SETBACK = "Z02-SIDE-SETBACK"
STREET_SIDE_SETBACK = "Z03-STREET-SIDE-SETBACK"
REAR_SETBACK = "Z04-REAR-SETBACK"
HEIGHT_MAX = "Z05-HEIGHT-MAX"
ANGLED_PLANE = "Z06-ANGLED-PLANE"
FAR = "Z07-FAR"
HILLSIDE_COVERAGE = "Z08-HILLSIDE-COVERAGE"
THIRD_FLOOR = "Z09-THIRD-FLOOR"


@dataclass(frozen=True)
class VariantDecision:
    rule_id: str
    magnitude: str
    variant_id: str
    quantity: Quantity
    predicate: str

    @property
    def value(self) -> float | None:
        return self.quantity.value

    def with_status(self, status: str, note: str | None = None) -> VariantDecision:
        return replace(self, quantity=self.quantity.with_status(status, note))

    def to_dict(self) -> dict:
        return {
            "rule_id": self.rule_id,
            "magnitude": self.magnitude,
            "variant_id": self.variant_id,
            "quantity": self.quantity.to_dict(),
            "predicate": self.predicate,
        }


def _decision(
    rs: RuleSet,
    rule_id: str,
    magnitude: str,
    variant_ids: list[str],
    value: float | None,
    unit: str,
    predicate: str,
    note: str | None = None,
) -> VariantDecision:
    status = worst_status(*(rs.status(rule_id, v) for v in variant_ids))
    sources = tuple(dict.fromkeys(rs.source_tag(rule_id, v) for v in variant_ids))
    q = Quantity(None if value is None else float(value), unit, status, sources, note)
    return VariantDecision(rule_id, magnitude, "+".join(variant_ids), q, predicate)


# --------------------------------------------------------------------------- setbacks


def front_setback(rs: RuleSet, street_type: str, front_steep_fraction: float) -> VariantDecision:
    """Most permissive applicable variant (capacity asks for the maximum buildable envelope)."""
    base = float(rs.rule(FRONT_SETBACK)["value"])
    options = [(BASE_VARIANT, base, f"base {base:g} ft")]
    cds = rs.params(FRONT_SETBACK, "cul_de_sac")
    if street_type == StreetType.CUL_DE_SAC:
        value = max(base - cds["reduction_ft"], cds["min_ft"])
        options.append(("cul_de_sac", float(value), "street_type=cul_de_sac"))
    slope = rs.params(FRONT_SETBACK, "front_slope")
    if front_steep_fraction >= slope["front_steep_fraction_at_least"]:
        options.append(
            (
                "front_slope",
                float(slope["reduced_to_ft"]),
                f"front_steep_fraction={front_steep_fraction:.2f} >= {slope['front_steep_fraction_at_least']}",
            )
        )
    variant, value, _ = min(options, key=lambda o: o[1])
    predicate = "; ".join(o[2] for o in options)
    return _decision(rs, FRONT_SETBACK, "front_setback", [variant], value, "ft", predicate)


def lot_width_minimum(rs: RuleSet, is_corner: bool) -> tuple[float, str]:
    if is_corner:
        return float(rs.params(LOT_WIDTH_MIN, "corner_lot")["lot_width_min_ft"]), "corner_lot"
    return float(rs.rule(LOT_WIDTH_MIN)["value"]), BASE_VARIANT


def side_setback(rs: RuleSet, lot_width_ft: float, is_corner: bool) -> tuple[VariantDecision, bool]:
    """Interior side setback and whether reassignment between sides is allowed."""
    base = float(rs.rule(SIDE_SETBACK)["value"])
    width_min, _ = lot_width_minimum(rs, is_corner)
    narrow = rs.params(SIDE_SETBACK, "narrow_lot")
    if lot_width_ft < width_min - LENGTH_EQ_TOL_FT:
        variant, value = "narrow_lot", narrow["fraction_of_width"] * lot_width_ft
        predicate = f"lot_width={lot_width_ft:.2f} < {width_min:g} -> {narrow['fraction_of_width']:.0%} of width"
    else:
        variant, value = BASE_VARIANT, base
        predicate = f"lot_width={lot_width_ft:.2f} >= {width_min:g}"
    reassignment = rs.params(SIDE_SETBACK, "reassignment")
    allowed = lot_width_ft > reassignment["width_above_ft"] + LENGTH_EQ_TOL_FT
    predicate += f"; reassignment {'allowed' if allowed else 'not allowed'} (width > {reassignment['width_above_ft']:g})"
    return _decision(rs, SIDE_SETBACK, "side_setback", [variant], value, "ft", predicate), allowed


def street_side_setback(rs: RuleSet) -> VariantDecision:
    value = float(rs.rule(STREET_SIDE_SETBACK)["value"])
    return _decision(
        rs, STREET_SIDE_SETBACK, "street_side_setback", [BASE_VARIANT], value, "ft", f"base {value:g} ft"
    )


def rear_setback(rs: RuleSet, lot_depth_ft: float, alley_width_ft: float = 0.0) -> VariantDecision:
    base = float(rs.rule(REAR_SETBACK)["value"])
    shallow = rs.params(REAR_SETBACK, "shallow_lot")
    deep = rs.params(REAR_SETBACK, "deep_lot")
    if lot_depth_ft < shallow["depth_below_ft"] - LENGTH_EQ_TOL_FT:
        variants = ["shallow_lot"]
        value = max(shallow["fraction_of_depth"] * lot_depth_ft, shallow["min_ft"])
        predicate = f"lot_depth={lot_depth_ft:.2f} < {shallow['depth_below_ft']:g}"
    elif lot_depth_ft > deep["depth_above_ft"] + LENGTH_EQ_TOL_FT:
        variants = ["deep_lot"]
        value = max(deep["fraction_of_depth"] * lot_depth_ft, base)
        predicate = f"lot_depth={lot_depth_ft:.2f} > {deep['depth_above_ft']:g}"
    else:
        variants, value = [BASE_VARIANT], base
        predicate = f"{shallow['depth_below_ft']:g} <= lot_depth={lot_depth_ft:.2f} <= {deep['depth_above_ft']:g}"
    if alley_width_ft > 0:
        alley = rs.params(REAR_SETBACK, "alley")
        credit = min(alley_width_ft * alley["alley_fraction"], alley["credit_max_ft"])
        value = max(value - credit, alley["min_inside_ft"])
        variants.append("alley")
        predicate += f"; alley {alley_width_ft:g} ft -> credit {credit:g} ft"
    return _decision(rs, REAR_SETBACK, "rear_setback", variants, value, "ft", predicate)


# --------------------------------------------------------------------------- intensity


def floor_area_ratio(
    rs: RuleSet, lot_area_sqft: float, steep_fraction: float
) -> tuple[VariantDecision, Quantity]:
    """FAR row by lot area and the area FAR applies to (reduced on hillside lots)."""
    rule = rs.rule(FAR)
    lower = 0.0
    for row in rule["table"]:
        upper = row["max_lot_area_sqft"]
        if upper is None or lot_area_sqft <= upper + 1e-9:
            far, band = row["far"], f"({lower:g}, {'inf' if upper is None else f'{upper:g}'}]"
            break
        lower = upper
    zone_min = float(rs.rule(LOT_AREA_MIN)["value"])
    hillside = rs.params(FAR, "hillside")
    variants = [BASE_VARIANT]
    predicate = f"lot_area={lot_area_sqft:.1f} in {band}"
    base_area = lot_area_sqft
    if steep_fraction > hillside["steep_fraction_above"] and lot_area_sqft > zone_min:
        non_steep = lot_area_sqft * (1.0 - steep_fraction)
        anchor = max(non_steep, zone_min)
        base_area = anchor + hillside["remainder_fraction"] * (lot_area_sqft - anchor)
        variants.append("hillside")
        predicate += f"; steep_fraction={steep_fraction:.2f} > {hillside['steep_fraction_above']}"
    decision = _decision(rs, FAR, "floor_area_ratio", variants, far, "ratio", predicate)
    base_q = Quantity.derived(base_area, "sq_ft", [decision.quantity], note="area the FAR applies to")
    return decision, base_q


def hillside_coverage(rs: RuleSet, steep_fraction: float) -> VariantDecision:
    rule = rs.rule(HILLSIDE_COVERAGE)
    threshold = rule["parameters"]["steep_fraction_above"]
    if steep_fraction > threshold:
        return _decision(
            rs, HILLSIDE_COVERAGE, "lot_coverage", [BASE_VARIANT], rule["value"], "ratio",
            f"steep_fraction={steep_fraction:.2f} > {threshold}",
        )
    return _decision(
        rs, HILLSIDE_COVERAGE, "lot_coverage", [BASE_VARIANT], None, "ratio",
        f"steep_fraction={steep_fraction:.2f} <= {threshold}: no coverage limit in RS-1-7",
    )


def height_limit(rs: RuleSet, overlay_map_limit_ft: float | None) -> VariantDecision:
    rule = rs.rule(HEIGHT_MAX)
    base = float(rule["value"])
    if overlay_map_limit_ft is not None and overlay_map_limit_ft < base:
        return _decision(
            rs, HEIGHT_MAX, "structure_height", ["height_limit_overlay_map"], overlay_map_limit_ft, "ft",
            f"overlay map {overlay_map_limit_ft:g} ft < zone {base:g} ft", note=rule.get("note"),
        )
    return _decision(
        rs, HEIGHT_MAX, "structure_height", [BASE_VARIANT], base, "ft",
        f"zone value {base:g} ft (options {rule.get('value_options_ft')})", note=rule.get("note"),
    )


def third_floor_limits(rs: RuleSet, lot_width_ft: float, lot_depth_ft: float) -> dict[str, Quantity]:
    p = rs.rule(THIRD_FLOOR)["parameters"]
    status, source = rs.status(THIRD_FLOOR), rs.source_tag(THIRD_FLOOR)
    note = rs.rule(THIRD_FLOOR).get("note")
    max_width = p["width_fraction_of_lot_width"] * lot_width_ft
    max_depth = max(p["depth_fraction_of_lot_depth"] * lot_depth_ft, p["depth_fraction_of_third_floor_width"] * max_width)
    return {
        "max_width": Quantity(max_width, "ft", status, (source,), note),
        "max_depth": Quantity(max_depth, "ft", status, (source,), note),
    }


def angled_plane(rs: RuleSet, lot_width_ft: float) -> dict:
    rule = rs.rule(ANGLED_PLANE)
    p = rule["parameters"]
    if lot_width_ft < p["narrow_width_below_ft"]:
        angle = p["narrow_angle_deg"]
    elif lot_width_ft <= p["wide_width_max_ft"]:
        angle = p["wide_angle_deg"]
    else:
        angle = None
    return {
        "angle_deg": angle,
        "front_trigger_height_ft": p["front_trigger_height_ft"],
        "applied": False,
        "status": rs.status(ANGLED_PLANE),
        "source": rs.source_tag(ANGLED_PLANE),
        "note": rule.get("note", ""),
    }


# --------------------------------------------------------------------------- lot conformity


def lot_conformity(
    rs: RuleSet,
    lot_area_sqft: float,
    lot_width_ft: float,
    lot_depth_ft: float,
    frontage_ft: float,
    is_corner: bool,
    curve_radius_ft: float | None,
    measurement_status: str,
) -> list[dict]:
    width_min, width_variant = lot_width_minimum(rs, is_corner)
    frontage_min = float(rs.rule(FRONTAGE_MIN)["value"])
    frontage_variant = BASE_VARIANT
    curved = rs.params(FRONTAGE_MIN, "curved_street")
    if curve_radius_ft is not None and curve_radius_ft < curved["radius_below_ft"]:
        frontage_min *= curved["fraction_of_minimum"]
        frontage_variant = "curved_street"
    checks = [
        ("lot_area", LOT_AREA_MIN, BASE_VARIANT, lot_area_sqft, float(rs.rule(LOT_AREA_MIN)["value"]), "sq_ft", None),
        ("lot_width", LOT_WIDTH_MIN, width_variant, lot_width_ft, width_min, "ft", measurement_status),
        ("lot_depth", LOT_DEPTH_MIN, BASE_VARIANT, lot_depth_ft, float(rs.rule(LOT_DEPTH_MIN)["value"]), "ft", measurement_status),
        ("street_frontage", FRONTAGE_MIN, frontage_variant, frontage_ft, frontage_min, "ft", None),
    ]
    out = []
    for check_id, rule_id, variant, value, required, unit, extra in checks:
        status = rs.status(rule_id, variant)
        if extra:
            status = worst_status(status, extra)
        out.append(
            {
                "check_id": check_id,
                "rule_id": rule_id,
                "value": value,
                "required": required,
                "unit": unit,
                "passes": value >= required - LENGTH_EQ_TOL_FT,
                "status": status,
                "source": rs.source_tag(rule_id, variant),
            }
        )
    return out


# --------------------------------------------------------------------------- site (layer 1)

FRONT_PAVEMENT = "Z10-FRONT-PAVEMENT"
PROJECTIONS = "Z11-PROJECTIONS"


def front_pavement_limits(rs: RuleSet) -> dict:
    rule = rs.rule(FRONT_PAVEMENT)
    deck = rs.params(FRONT_PAVEMENT, "deck_counts_as_paving")
    return {
        "max_fraction": float(rule["value"]),
        "vehicle_limit": rule["parameters"]["vehicle_limit"],
        "vehicle_limit_lot_area_below_sqft": rule["parameters"]["vehicle_limit_lot_area_below_sqft"],
        "deck_counts": bool(deck["counts"]),
        "status": rs.status(FRONT_PAVEMENT),
        "deck_status": rs.status(FRONT_PAVEMENT, "deck_counts_as_paving"),
        "source": rs.source_tag(FRONT_PAVEMENT),
    }


def porch_projection_limit(rs: RuleSet, front_setback_ft: float) -> dict:
    p = rs.params(PROJECTIONS, "porch_entry")
    return {
        "max_projection_ft": min(p["max_projection_ft"], p["max_fraction_of_setback"] * front_setback_ft),
        "max_height_ft": p["max_height_ft"],
        "min_open_fraction": p["min_open_fraction"],
        "status": rs.status(PROJECTIONS, "porch_entry"),
        "source": rs.source_tag(PROJECTIONS, "porch_entry"),
    }


def equipment_clearance(rs: RuleSet) -> dict:
    p = rs.params(PROJECTIONS, "mechanical_equipment")
    return {
        "min_distance_to_line_ft": p["min_distance_to_line_ft"],
        "status": rs.status(PROJECTIONS, "mechanical_equipment"),
        "source": rs.source_tag(PROJECTIONS, "mechanical_equipment"),
    }
