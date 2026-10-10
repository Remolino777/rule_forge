"""Stacking catalog (step 6.7): design parameters of the vertical layer, with source and status.

A separate catalog owned by the stacking module (like the household catalog), so the residential catalog and the
golden packages stay unchanged. Normative values are not here: they live in the rulesets.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from spaceplan.core.lib_aux.hashing import sha256_of
from spaceplan.core.lib_aux.json_io import load_json, load_resource_json

STACKING_CATALOG = ("data", "catalog", "stacking_catalog.json")
ROOF_KINDS = ("flat", "pitched")


class StackingCatalogError(ValueError):
    pass


@dataclass(frozen=True)
class StackingCatalog:
    data: dict[str, Any]
    sha256: str

    @property
    def version(self) -> str:
        return self.data["catalog_version"]

    @property
    def levels(self) -> dict[str, Any]:
        return self.data["levels"]

    @property
    def default_mode(self) -> str:
        return self.data["selection"]["default_mode"]

    def stage_default_mode(self, stage: str) -> str:
        """Selection mode a stage uses when none is given (S1 draws fewer cells than S0 checks)."""
        return self.data["selection"].get("stage_default_modes", {}).get(stage, self.default_mode)

    def selection_k(self, mode: str | None) -> int | None:
        """Rank cut of a selection mode (None = every ranked cell)."""
        modes = self.data["selection"]["modes"]
        mode = mode or self.default_mode
        if mode not in modes:
            raise StackingCatalogError(f"unknown selection mode {mode!r}; expected one of {', '.join(modes)}")
        return modes[mode]

    @property
    def roofs(self) -> list[dict[str, Any]]:
        return self.data["roofs"]["types"]

    @property
    def default_roof(self) -> str:
        return self.data["roofs"]["default_roof"]

    def roof(self, roof_id: str) -> dict[str, Any]:
        for roof in self.roofs:
            if roof["roof_id"] == roof_id:
                return roof
        raise StackingCatalogError(f"unknown roof {roof_id!r}")

    @property
    def stair_space_type(self) -> str:
        return self.data["stair"]["space_type"]

    @property
    def stair_tolerance_sqft(self) -> float:
        return self.data["stair"]["consistency_tolerance_sqft"]

    @property
    def probe_exposures(self) -> list[float]:
        return list(self.data["below_grade"]["probe_exposures_ft"])

    # ----------------------------------------------------------------- stage S1

    @property
    def stair_design(self) -> dict[str, Any]:
        return self.data["stair"]["design"]

    @property
    def access_core(self) -> dict[str, Any]:
        """Design values of stage S1.2 (access core: door, vestibule, walls, strategies, void)."""
        if "access_core" not in self.data:
            raise StackingCatalogError("stacking catalog has no access_core block (stage S1.2 needs >= 0.6.0)")
        return self.data["access_core"]

    def stair_type(self, stair_id: str) -> dict[str, Any]:
        return next(t for t in self.data["stair"]["types"] if t["stair_id"] == stair_id)

    @property
    def stair_types(self) -> list[dict[str, Any]]:
        """Enabled stair configurations (stage S1.1 compares all of them)."""
        by_id = {t["stair_id"]: t for t in self.data["stair"]["types"]}
        return [by_id[i] for i in self.data["stair"]["enabled"]]

    @property
    def stair_search_step(self) -> float:
        return float(self.data["stair"]["placement"]["search_step_ft"])

    @property
    def stair_placement(self) -> dict[str, Any]:
        return self.data["stair"]["placement"]

    @property
    def under_stair(self) -> dict[str, Any]:
        return self.data["stair"]["under_stair"]

    @property
    def stair_access(self) -> dict[str, Any]:
        return self.data["stair_access"]

    def bottom_options(self, scheme_id: str | None) -> tuple[list[str], str]:
        """Bottom-start options allowed for a vertical scheme and the one stage S2 tries first."""
        acc = self.data["stair_access"]
        opts = acc["bottom_options_by_scheme"]
        pref = acc["bottom_preferred_by_scheme"]
        return list(opts.get(scheme_id or "", opts["default"])), pref.get(scheme_id or "", pref["default"])

    def upper_placements(self, scheme_id: str | None) -> list[str]:
        """Upper-floor placements in the order stage S1 tries them for a vertical scheme."""
        uf = self.data["upper_floor"]
        return list(uf.get("scheme_order", {}).get(scheme_id or "", uf["placements"]))

    @property
    def garage(self) -> dict[str, Any]:
        return self.data["garage"]

    @property
    def roof_order(self) -> list[str]:
        return list(self.data["roof_orientation"]["order"])

    @property
    def flat_roof_id(self) -> str:
        return self.data["roof_orientation"]["flat_roof"]

    @property
    def geometry(self) -> dict[str, Any]:
        return self.data["geometry"]

    # ----------------------------------------------------------------- stage S2

    @property
    def s2(self) -> dict[str, Any]:
        """Design values of stage S2 (zoning around the stair core)."""
        if "s2" not in self.data:
            raise StackingCatalogError("stacking catalog has no s2 block (stage S2 needs catalog >= 0.5.0)")
        return self.data["s2"]


STAIR_TYPES = ("straight", "straight_landing", "l_turn", "u_turn", "u_well")
CHOICE_KEYS = ("net_ground_bucket", "half_bath_fit", "entry_distance_ft", "joint_offset_ft")
BOTTOM_OPTIONS = ("A", "B", "C")
PLACEMENTS = ("rear", "front", "over_garage", "compact")
ROOF_STEPS = ("default", "rotated", "flat")
S1_BLOCKS = ("upper_floor", "garage", "roof_orientation", "geometry", "stair_access")


def _check_s1(data: dict[str, Any]) -> list[str]:
    """Structural problems of the stage-S1 blocks."""
    problems = []
    for key in S1_BLOCKS:
        if key not in data:
            problems.append(f"missing block {key!r}")
    stair = data["stair"]
    for key in ("design", "types", "enabled", "placement", "under_stair"):
        if key not in stair:
            problems.append(f"missing stair.{key}")
    if problems:
        return problems
    for key in ("tread_in", "width_ft", "landing_ft", "u_turn_gap_ft", "structure_depth_ft"):
        if not isinstance(stair["design"].get(key), (int, float)) or stair["design"][key] < 0:
            problems.append(f"stair.design.{key} must be a number >= 0")
    ids = [t.get("stair_id") for t in stair["types"]]
    if any(i not in STAIR_TYPES for i in ids):
        problems.append(f"stair.types: stair_id must be one of {STAIR_TYPES}")
    if not stair["enabled"] or any(i not in ids for i in stair["enabled"]):
        problems.append("stair.enabled must list declared stair types")
    if any(k not in CHOICE_KEYS for k in stair["placement"].get("choice", [])) or not stair["placement"].get("choice"):
        problems.append(f"stair.placement.choice must be drawn from {CHOICE_KEYS}")
    us = stair["under_stair"]
    if not us.get("bands") or us.get("usable_from_band") not in {b.get("band") for b in us["bands"]}:
        problems.append("stair.under_stair: bands missing or usable_from_band undeclared")
    if not isinstance(stair["placement"].get("half_bath_trials"), int) or stair["placement"]["half_bath_trials"] < 0:
        problems.append("stair.placement.half_bath_trials must be an integer >= 0")
    for key in ("half_bath_extension_max_ft", "vestibule_ft"):
        if not isinstance(us.get(key), (int, float)) or us[key] < 0:
            problems.append(f"stair.under_stair.{key} must be a number >= 0")
    acc = data["stair_access"]
    if not isinstance(acc.get("small_house_upper_rooms_max"), int) or acc["small_house_upper_rooms_max"] < 0:
        problems.append("stair_access.small_house_upper_rooms_max must be an integer >= 0")
    for key in ("bottom_options_by_scheme", "bottom_preferred_by_scheme"):
        if "default" not in acc.get(key, {}):
            problems.append(f"stair_access.{key} needs a default")
    for opts in acc.get("bottom_options_by_scheme", {}).values():
        if not opts or any(o not in BOTTOM_OPTIONS for o in opts):
            problems.append(f"stair_access.bottom_options_by_scheme must be drawn from {BOTTOM_OPTIONS}")
    for kind in ("hall", "upper_vestibule"):
        z = acc.get("top_zone", {}).get(kind, {})
        if not all(isinstance(z.get(k), (int, float)) and z[k] > 0 for k in ("depth_ft", "width_ft")):
            problems.append(f"stair_access.top_zone.{kind} needs depth_ft and width_ft > 0")
    if not isinstance(stair["placement"].get("search_step_ft"), (int, float)) or stair["placement"]["search_step_ft"] <= 0:
        problems.append("stair.placement.search_step_ft must be > 0")
    uf = data["upper_floor"]
    orders = [uf.get("placements", [])] + list(uf.get("scheme_order", {}).values())
    if not uf.get("placements") or any(p not in PLACEMENTS for order in orders for p in order):
        problems.append(f"upper_floor placements must be drawn from {PLACEMENTS}")
    if not isinstance(uf.get("compact_min_depth_ft"), (int, float)) or uf["compact_min_depth_ft"] <= 0:
        problems.append("upper_floor.compact_min_depth_ft must be a number > 0")
    g = data["garage"]
    if g.get("side") not in ("left", "right"):
        problems.append("garage.side must be 'left' or 'right'")
    for key in ("single_width_ft", "double_width_ft", "double_from_sqft", "max_width_fraction"):
        if not isinstance(g.get(key), (int, float)) or g[key] <= 0:
            problems.append(f"garage.{key} must be a number > 0")
    ro = data["roof_orientation"]
    if not ro.get("order") or any(s not in ROOF_STEPS for s in ro["order"]):
        problems.append(f"roof_orientation.order must be drawn from {ROOF_STEPS}")
    roof_ids = {r.get("roof_id") for r in data["roofs"].get("types", [])}
    if ro.get("flat_roof") not in roof_ids:
        problems.append("roof_orientation.flat_roof is not a declared roof")
    for key in ("area_tolerance_sqft", "round_ft", "bisection_rounds"):
        if not isinstance(data["geometry"].get(key), (int, float)) or data["geometry"][key] <= 0:
            problems.append(f"geometry.{key} must be a number > 0")
    return problems


S2_AXES = ("x", "y")
S2_WEIGHTS = ("relations", "vertical", "shape", "anchors", "stair_access")
ARRIVALS = ("family_room", "upper_vestibule", "hall")


def _check_s2(data: dict[str, Any]) -> list[str]:
    """Structural problems of the stage-S2 block (optional before catalog 0.5.0)."""
    s2 = data.get("s2")
    if s2 is None:
        return []
    problems = []
    if not isinstance(s2.get("grid_ft"), (int, float)) or s2["grid_ft"] <= 0:
        problems.append("s2.grid_ft must be a number > 0")
    topo = s2.get("topology", {})
    for floor in ("ground", "upper"):
        t = topo.get(floor, {})
        if not t.get("axes") or any(a not in S2_AXES for a in t["axes"]):
            problems.append(f"s2.topology.{floor}.axes must be drawn from {S2_AXES}")
        if t.get("max_bands") not in (1, 2):
            problems.append(f"s2.topology.{floor}.max_bands must be 1 or 2")
    if not isinstance(topo.get("max_topologies_per_floor"), int) or topo["max_topologies_per_floor"] < 1:
        problems.append("s2.topology.max_topologies_per_floor must be an integer >= 1")
    if sorted(s2.get("arrival_order", [])) != sorted(ARRIVALS):
        problems.append(f"s2.arrival_order must order {ARRIVALS}")
    if set(s2.get("weights", {})) != set(S2_WEIGHTS) or any(v < 0 for v in s2.get("weights", {}).values()):
        problems.append(f"s2.weights must give a number >= 0 for each of {S2_WEIGHTS}")
    share = s2.get("receiving_min_share")
    if not isinstance(share, (int, float)) or not 0 < share <= 1:
        problems.append("s2.receiving_min_share must be in (0, 1]")
    for key in ("D", "I"):
        if not isinstance(s2.get("vertical_depth_ok", {}).get(key), int):
            problems.append(f"s2.vertical_depth_ok.{key} must be an integer")
    for key in ("hall", "upper_vestibule"):
        if not isinstance(s2.get("circulation_min_sqft", {}).get(key), (int, float)):
            problems.append(f"s2.circulation_min_sqft.{key} must be a number")
    doors = s2.get("zone_doors", {})
    for key in ("private_opens_to", "garage_opens_to"):
        if not isinstance(doors.get(key), list):
            problems.append(f"s2.zone_doors.{key} must be a list of zones")
    if not isinstance(s2.get("keep_alternatives"), int) or s2["keep_alternatives"] < 0:
        problems.append("s2.keep_alternatives must be an integer >= 0")
    if s2.get("unit_min_width", {}).get("rule") not in ("space_sides", "zone"):
        problems.append("s2.unit_min_width.rule must be 'space_sides' or 'zone'")
    if "source" not in s2:
        problems.append("s2.source is missing")
    return problems


def check_stacking_catalog(data: dict[str, Any]) -> list[str]:
    """Structural problems of a stacking catalog (empty list = valid)."""
    problems = []
    for key in ("catalog_id", "catalog_version", "selection", "levels", "roofs", "stair", "below_grade"):
        if key not in data:
            problems.append(f"missing block {key!r}")
    if problems:
        return problems
    sel = data["selection"]
    if sel.get("default_mode") not in sel.get("modes", {}):
        problems.append("selection.default_mode is not one of selection.modes")
    if any(m not in sel.get("modes", {}) for m in sel.get("stage_default_modes", {}).values()):
        problems.append("selection.stage_default_modes values must be selection modes")
    for k in sel.get("modes", {}).values():
        if k is not None and (not isinstance(k, int) or k < 1):
            problems.append("selection.modes values must be integers >= 1 or null")
    for key in ("floor_to_floor_ft", "ground_floor_above_grade_ft", "top_floor_plate_ft"):
        value = data["levels"].get(key)
        if not isinstance(value, (int, float)) or value < 0:
            problems.append(f"levels.{key} must be a number >= 0")
    if data["levels"].get("floor_to_floor_ft", 0) <= 0:
        problems.append("levels.floor_to_floor_ft must be > 0")
    if "source" not in data["levels"]:
        problems.append("levels.source is missing")
    ids = [r.get("roof_id") for r in data["roofs"].get("types", [])]
    if len(ids) != len(set(ids)) or not ids:
        problems.append("roofs.types must have unique roof_id values")
    if data["roofs"].get("default_roof") not in ids:
        problems.append("roofs.default_roof is not a declared roof")
    for roof in data["roofs"].get("types", []):
        if roof.get("kind") not in ROOF_KINDS:
            problems.append(f"roof {roof.get('roof_id')!r}: kind must be one of {ROOF_KINDS}")
        elif roof["kind"] == "flat" and not isinstance(roof.get("parapet_ft"), (int, float)):
            problems.append(f"roof {roof['roof_id']!r}: flat roof needs parapet_ft")
        elif roof["kind"] == "pitched" and not isinstance(roof.get("pitch_rise_per_run"), (int, float)):
            problems.append(f"roof {roof['roof_id']!r}: pitched roof needs pitch_rise_per_run")
    if not data["below_grade"].get("probe_exposures_ft"):
        problems.append("below_grade.probe_exposures_ft is empty")
    return problems + _check_s1(data) + _check_s2(data)


def load_stacking_catalog(path: str | Path | None = None) -> StackingCatalog:
    data = load_json(path) if path else load_resource_json("spaceplan", *STACKING_CATALOG)
    problems = check_stacking_catalog(data)
    if problems:
        raise StackingCatalogError("invalid stacking catalog:\n  - " + "\n  - ".join(problems))
    return StackingCatalog(data=data, sha256=sha256_of(data))


__all__ = ["BOTTOM_OPTIONS", "CHOICE_KEYS", "PLACEMENTS", "ROOF_STEPS", "STACKING_CATALOG", "STAIR_TYPES", "StackingCatalog", "StackingCatalogError",
           "check_stacking_catalog", "load_stacking_catalog"]
