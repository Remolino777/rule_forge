"""Vertical facts of a lot (step 6.7, stage S0): height envelope, floors the height allows, below-grade probe.

Read from the lot_capacity contract (lot metrics, side setback, the plane resolved by lotcap, terrain) and the
vertical ruleset; no geometry is computed here.
"""

from __future__ import annotations

from typing import Any

from spaceplan.core.lib.rules import RuleSet
from spaceplan.modules.stacking.lib.height_check import roof_profile
from spaceplan.modules.stacking.lib.stacking_catalog import StackingCatalog
from spaceplan.modules.stacking.lib.vertical_rules import (
    HeightEnvelope,
    classify_below_grade,
    first_story_ok,
    height_envelope,
    slope_class,
)
from spaceplan.modules.stacking.lib_aux.vertical_geometry import floor_sides

SLOPE_READING = "lot mean slope (approximate: 113.0234(a)(2) reads the slope along each footprint edge)"


def lot_width(lot_capacity: dict[str, Any]) -> float:
    metrics = lot_capacity["lot_metrics"]
    return float(metrics["widths_ft"][metrics["width_method"]])


def reference_rectangle(lot_capacity: dict[str, Any]) -> tuple[float | None, float | None]:
    """Width and depth of the strategy-A rectangle (inscribed in the envelope): the lot-level reference footprint
    for the roof estimate of floors_by_height (the stepped and polygonal footprints are wider but not rectangles)."""
    for r in lot_capacity.get("realizable_capacity", []):
        if r.get("strategy") == "A_inscribed_rectangle" and r.get("width_ft"):
            return r["width_ft"], r.get("depth_ft")
    return None, None


def lot_envelope(rs: RuleSet, lot_capacity: dict[str, Any]) -> HeightEnvelope:
    return height_envelope(rs, lot_capacity["capacity"]["envelope_plane"])


def floors_by_height(cat: StackingCatalog, envelope: HeightEnvelope, width_ft: float | None,
                     depth_ft: float | None) -> dict[str, int]:
    """Largest number of above-grade floors whose roof top stays under the overall maximum, per roof type
    (top floor approximated by the footprint rectangle)."""
    lv = cat.levels
    out = {}
    for roof in cat.roofs:
        n = 0
        while True:
            plate = lv["ground_floor_above_grade_ft"] + n * lv["floor_to_floor_ft"] + lv["top_floor_plate_ft"]
            sides = floor_sides((width_ft or 0.0) * (depth_ft or 0.0), width_ft or 0.0)
            top = roof_profile(roof, plate, sides.short, sides.short_is_width)["top_ft"]
            if top > envelope.overall_max_ft:
                break
            n += 1
        out[roof["roof_id"]] = n
    return out


def lot_vertical_facts(rs: RuleSet, cat: StackingCatalog, lot_capacity: dict[str, Any]) -> dict[str, Any]:
    cap = lot_capacity["capacity"]
    envelope = lot_envelope(rs, lot_capacity)
    terrain = lot_capacity.get("terrain") or {}
    slope = terrain.get("mean_slope")
    width_a, depth_a = reference_rectangle(lot_capacity)
    by_height = floors_by_height(cat, envelope, width_a, depth_a)
    return {
        "lot_id": lot_capacity["brief_id"],
        "lot_width_ft": round(lot_width(lot_capacity), 4),
        "width_method": lot_capacity["lot_metrics"]["width_method"],
        "side_setback_ft": cap["setbacks"]["side"]["value"],
        "height_envelope": envelope.to_dict(),
        "floors_max_capacity": cap["floors_max_height"]["value"],
        "floors_by_height": by_height,
        "third_floor_possible": max(by_height.values()) >= 3,
        "first_story_ok": first_story_ok(rs, cat.levels["ground_floor_above_grade_ft"]),
        "mean_slope": slope,
        "slope_class": slope_class(rs, slope),
        "slope_reading": SLOPE_READING,
        "below_grade_probe": [classify_below_grade(rs, e, slope) for e in cat.probe_exposures],
    }


__all__ = ["SLOPE_READING", "floors_by_height", "lot_envelope", "lot_vertical_facts", "lot_width", "reference_rectangle"]
