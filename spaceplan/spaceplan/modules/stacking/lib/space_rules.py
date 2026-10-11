"""Rules and design values of stage S2.1 (step 6.7a): spaces and doors inside each zone unit.

Three layers, read once per run (no number lives in this file):
  * normative: C01 (habitable area and least dimension), C03 (glazing ratio) and C06 (hall width) of the
    habitability ruleset; O01 (emergency escape of sleeping rooms), O02 (garage openings) and O03 (habitable rooms
    on the facade) of the openings ruleset; S08 (no door swing over the stair) of the stair ruleset;
  * client: K01 / K02 receiving spaces, K04 half-bath door (client stair ruleset);
  * design: the s21 block of the stacking catalog (door widths, frame, swing, facade conversion, search caps) and
    the residential catalog it points to (hall width, closets, space types).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from spaceplan.core.lib.rules import CRC_RULESET, RuleSet, load_ruleset, load_ruleset_resource

OPENINGS_RULESET = ("data", "rules", "crc_2025_openings.json")
HABITABLE_AREA_RULE, HABITABLE_DIMENSION_RULE = "C01-HABITABLE-AREA", "C01-HABITABLE-DIMENSION"
HALL_WIDTH_RULE = "C06-HALLWAY-WIDTH"
ESCAPE_RULE, GARAGE_OPENINGS_RULE, FACADE_RULE = "O01-EMERGENCY-ESCAPE", "O02-GARAGE-OPENINGS", "O03-HABITABLE-FACADE"
TOP_DOOR_RULE = "S08-STAIR-TOP-DOOR"
HALF_BATH_RULE = "K04-HALF-BATH-VESTIBULE"
INCH_FT = 1.0 / 12.0
ACCESSIBLE_PROFILE = "accessible"


def load_openings_ruleset(path: str | Path | None = None) -> RuleSet:
    return load_ruleset(path) if path else load_ruleset_resource(*OPENINGS_RULESET)


def catalog_value(catalog, ref: Any) -> Any:
    """A value of the s21 block, or the residential-catalog value it names with a dotted path
    ("circulation.design_width_ft")."""
    if not isinstance(ref, str) or "." not in ref:
        return ref
    node: Any = catalog.data
    for part in ref.split("."):
        node = node[part]
    return node


@dataclass(frozen=True)
class SpaceRules:
    """Everything stage S2.1 checks or scores, in feet and square feet."""

    s21: dict[str, Any]
    habitable_min_sqft: float
    habitable_min_side_ft: float
    habitable_exempt: frozenset[str]
    hall_min_ft: float
    hall_width_ft: float
    hall_width_accessible_ft: float
    hall_min_terminals: int
    max_aspect: float
    glazing_ratio: float
    light_exempt: frozenset[str]
    sleeping_types: frozenset[str]
    escape_width_ft: float
    garage_forbidden: frozenset[str]
    half_bath_types: frozenset[str]
    half_bath_door_to: frozenset[str]
    door_ft: dict[str, float]
    door_accessible_ft: float
    swing_forbidden: tuple[str, ...]
    closet_type: str
    closet_min_sqft: float
    closet_min_side_ft: float
    closet_max_sqft: float
    closet_hosts: frozenset[str]
    keep_fraction: float
    private_roles: frozenset[str]
    private_opens_to: frozenset[str]
    garage_opens_to: frozenset[str]
    statuses: dict[str, str] = field(default_factory=dict)

    def facade_need_ft(self, space_type: str, area_sqft: float, habitable: bool) -> float:
        """Exterior wall a space needs: glazing of a habitable room (O03 via C03) and the escape opening of a
        sleeping room (O01), each with the frame allowance; 0 when neither applies."""
        f = self.s21["facade"]
        need = 0.0
        if habitable and space_type not in self.light_exempt:
            need = area_sqft * self.glazing_ratio / float(f["glazing_height_ft"]) + float(f["frame_allowance_ft"])
        if space_type in self.sleeping_types:
            need = max(need, self.escape_width_ft + float(f["frame_allowance_ft"]))
        return need

    def leaf_ft(self, kind: str, accessible: bool) -> float:
        """Leaf of a door: clear width + stops (closet doors keep their own width)."""
        clear = self.door_ft["closet"] if kind == "closet" else (self.door_accessible_ft if accessible
                                                                 else self.door_ft["interior"])
        return clear + self.door_ft["leaf_over_clear"]

    def clear_ft(self, kind: str, accessible: bool) -> float:
        return self.door_ft["closet"] if kind == "closet" else (self.door_accessible_ft if accessible
                                                                else self.door_ft["interior"])


def space_rules(scat, catalog, crc: RuleSet, openings: RuleSet, stairs: RuleSet, client: RuleSet) -> SpaceRules:
    s21 = scat.s21
    lay, doors, left = s21["layout"], s21["doors"], s21["leftovers"]
    o3 = openings.params(FACADE_RULE)
    o1 = openings.params(ESCAPE_RULE)
    k04 = client.params(HALF_BATH_RULE)
    closet = catalog.space_type(left["closet_space_type"])
    circ = catalog.data["circulation"]
    s2doors = scat.s2["zone_doors"]
    return SpaceRules(
        s21=s21,
        habitable_min_sqft=float(crc.rule(HABITABLE_AREA_RULE)["value"]),
        habitable_min_side_ft=float(crc.rule(HABITABLE_DIMENSION_RULE)["value"]),
        habitable_exempt=frozenset(crc.params(HABITABLE_DIMENSION_RULE, "kitchen_exempt")["exempt_space_types"]),
        hall_min_ft=float(crc.rule(HALL_WIDTH_RULE)["value"]),
        hall_width_ft=float(catalog_value(catalog, lay["hall_width"])),
        hall_width_accessible_ft=float(catalog_value(catalog, lay["hall_width_accessible"])),
        hall_min_terminals=int(catalog_value(catalog, lay["hall_min_terminals"])),
        max_aspect=float(catalog_value(catalog, lay["max_aspect"])),
        glazing_ratio=float(crc.rule(o3["glazing_rule"])["value"]),
        light_exempt=frozenset(o3["artificial_light_exception"]["space_types"]),
        sleeping_types=frozenset(o1["sleeping_space_types"]),
        escape_width_ft=float(o1["min_clear_width_in"]) * INCH_FT,
        garage_forbidden=frozenset(openings.params(GARAGE_OPENINGS_RULE)["forbidden_space_types"]),
        half_bath_types=frozenset(k04["space_types"]),
        half_bath_door_to=frozenset(k04["door_to_allowed"]),
        door_ft={"interior": float(doors["interior_clear_width_in"]) * INCH_FT,
                 "closet": float(doors["closet_clear_width_in"]) * INCH_FT,
                 "leaf_over_clear": float(doors["leaf_over_clear_in"]) * INCH_FT,
                 "frame": float(doors["frame_in"]) * INCH_FT,
                 "corner_return": float(doors["corner_return_in"]) * INCH_FT,
                 "opening": float(doors["opening_width_ft"])},
        door_accessible_ft=float(catalog_value(catalog, doors["accessible_clear_width_in"])) * INCH_FT,
        swing_forbidden=tuple(doors["swing_forbidden_over"]),
        closet_type=left["closet_space_type"],
        closet_min_sqft=float(closet["area"]["min"]),
        closet_min_side_ft=float(closet["min_side_ft"]),
        closet_max_sqft=float(closet["area"]["max"]),
        closet_hosts=frozenset(left["closet_hosts"]),
        keep_fraction=float(left["keep_in_space_below_fraction"]),
        private_roles=frozenset(circ["private_roles"]),
        private_opens_to=frozenset(s2doors["private_opens_to"]),
        garage_opens_to=frozenset(s2doors["garage_opens_to"]),
        statuses={r: rs.status(r) for rs, r in ((crc, HABITABLE_AREA_RULE), (crc, HABITABLE_DIMENSION_RULE),
                                                (crc, HALL_WIDTH_RULE), (openings, ESCAPE_RULE),
                                                (openings, GARAGE_OPENINGS_RULE), (openings, FACADE_RULE),
                                                (stairs, TOP_DOOR_RULE))},
    )


def load_crc_ruleset() -> RuleSet:
    return load_ruleset_resource(*CRC_RULESET)


__all__ = [
    "ACCESSIBLE_PROFILE",
    "ESCAPE_RULE",
    "FACADE_RULE",
    "GARAGE_OPENINGS_RULE",
    "HABITABLE_AREA_RULE",
    "HABITABLE_DIMENSION_RULE",
    "HALF_BATH_RULE",
    "HALL_WIDTH_RULE",
    "OPENINGS_RULESET",
    "TOP_DOOR_RULE",
    "SpaceRules",
    "catalog_value",
    "load_crc_ruleset",
    "load_openings_ruleset",
    "space_rules",
]
