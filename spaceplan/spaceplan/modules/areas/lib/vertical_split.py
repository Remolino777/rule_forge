"""Vertical distribution schemes (step 6.6): which spaces go on which floor, at the level of areas.

A scheme (catalog `vertical_schemes`) assigns groups of spaces to floors. Groups come from the household
role and the space type (primary suite, children, teenagers, guests, work, laundry, social, ...). The
household never excludes a scheme: it weighs the metrics (stair dependency, supervision, separation)
through catalog multipliers, and every applicable scheme competes with the same criterion.

Hard rules, applied after the scheme and recorded as exceptions:
  * a space with floor_preference 0 (reduced mobility, garage) stays on the ground floor;
  * hosted spaces follow their host (a closet in its bedroom, a pantry in its kitchen);
  * laundry follows the cultural aspect `laundry_location` (near the bedrooms or with the kitchen);
  * circulation (halls) is split in proportion to each floor's net area; a stair is added on every
    floor of a two-floor scheme (same convention as the quantity sheet of step 6.5b).

Everything here is areas: no geometry. The geometry of two floors is step 6.7.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from spaceplan.core.lib.catalog import Catalog
from spaceplan.core.lib_aux.predicates import evaluate

ENTRY_FLOOR = 0
RULE = "rule"


@dataclass(frozen=True)
class FloorSplit:
    """A program distributed over floors by one vertical scheme."""

    scheme_id: str
    floors: int
    floor_of: dict[str, int]
    group_of: dict[str, str]
    net_by_floor: tuple[float, ...]
    gross_by_floor: tuple[float, ...]
    gross_by_zone: dict[str, float]
    stair_sqft_per_floor: float
    exceptions: tuple[dict, ...] = field(default_factory=tuple)

    @property
    def gross(self) -> float:
        return sum(self.gross_by_floor)

    @property
    def ground(self) -> float:
        return self.gross_by_floor[0]

    @property
    def upper(self) -> float:
        return sum(self.gross_by_floor[1:])

    @property
    def shares(self) -> list[float]:
        total = self.gross or 1.0
        return [g / total for g in self.gross_by_floor]

    def signature(self) -> tuple:
        return (self.floors, tuple(sorted(self.floor_of.items())))

    def to_dict(self) -> dict[str, Any]:
        upper_spaces = sorted(s for s, f in self.floor_of.items() if f > 0)
        return {
            "scheme_id": self.scheme_id,
            "floors": self.floors,
            "gross_by_floor_sqft": [round(g, 1) for g in self.gross_by_floor],
            "net_by_floor_sqft": [round(n, 1) for n in self.net_by_floor],
            "stair_sqft_per_floor": self.stair_sqft_per_floor if self.floors > 1 else 0.0,
            "upper_spaces": upper_spaces,
            "exceptions": list(self.exceptions),
        }


SPACE_SPLIT_KEYS = ("space_id", "space_type", "zone", "household_role", "host_space_id")


def space_split(program: dict, split: FloorSplit) -> list[dict[str, Any]]:
    """Every space of the program with its floor and its target area (step 6.7a S2 reads it to zone each floor).

    The list reflects the split actually evaluated (balanced or trimmed program), which the portfolio does not."""
    out = []
    for s in program["spaces"]:
        sid = s["space_id"]
        out.append({**{k: s.get(k) for k in SPACE_SPLIT_KEYS}, "floor": split.floor_of.get(sid, ENTRY_FLOOR),
                    "area_sqft": round(float(s["target_area_sqft"]), 1)})
    return sorted(out, key=lambda r: (r["floor"], r["space_id"]))


def space_matches(match: dict, space: dict) -> bool:
    for key in ("household_role", "space_type", "zone"):
        if key in match and space.get(key) not in match[key]:
            return False
    return True


def group_of_space(vs: dict, space: dict) -> str:
    for g in vs["groups"]:
        if space_matches(g["match"], space):
            return g["group"]
    raise KeyError(f"space {space['space_id']!r} matches no vertical group")


def program_group_facts(vs: dict, program: dict) -> dict[str, int]:
    """Counts by group, used by the applicability predicates of the schemes."""
    counts = {g["group"]: 0 for g in vs["groups"]}
    for s in program["spaces"]:
        if s.get("host_space_id"):
            continue
        counts[group_of_space(vs, s)] += 1
    facts = {f"n_{g}": n for g, n in counts.items()}
    facts["n_bedroom_groups"] = sum(counts[g] for g in vs["bedroom_groups"])
    facts["n_secondary_upper"] = sum(counts[g] for g in ("child", "teen", "adult", "guest", "work") if g in counts)
    facts["n_occasional"] = counts.get("guest", 0) + counts.get("work", 0)
    return facts


def applicable_schemes(vs: dict, facts: dict[str, Any]) -> list[dict]:
    return [s for s in vs["schemes"] if evaluate(s["applies"], facts)]


def _laundry_floor(vs: dict, floor_of: dict[str, int], group_of: dict[str, str], areas: dict[str, float],
                   aspects: dict[str, Any]) -> int:
    rule = vs["laundry_rule"]
    if aspects.get(rule["aspect"]) != "near_bedrooms":
        return rule["otherwise"]
    by_floor: dict[int, float] = {}
    for sid, g in group_of.items():
        if g in vs["bedroom_groups"]:
            by_floor[floor_of[sid]] = by_floor.get(floor_of[sid], 0.0) + areas[sid]
    if not by_floor:
        return rule["otherwise"]
    return max(sorted(by_floor), key=lambda f: by_floor[f])


def split_program(catalog: Catalog, program: dict, scheme: dict, aspects: dict[str, Any]) -> FloorSplit:
    """Distribute a program over the floors of a scheme (areas only)."""
    vs = catalog.data["vertical_schemes"]
    floors = scheme["floors"]
    spaces = {s["space_id"]: s for s in program["spaces"]}
    areas = {sid: float(s["target_area_sqft"]) for sid, s in spaces.items()}
    group_of = {sid: group_of_space(vs, s) for sid, s in spaces.items()}
    assign = scheme["assign"]
    floor_of: dict[str, int] = {}
    exceptions: list[dict] = []

    for sid, s in spaces.items():
        if s.get("host_space_id"):
            continue
        g = group_of[sid]
        f = assign.get(g, ENTRY_FLOOR)
        floor_of[sid] = ENTRY_FLOOR if f == RULE else int(f)
    # hard rule: floor preference (reduced mobility, garage); a cohesive group (suite) moves as a whole
    cohesive = set(vs.get("cohesive_groups", []))
    for sid, s in spaces.items():
        pref = s.get("floor_preference")
        if sid not in floor_of or pref is None or pref >= floors or floor_of[sid] == pref:
            continue
        g = group_of[sid]
        members = [m for m in floor_of if group_of[m] == g] if g in cohesive else [sid]
        moved = [m for m in members if floor_of[m] != pref]
        for m in moved:
            floor_of[m] = pref
        exceptions.append({"space_id": sid, "group": g, "to_floor": pref, "moved": sorted(moved),
                           "reason": "floor_preference (household rule: mobility or garage)"
                           + ("; the suite stays together" if len(moved) > 1 else "")})
    # laundry rule (cultural aspect) over the non-hosted laundry
    if floors > 1:
        lf = _laundry_floor(vs, floor_of, group_of, areas, aspects)
        for sid, s in spaces.items():
            if (group_of[sid] == "laundry" and assign.get("laundry") == RULE and sid in floor_of
                    and s.get("floor_preference") is None):
                floor_of[sid] = lf
    # hosted spaces follow the host, except laundry that follows its rule
    for sid, s in spaces.items():
        host = s.get("host_space_id")
        if not host:
            continue
        if group_of[sid] == "laundry" and assign.get("laundry") == RULE and floors > 1:
            floor_of[sid] = _laundry_floor(vs, floor_of, group_of, areas, aspects)
        elif host in floor_of and group_of.get(host) != "circulation":
            floor_of[sid] = floor_of[host]
        else:
            floor_of[sid] = ENTRY_FLOOR
    return build_split(catalog, program, scheme["scheme_id"], floors, floor_of, group_of, exceptions)


def build_split(catalog: Catalog, program: dict, scheme_id: str, floors: int, floor_of: dict[str, int],
                group_of: dict[str, str], exceptions: list[dict] | tuple[dict, ...]) -> FloorSplit:
    """Areas per floor of a given assignment: circulation split in proportion to the other net area of each
    floor, gross factor of the program, a stair on every floor of a multi-floor split."""
    spaces = {s["space_id"]: s for s in program["spaces"]}
    areas = {sid: float(s["target_area_sqft"]) for sid, s in spaces.items()}
    circ = [sid for sid in spaces if group_of[sid] == "circulation"]
    net = [0.0] * floors
    for sid, f in floor_of.items():
        if sid not in circ:
            net[f] += areas[sid]
    circ_area = sum(areas[sid] for sid in circ)
    base = sum(net) or 1.0
    net = [n + circ_area * n / base for n in net]

    ci = catalog.data["cost_index"]
    declared = program.get("required_gross_area_sqft")
    total_net = sum(areas.values()) or 1.0
    scale = declared / total_net if declared else program.get("gross_factor", 1.0)
    stair = catalog.space_type(ci["estimates"]["stair_space_type"])["area"]["target"] if floors > 1 else 0.0
    gross = tuple(n * scale + stair for n in net)
    by_zone: dict[str, float] = {}
    for sid, s in spaces.items():
        by_zone[s["zone"]] = by_zone.get(s["zone"], 0.0) + areas[sid] * scale
    if stair:
        by_zone["circulation"] = by_zone.get("circulation", 0.0) + stair * floors
    return FloorSplit(scheme_id, floors, dict(floor_of), group_of, tuple(net), gross, by_zone, stair,
                      tuple(exceptions))


def has_empty_upper(catalog: Catalog, split: FloorSplit) -> bool:
    """True when nothing a household would climb for is upstairs (only baths, laundry or halls).

    Happens when a hard rule pins down what the scheme sent up (e.g. a suite kept on the ground floor
    by a mobility rule): the scheme then degenerates and is reported as not applicable."""
    if split.floors == 1:
        return False
    vs = catalog.data["vertical_schemes"]
    meaningful = {*vs["bedroom_groups"], "work", "social", "kitchen"}
    return not any(f > 0 and split.group_of[sid] in meaningful for sid, f in split.floor_of.items())


# ------------------------------------------------------------------------------------------- metrics


def vertical_metrics(catalog: Catalog, split: FloorSplit, program: dict, facts: dict[str, Any]) -> dict[str, float]:
    """Lot-independent metrics of a split in [0, 1] (1 = best)."""
    aa = catalog.data["area_analysis"]
    vs = catalog.data["vertical_schemes"]
    sc = vs["scoring"]
    spaces = {s["space_id"]: s for s in program["spaces"]}
    daily_types = set(aa["daily_use"]["space_types"])
    daily_roles = set(aa["daily_use"]["household_roles"])
    daily = [sid for sid, s in spaces.items()
             if s["space_type"] in daily_types or s.get("household_role") in daily_roles]
    daily_area = sum(spaces[sid]["target_area_sqft"] for sid in daily) or 1.0
    off = sum(spaces[sid]["target_area_sqft"] for sid in daily if split.floor_of[sid] != ENTRY_FLOOR)
    metrics = {"stair_independence": 1.0 - off / daily_area}

    def floors_of(groups) -> set[int]:
        return {split.floor_of[sid] for sid, g in split.group_of.items() if g in groups
                and not spaces[sid].get("host_space_id")}

    primary = floors_of({"primary"})
    sup = floors_of(set(sc["supervision_groups"]))
    if facts.get("children_0_5", 0) > 0 and sup and primary:
        metrics["supervision"] = 1.0 if sup <= primary else 0.0
    else:
        metrics["supervision"] = 1.0
    sep_ids = [sid for sid, g in split.group_of.items() if g in sc["separation_groups"]
               and not spaces[sid].get("host_space_id")]
    if sep_ids and primary:
        apart = sum(spaces[sid]["target_area_sqft"] for sid in sep_ids if split.floor_of[sid] not in primary)
        metrics["separation"] = apart / sum(spaces[sid]["target_area_sqft"] for sid in sep_ids)
    elif sep_ids:
        social = floors_of({"social"})
        apart = sum(spaces[sid]["target_area_sqft"] for sid in sep_ids if split.floor_of[sid] not in social)
        metrics["separation"] = 0.5 + 0.5 * apart / sum(spaces[sid]["target_area_sqft"] for sid in sep_ids)
    else:
        metrics["separation"] = 1.0
    if split.floors == 1:
        metrics["upper_efficiency"] = 1.0
    else:
        useful = split.upper - split.stair_sqft_per_floor * (split.floors - 1)
        metrics["upper_efficiency"] = min(1.0, useful / aa["upper_floor_min_useful_sqft"])
    return metrics


def metric_weights(catalog: Catalog, facts_now: dict[str, Any], facts_later: dict[str, Any] | None
                   ) -> tuple[dict[str, float], list[str]]:
    """Base weights times the household multipliers (trajectory: a rule fires if it holds now or later)."""
    sc = catalog.data["vertical_schemes"]["scoring"]
    weights = dict(sc["weights"])
    fired = []
    for m in sc["multipliers"]:
        now = evaluate(m["when"], facts_now)
        later = facts_later is not None and evaluate(m["when"], facts_later)
        if now or later:
            weights[m["metric"]] *= m["factor"]
            fired.append(m["rule_id"] + ("" if now else " (next stage)"))
    return weights, fired


def weighted_score(weights: dict[str, float], metrics: dict[str, float]) -> tuple[float, dict[str, float]]:
    total = sum(weights.values()) or 1.0
    parts = {k: weights[k] * metrics[k] / total for k in weights}
    return sum(parts.values()), parts


def dedupe_splits(splits: list[FloorSplit]) -> tuple[list[FloorSplit], dict[str, str]]:
    """Keep the first split of each distinct distribution; map the others to it."""
    seen: dict[tuple, str] = {}
    kept, equivalent = [], {}
    for sp in splits:
        sig = sp.signature()
        if sig in seen:
            equivalent[sp.scheme_id] = seen[sig]
        else:
            seen[sig] = sp.scheme_id
            kept.append(sp)
    return kept, equivalent


__all__ = [
    "FloorSplit",
    "applicable_schemes",
    "build_split",
    "dedupe_splits",
    "group_of_space",
    "has_empty_upper",
    "metric_weights",
    "space_split",
    "program_group_facts",
    "space_matches",
    "split_program",
    "vertical_metrics",
    "weighted_score",
]
