"""The stair core first (step V6.8 k1b, client 2026-10-14 12:47 and 2026-10-17 01:38).

    clear zones   the start (below) and the arrival (above) of the stair each get a clear zone at least as wide as the
                  stair and `stair.arrival_clear.depth_ft` deep (S1 sizes them); no door leaf swings over them (the
                  catalog's swing_forbidden_over); each lies wholly inside one zone unit (S2) and one space (S2.1),
                  a circulation one (foyer or hall below; hall or vestibule above);
    block         the stair and the zone of each floor are one block: S2 pins the receiving unit on the whole block
                  (its edges become band and column cuts), the frame takes the block's edges as candidate axes, and
                  the zone units the stair touches are scored (target `stair.core.units_touched_target`);
    joint edges   over the garage (and at the rear) the rear joint is an anchor of the U along it; the preselection
                  keeps `stair.joint.slots_per_edge` candidates per joint edge (side and rear);
    under stair   K13: a half bath never stands beside the stair (S2.1 check).

Every value comes from the design registry (data/rules/design_circulation_doors.json, P13-P15) and the client
ruleset (K13); no numbers live here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from spaceplan.modules.stacking.lib_aux.core_cells import labels_on, labels_touching

SIDE_EDGE, REAR_EDGE = "side", "rear"
VESTIBULE_TYPE = "vestibule"                      # the fixed vestibule of the half bath under the stair (S1.1)
PREFIX_CLEAR, PREFIX_CORE, PREFIX_JOINT = "stair.arrival_clear.", "stair.core.", "stair.joint."


@dataclass(frozen=True)
class CoreSettings:
    depth_ft: float = 0.0               # clear depth of each end zone (0: the catalog's zones)
    width_from_stair: bool = False      # each zone at least the stair's width
    single_space: bool = False          # each zone inside one unit / one space (hard)
    circulation_only: bool = False      # that unit / space is circulation (hard)
    block_first: bool = False           # S2 pins the receiving unit on the whole block
    touched_target: float = 0.0         # zone units the stair touches (target; scored)
    touched_weight: float = 0.0         # weight of that score in S2
    rear_anchor: bool = False           # rear joint tried over the garage and at the rear
    slots_per_edge: int = 0             # preselection slots per joint edge

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


def core_settings(values: dict[str, Any] | None, kinds: dict[str, str] | None = None) -> CoreSettings:
    """Settings from the registry values (an empty registry gives the pre-k1b behaviour). A soft `single_space` or
    `circulation_only` is not enforced (reported only)."""
    v = values or {}
    k = kinds or {}

    def hard(pid: str) -> bool:
        return bool(v.get(pid)) and k.get(pid, "hard") == "hard"

    return CoreSettings(
        depth_ft=float(v.get(PREFIX_CLEAR + "depth_ft") or 0.0),
        width_from_stair=bool(v.get(PREFIX_CLEAR + "width_from_stair")),
        single_space=hard(PREFIX_CLEAR + "single_space"),
        circulation_only=hard(PREFIX_CLEAR + "circulation_only"),
        block_first=bool(v.get(PREFIX_CORE + "block_first")),
        touched_target=float(v.get(PREFIX_CORE + "units_touched_target") or 0.0),
        touched_weight=float(v.get(PREFIX_CORE + "units_touched_weight") or 0.0),
        rear_anchor=bool(v.get(PREFIX_JOINT + "rear_anchor")),
        slots_per_edge=int(v.get(PREFIX_JOINT + "slots_per_edge") or 0))


# ------------------------------------------------------------------ S1: the zones' size


def zone_cfg(cfg: dict[str, Any], cs: CoreSettings | None) -> dict[str, Any]:
    """The stair search settings with the clear zones of k1b: both ends at least `depth_ft` deep; the arrival zone at
    least as wide as the stair (`top_width_from_stair`; the start zone already is)."""
    if cs is None or (cs.depth_ft <= 0.0 and not cs.width_from_stair):
        return cfg
    out = dict(cfg)
    out["landing_ft"] = max(float(cfg["landing_ft"]), cs.depth_ft)
    out["top_depth_ft"] = max(float(cfg["top_depth_ft"]), cs.depth_ft)
    out["top_width_from_stair"] = cs.width_from_stair
    return out


# ------------------------------------------------------------------ S1.2: joint edges


def edge_class(line) -> str:
    """'rear' for a joint line across the depth (parallel to the street, local frame: street at low y), 'side' for one
    along it."""
    (x0, y0), (x1, y1) = line.coords[0], line.coords[-1]
    return REAR_EDGE if abs(x1 - x0) >= abs(y1 - y0) else SIDE_EDGE


# ------------------------------------------------------------------ S2: the zone units the stair touches


def touched_score(n: int, cs: CoreSettings) -> float:
    """1 when the stair touches at most the target number of units, falling as 1 / (1 + extra) beyond it."""
    target = max(1.0, cs.touched_target)
    return 1.0 if n <= target else 1.0 / (1.0 + n - target)


# ------------------------------------------------------------------ S2.1 checks


def clear_zone_violation(labels: np.ndarray, specs, landing: np.ndarray, cs: CoreSettings,
                         circulation_types: tuple[str, ...], entry_types: tuple[str, ...]) -> str | None:
    """The end zone of the stair on this floor lies in one space (fixed entry vestibule cells aside) and that space is
    circulation. None when it passes or the settings are off."""
    if cs is None or not (cs.single_space or cs.circulation_only) or landing is None or not landing.any():
        return None
    on = labels_on(labels, landing)
    spaces = {k for k in on if specs[k].space_type not in entry_types}
    if cs.single_space and len(spaces) > 1:
        return "clear:split:" + "+".join(sorted(specs[k].space_type for k in spaces))
    if cs.circulation_only:
        bad = sorted({specs[k].space_type for k in spaces} - set(circulation_types))
        if bad:
            return f"clear:not_circulation:{bad[0]}"
    return None


def half_bath_beside_stair(labels: np.ndarray, specs, stair: np.ndarray, half_bath_types) -> str | None:
    """K13: a half bath that is not the fixed one under the stair never shares a wall with the stair."""
    if stair is None or not stair.any():
        return None
    for k in labels_touching(labels, stair):
        s = specs[k]
        if s.space_type in half_bath_types and not s.fixed:
            return "K13:half_bath_beside_stair"
    return None


def half_bath_opens_violation(doors, specs, half_bath_types, opens_to: tuple[str, ...],
                              passable: tuple[str, ...]) -> str | None:
    """K13: the half bath under the stair (a fixed node) and its vestibule open only onto the foyer or a hall (fixed
    entry vestibule and stair aside, `passable`); a door or opening from the pair to anything else fails."""
    group = {k for k, s in enumerate(specs) if s.fixed and (s.space_type in half_bath_types
                                                              or s.space_type == VESTIBULE_TYPE)}
    if not any(specs[k].space_type in half_bath_types for k in group):
        return None
    for d in doors:
        if (d.a in group) == (d.b in group):
            continue
        other = d.b if d.a in group else d.a
        if other < 0:
            continue
        t = specs[other].space_type
        if t not in opens_to and t not in passable:
            return f"K13:half_bath_opens_to:{t}"
    return None


__all__ = ["REAR_EDGE", "SIDE_EDGE", "CoreSettings", "clear_zone_violation", "core_settings", "edge_class",
           "half_bath_beside_stair", "half_bath_opens_violation", "touched_score", "zone_cfg"]
