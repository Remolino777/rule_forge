"""Vertical rules (step 6.7): angled-plane geometry, height measurement, stories and basements.

Reads the vertical ruleset (data/rules/sdmc_rs_1_7_vertical.json); no normative number lives in this file. The
plane angle by lot width and the front trigger height come already resolved from the capacity layer
(lot_capacity.capacity.envelope_plane, rule Z06); this module adds how they combine with the start and overall
heights (V01), how heights are measured (V02) and how stories and basements are classified (V03, V04).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from spaceplan.core.lib.rules import RuleSet, load_ruleset, load_ruleset_resource

VERTICAL_RULESET = ("data", "rules", "sdmc_rs_1_7_vertical.json")
PLANE_RULE = "V01-ANGLED-PLANE-GEOMETRY"
HEIGHT_RULE = "V02-HEIGHT-MEASUREMENT"
BASEMENT_RULE = "V03-BASEMENT-GFA"
STORY_RULE = "V04-STORY-DEFINITION"
GARAGE_RULE = "V05-GARAGE-GFA"
FLAT, SLOPED = "flat", "sloped"


def load_vertical_ruleset(path: str | Path | None = None) -> RuleSet:
    return load_ruleset(path) if path else load_ruleset_resource(*VERTICAL_RULESET)


@dataclass(frozen=True)
class HeightEnvelope:
    """Height limits of one lot: the plane starts at `start_ft` on the side setback line, leans inward at
    `angle_deg` from the vertical and stops at `overall_max_ft`; front planes only above `front_trigger_ft`."""

    start_ft: float
    overall_max_ft: float
    angle_deg: float | None
    front_trigger_ft: float | None
    status: str
    sources: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {"plane_start_ft": self.start_ft, "overall_max_ft": self.overall_max_ft, "angle_deg": self.angle_deg,
                "front_trigger_ft": self.front_trigger_ft, "status": self.status, "sources": list(self.sources)}


def height_envelope(rs: RuleSet, envelope_plane: dict[str, Any]) -> HeightEnvelope:
    """Combine the plane resolved by lotcap (angle, front trigger) with the start and overall heights of V01."""
    p = rs.params(PLANE_RULE)
    statuses = {rs.status(PLANE_RULE), envelope_plane.get("status", "provisional")}
    return HeightEnvelope(
        start_ft=float(p["plane_start_height_ft"]),
        overall_max_ft=float(p["overall_max_height_ft"]),
        angle_deg=envelope_plane.get("angle_deg"),
        front_trigger_ft=envelope_plane.get("front_trigger_height_ft"),
        status="provisional" if "provisional" in statuses else "verified",
        sources=(rs.source_tag(PLANE_RULE), envelope_plane.get("source", "SDMC 131.0444(b)(c)")),
    )


def overall_height_limit(rs: RuleSet, overall_max_ft: float, grade_differential_ft: float) -> float:
    """113.0270(a)(2)(B): overall height may reach the zone maximum plus the grade differential within the
    footprint, capped."""
    cap = rs.params(HEIGHT_RULE)["overall_height_extra_cap_ft"]
    return overall_max_ft + min(max(grade_differential_ft, 0.0), cap)


def first_story_ok(rs: RuleSet, ground_floor_above_grade_ft: float) -> bool:
    """113.0261(a): the ground level is the first story when its floor is not too far above grade."""
    return ground_floor_above_grade_ft <= rs.params(STORY_RULE)["first_story_max_floor_above_grade_ft"]


def slope_class(rs: RuleSet, slope: float | None) -> str:
    threshold = rs.params(BASEMENT_RULE)["slope_threshold"]
    return SLOPED if (slope or 0.0) >= threshold else FLAT


def classify_below_grade(rs: RuleSet, exposure_ft: float, slope: float | None) -> dict[str, Any]:
    """A level below the ground floor whose finish floor above sits `exposure_ft` over grade (lower of existing
    or proposed): counted in the gross floor area (113.0234(a)(2)) and/or a story (113.0261(d))."""
    cls = slope_class(rs, slope)
    params = rs.params(BASEMENT_RULE)
    threshold = params["flat_exposure_ft"] if cls == FLAT else params["sloped_exposure_ft"]
    story_at = rs.params(STORY_RULE)["basement_story_exposure_ft"]
    counts = exposure_ft > threshold
    is_story = exposure_ft >= story_at
    band = "story" if is_story else ("gfa_not_story" if counts else "outside_gfa")
    return {"exposure_ft": exposure_ft, "slope_class": cls, "gfa_threshold_ft": threshold,
            "story_threshold_ft": story_at, "counts_in_gfa": counts, "is_story": is_story, "band": band,
            "sources": [rs.source_tag(BASEMENT_RULE), rs.source_tag(STORY_RULE)]}


def garage_counts_in_gfa(rs: RuleSet) -> bool:
    return bool(rs.rule(GARAGE_RULE)["value"])


__all__ = [
    "BASEMENT_RULE",
    "FLAT",
    "GARAGE_RULE",
    "HEIGHT_RULE",
    "PLANE_RULE",
    "SLOPED",
    "STORY_RULE",
    "VERTICAL_RULESET",
    "HeightEnvelope",
    "classify_below_grade",
    "first_story_ok",
    "garage_counts_in_gfa",
    "height_envelope",
    "load_vertical_ruleset",
    "overall_height_limit",
    "slope_class",
]
