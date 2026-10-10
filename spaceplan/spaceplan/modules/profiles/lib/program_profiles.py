"""Program profiles (step 6.5d): minimum, optimum and maximum buildable, staged and accessible.

One expansion curve per household and lot:

    start   = the required tier (minimum program of the household)
    moves   = add one instance of a need toward its preferred/desirable count, apply a substitution
              (living-dining -> living + dining, bedroom -> suite, ...), upgrade one zone from the
              compact to the balanced size, add one garage car
    greedy  = always the feasible move with the best quality gain per unit of relative cost index
    ceiling = normative (gross area <= FAR maximum) and budget (index <= budget fraction)

    minimum = first point, maximum = last point (with the ceiling that stopped it),
    optimum = knee of quality vs cost (lib_aux.knee), staged = minimum today + expansion to the
    optimum of the next stage, accessible = optimum with a ground-floor bedroom and full bath.

    Client design variables (2026-10-09, optimum policy "footprint"): the optimum is the last point of the curve
    whose gross area fits one floor within the design footprint; the knee stays reported as a lens.

Quality is a program-level proxy (catalog program_quality, provisional) until the geometric score of
step 6.8. Nothing here reads money: the cost axis is the relative index of step 6.5b.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from spaceplan.core.lib.catalog import Catalog
from spaceplan.core.lib.enums import HOUSEHOLD_TIERS as TIERS
from spaceplan.core.lib_aux.knee import greedy_ratio_path, knee_index
from spaceplan.modules.cost.lib.cost_models import (
    CostModel,
    get_cost_model,
    mode_point,
    relative_index,
)
from spaceplan.modules.cost.lib.quantities import QuantitySheet, build_sheet
from spaceplan.modules.household.lib.household_catalog import HouseholdCatalog
from spaceplan.modules.household.lib.household_rules import Derivation
from spaceplan.modules.household.lib.program_builder import program_from_needs

NORMATIVE, BUDGET, COMPLETE = "normative", "budget", "program_complete"
REQUIRED, PREFERRED, DESIRABLE = TIERS
Key = tuple[str, str]


@dataclass(frozen=True)
class State:
    counts: tuple[int, ...]
    upgraded: frozenset[str]
    cars: int
    done: frozenset[str]


@dataclass
class _SyntheticNeed:
    space_type: str
    household_role: str
    counts: dict
    ground_counts: dict


@dataclass
class ProfileContext:
    """Everything the expansion needs for one household stage on one reading (lot or reference)."""

    catalog: Catalog
    hcat: HouseholdCatalog
    derivation: Derivation
    needs: list
    reference: QuantitySheet
    model: CostModel
    far_sqft: float | None = None
    budget_fraction: float | None = None
    next_needs: list | None = None
    floors_for_cost: int = 1
    strategy: str | None = None
    mean_slope: float | None = None
    _cache: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.keys: list[Key] = [(n.space_type, n.household_role) for n in self.needs]
        self.index_of = {k: i for i, k in enumerate(self.keys)}
        self.cap = [max(n.counts[t] for t in TIERS) for n in self.needs]
        self.req = [n.counts[REQUIRED] for n in self.needs]
        self.pref = [n.counts[PREFERRED] for n in self.needs]
        self.des = [max(n.counts[PREFERRED], n.counts[DESIRABLE]) for n in self.needs]
        culture_rules = {t["rule_id"] for t in self.derivation.trace if t["layer"] == "culture"}
        self.cultural = [bool(set(n.rule_ids) & culture_rules) for n in self.needs]
        subs = []
        for s in self.hcat.data["program_substitutions"]:
            src = (s["from"]["space_type"], s["from"]["household_role"])
            to = [(t["space_type"], t["household_role"]) for t in s["to"]]
            if src in self.index_of and all(t in self.index_of and self.pref[self.index_of[t]] > 0 for t in to):
                subs.append({**s, "src": src, "dst": to,
                             "rm": [(r["space_type"], r["household_role"]) for r in s["also_remove"]]})
        self.substitutions = subs
        self.sub_targets = {t: s["substitution_id"] for s in subs for t in s["dst"]}
        q = self.hcat.data["program_quality"]
        self.w = q["weights"]
        self.culture_multiplier = q["culture_multiplier"]
        profiles = self.catalog.data["profiles"]
        self.compact = profiles[self.hcat.tier(REQUIRED)["area_profile"]]
        self.balanced = profiles[self.hcat.tier(PREFERRED)["area_profile"]]
        self.size_zones = frozenset(z for z in self.compact if abs(self.compact[z] - self.balanced[z]) > 1e-9)
        self.cars_req = self.derivation.garage_cars[REQUIRED]
        self.cars_max = max(self.derivation.garage_cars.values())
        full = self.program(self.full_state())
        zone_area = Counter()
        for s in full["spaces"]:
            zone_area[s["zone"]] += s["target_area_sqft"]
        total = sum(zone_area.values()) or 1.0
        self.zone_share = {z: a / total for z, a in zone_area.items() if z in self.size_zones}
        self.next_pref = None
        if self.next_needs:
            self.next_pref = Counter({(n.space_type, n.household_role): n.counts[PREFERRED] for n in self.next_needs
                                      if n.counts[PREFERRED] > 0})
        self._gain_norm = 1.0
        self._gain_norm = self.raw_gain(self.full_state()) or 1.0
        self.point = mode_point(self.model, self.catalog.data["cost_index"])

    # ---------------------------------------------------------------------------------- states

    def start(self) -> State:
        return State(tuple(self.req), frozenset(), self.cars_req, frozenset())

    def full_state(self) -> State:
        counts = list(self.req)
        done = set()
        for s in self.substitutions:
            counts[self.index_of[s["src"]]] = 0
            for r in s["rm"]:
                if r in self.index_of:
                    i = self.index_of[r]
                    counts[i] = max(0, counts[i] - 1)
            done.add(s["substitution_id"])
        for i in range(len(counts)):
            if self.keys[i] in {s["src"] for s in self.substitutions}:
                continue
            counts[i] = max(counts[i], self.des[i])
        return State(tuple(counts), self.size_zones, self.cars_max, frozenset(done))

    def moves(self, s: State):
        for sub in self.substitutions:
            if sub["substitution_id"] not in s.done and s.counts[self.index_of[sub["src"]]] > 0:
                yield ("substitute", sub["substitution_id"])
        sources = {sub["src"] for sub in self.substitutions}
        for i, k in enumerate(self.keys):
            pending = k in self.sub_targets and self.sub_targets[k] not in s.done
            if k in sources or pending:
                continue
            if s.counts[i] < self.des[i]:
                yield ("add", f"{k[0]}:{k[1]}")
        for z in sorted(self.zone_share):
            if z not in s.upgraded:
                yield ("size", z)
        if s.cars < self.cars_max:
            yield ("car", str(s.cars + 1))

    def apply(self, s: State, move) -> State:
        kind, arg = move
        counts = list(s.counts)
        if kind == "substitute":
            sub = next(x for x in self.substitutions if x["substitution_id"] == arg)
            counts[self.index_of[sub["src"]]] = 0
            for t in sub["dst"]:
                i = self.index_of[t]
                counts[i] = max(counts[i], self.pref[i])
            for r in sub["rm"]:
                if r in self.index_of:
                    i = self.index_of[r]
                    counts[i] = max(0, counts[i] - 1)
            return State(tuple(counts), s.upgraded, s.cars, s.done | {arg})
        if kind == "add":
            st, role = arg.split(":")
            counts[self.index_of[(st, role)]] += 1
            return State(tuple(counts), s.upgraded, s.cars, s.done)
        if kind == "size":
            return State(s.counts, s.upgraded | {arg}, s.cars, s.done)
        return State(s.counts, s.upgraded, s.cars + 1, s.done)

    # --------------------------------------------------------------------------------- program

    def ground(self, i: int, c: int) -> int:
        n = self.needs[i]
        g = max((n.ground_counts[t] for t in TIERS if n.counts[t] <= c and n.counts[t] > 0), default=0)
        return min(c, max(g, n.ground_counts[REQUIRED] if c >= n.counts[REQUIRED] else 0))

    def program(self, s: State) -> dict:
        key = ("program", s)
        if key in self._cache:
            return self._cache[key]
        needs = [_SyntheticNeed(k[0], k[1], {"s": c}, {"s": self.ground(i, c)})
                 for i, (k, c) in enumerate(zip(self.keys, s.counts)) if c > 0]
        d = self.derivation
        zones = set(self.compact)
        zone_factors = {}
        for z in zones:
            tier = PREFERRED if z in s.upgraded else REQUIRED
            ratio = 1.0 if z in s.upgraded else self.compact[z] / self.balanced[z]
            zone_factors[z] = ratio * d.zone_factors[tier].get(z, 1.0)
        type_factors = {}
        for st in {n.space_type for n in needs}:
            zone = self.catalog.space_type(st)["zone"]
            tier = PREFERRED if zone in s.upgraded else REQUIRED
            type_factors[st] = d.type_factors[tier].get(st, 1.0)
        program = program_from_needs(self.catalog, needs, "s", s.cars, self.hcat.tier(PREFERRED)["area_profile"],
                                     zone_factors, self.hcat.data["program_defaults"]["gross_factor"], type_factors)
        self._cache[key] = program
        return program

    def sheet(self, s: State) -> QuantitySheet:
        key = ("sheet", s)
        if key not in self._cache:
            self._cache[key] = build_sheet(self.catalog, self.program(s), "state", floors=self.floors_for_cost,
                                           strategy=self.strategy, mean_slope=self.mean_slope)
        return self._cache[key]

    # ------------------------------------------------------------------------- gain and cost

    def coverage(self, s: State) -> float | None:
        if not self.next_pref:
            return None
        have = Counter()
        for k, c in zip(self.keys, s.counts):
            have[k] += c
        total = sum(self.next_pref.values())
        return sum(min(have[k], n) for k, n in self.next_pref.items()) / total

    def raw_gain(self, s: State) -> float:
        w = self.w
        g = 0.0
        sources = {sub["src"] for sub in self.substitutions}
        for i, k in enumerate(self.keys):
            if k in sources:
                continue
            base = self.req[i] if k not in self.sub_targets else 0
            c = s.counts[i]
            pref_part = max(0, min(c, self.pref[i]) - base)
            des_part = max(0, min(c, self.des[i]) - max(self.pref[i], base))
            mult = self.culture_multiplier if self.cultural[i] else 1.0
            g += mult * (w["preferred_instance"] * pref_part + w["desirable_instance"] * des_part)
        g += w["zone_size_upgrade"] * sum(self.zone_share.get(z, 0.0) for z in s.upgraded)
        g += w["garage_car"] * max(0, s.cars - self.cars_req)
        cov = self.coverage(s)
        if cov is not None:
            g += w["next_stage_coverage"] * cov
        return g

    def gain(self, s: State) -> float:
        return self.raw_gain(s) / self._gain_norm

    def index(self, s: State) -> float:
        key = ("index", s)
        if key not in self._cache:
            self._cache[key] = relative_index(self.model, self.sheet(s), self.reference,
                                              self.catalog.data["cost_index"], self.point)
        return self._cache[key]

    def gross(self, s: State) -> float:
        return self.sheet(s).gross_area

    def feasible(self, s: State) -> tuple[bool, str | None]:
        if self.far_sqft is not None and self.gross(s) > self.far_sqft + 1e-6:
            return False, NORMATIVE
        if self.budget_fraction is not None and self.index(s) > self.budget_fraction + 1e-9:
            return False, BUDGET
        return True, None

    # --------------------------------------------------------------------------------- curve

    def curve(self) -> tuple[list, str]:
        path, stop = greedy_ratio_path(self.start(), self.moves, self.apply, self.gain, self.index, self.feasible)
        return path, stop or COMPLETE


# ------------------------------------------------------------------------------------- profiles


def _spaces_counter(program: dict) -> Counter:
    return Counter((s["space_type"], s.get("household_role", "general")) for s in program["spaces"])


def describe(ctx: ProfileContext, s: State, label: str) -> dict:
    program = ctx.program(s)
    ok, why = ctx.feasible(s)
    return {
        "profile": label,
        "gross_area_sqft": round(ctx.gross(s), 1),
        "index": round(ctx.index(s), 4),
        "quality": round(ctx.gain(s), 4),
        "next_stage_coverage": None if ctx.coverage(s) is None else round(ctx.coverage(s), 4),
        "within_ceilings": ok,
        "blocked_by": why,
        "garage_cars": s.cars,
        "upgraded_zones": sorted(s.upgraded),
        "substitutions": sorted(s.done),
        "program": program,
    }


FOOTPRINT_OPTIMUM = "footprint"


def footprint_index(gross: list[float], cap: float) -> tuple[int, bool]:
    """Last point whose gross area fits the footprint cap (first point when none does), and whether it fits."""
    fit = [i for i, g in enumerate(gross) if g <= cap + 1e-6]
    return (fit[-1], True) if fit else (0, False)


def trimmed_index(ctx: ProfileContext, path: list, fits: Callable[[dict], bool]) -> int | None:
    """Last step of the curve whose program passes `fits` (None when no step does). Step 9a: the maximum is
    trimmed back along the curve when its program cannot be split inside the design footprint."""
    for i in range(len(path) - 1, -1, -1):
        if fits(ctx.program(path[i][0])):
            return i
    return None


def expansion_profiles(ctx: ProfileContext, optimum_policy: str | None = None,
                       optimum_cap_sqft: float | None = None, maximum_fits: Callable[[dict], bool] | None = None,
                       maximum_trim_label: str | None = None) -> dict:
    """Minimum, optimum and maximum from the expansion curve, with the curve itself.

    maximum_fits: optional predicate over a program (step 9a); when the last step fails it, the maximum is the
    last step that passes it and its governing limit is `maximum_trim_label`."""
    start = ctx.start()
    ok, why = ctx.feasible(start)
    path, stop = ctx.curve() if ok else ([(start, None, ctx.index(start), ctx.gain(start))], why)
    xs = [p[2] for p in path]
    ys = [p[3] for p in path]
    knee_step = knee_index(xs, ys, ctx.hcat.data["program_quality"]["knee_min_gain"])
    knee, opt_note = knee_step, None
    if optimum_policy == FOOTPRINT_OPTIMUM and optimum_cap_sqft is not None:
        knee, fits = footprint_index([ctx.gross(p[0]) for p in path], optimum_cap_sqft)
        if not fits:
            opt_note = (f"the minimum program ({ctx.gross(path[0][0]):.0f} sq ft) exceeds the design footprint "
                        f"({optimum_cap_sqft:.0f} sq ft): it needs two floors")
    top, trim = len(path) - 1, None
    if maximum_fits is not None and not maximum_fits(ctx.program(path[top][0])):
        found = trimmed_index(ctx, path, maximum_fits)
        trim = {"from_step": top, "to_step": found, "fits": found is not None,
                "from_gross_sqft": round(ctx.gross(path[top][0]), 1)}
        if found is not None:
            top = found
    points = [{"step": i, "move": None if m is None else f"{m[0]}:{m[1]}", "index": round(c, 4),
               "quality": round(g, 4), "gross_area_sqft": round(ctx.gross(s), 1)} for i, (s, m, c, g) in enumerate(path)]
    return {
        "minimum": {**describe(ctx, path[0][0], "minimum"), "note": None if ok else
                    f"the minimum program already exceeds the {why} ceiling"},
        "optimum": {**describe(ctx, path[knee][0], "optimum"), "curve_step": knee, "knee_step": knee_step,
                    "optimum_policy": optimum_policy or "knee",
                    "optimum_cap_sqft": None if optimum_cap_sqft is None else round(optimum_cap_sqft, 1),
                    "note": opt_note},
        "maximum": {**describe(ctx, path[top][0], "maximum"), "curve_step": top,
                    "governing": (maximum_trim_label if trim and trim["fits"] else stop) if ok else why,
                    "trim": trim},
        "curve": points,
        "_states": {"minimum": path[0][0], "optimum": path[knee][0], "maximum": path[top][0]},
    }


def program_delta(before: dict, after: dict) -> list[dict]:
    a, b = _spaces_counter(before), _spaces_counter(after)
    return [{"space_type": k[0], "household_role": k[1], "now": a.get(k, 0), "later": b.get(k, 0),
             "change": b.get(k, 0) - a.get(k, 0)} for k in sorted(set(a) | set(b)) if a.get(k, 0) != b.get(k, 0)]


def staged_profile(ctx: ProfileContext, later_ctx: ProfileContext | None, minimum: State, optimum: State) -> dict:
    """Build the minimum today; grow to the optimum of the next stage (or of today when there is none)."""
    ci = ctx.catalog.data["cost_index"]
    later_factor = ci["later_works_factor"]["mode"]
    if later_ctx is not None:
        target_ctx = later_ctx
        target = expansion_profiles(later_ctx)["_states"]["optimum"]
    else:
        target_ctx, target = ctx, optimum
    today_program, final_program = ctx.program(minimum), target_ctx.program(target)
    today_index, final_index = ctx.index(minimum), target_ctx.index(target)
    later_index = max(0.0, final_index - today_index) * later_factor
    convertible = set(ctx.hcat.data["trajectory"]["convertible_space_types"])
    final_ok, final_why = target_ctx.feasible(target)
    if target_ctx.far_sqft is not None:
        final_ok = target_ctx.gross(target) <= target_ctx.far_sqft + 1e-6
        final_why = None if final_ok else NORMATIVE
    return {
        "profile": "staged",
        "today": describe(ctx, minimum, "staged_today"),
        "final": {**describe(target_ctx, target, "staged_final"), "within_normative": final_ok,
                  "blocked_by": final_why},
        "expansion": program_delta(today_program, final_program),
        "expansion_gross_sqft": round(target_ctx.gross(target) - ctx.gross(minimum), 1),
        "convertible_now": sorted({s["space_id"] for s in today_program["spaces"] if s["space_type"] in convertible}),
        "index_today": round(today_index, 4),
        "index_later": round(later_index, 4),
        "index_total": round(today_index + later_index, 4),
        "index_build_final_now": round(final_index, 4),
        "later_works_factor": later_factor,
        "staging_premium": round(today_index + later_index - final_index, 4),
        "target_stage": "next" if later_ctx is not None else "current",
    }


def accessible_program(catalog: Catalog, program: dict) -> tuple[dict, dict]:
    """Copy of the program with a ground-floor bedroom and full bath, larger bath and bedroom (catalog)."""
    import copy

    acc = catalog.data["accessibility"]
    out = copy.deepcopy(program)
    spaces = out["spaces"]
    changes = []

    def scale(space, factor):
        rng = catalog.space_type(space["space_type"])["area"]
        new = min(rng["max"], math.ceil(space["target_area_sqft"] * factor))
        if new != space["target_area_sqft"]:
            changes.append({"space_id": space["space_id"], "change": "area", "from": space["target_area_sqft"], "to": new})
        space["target_area_sqft"] = float(new)

    def ground(space):
        if space["floor_preference"] != 0:
            changes.append({"space_id": space["space_id"], "change": "ground_floor"})
        space["floor_preference"] = 0

    bedrooms = [s for s in spaces if s["space_type"] in acc["bedroom_space_types"]]
    chosen = (next((s for s in bedrooms if s.get("household_role") == "accessible"), None)
              or next((s for s in bedrooms if s.get("household_role") == "primary"), None)
              or (bedrooms[0] if bedrooms else None))
    bath = None
    if chosen is not None:
        ground(chosen)
        scale(chosen, acc["bedroom_area_factor"])
        role = chosen.get("household_role")
        bath = (next((s for s in spaces if s["space_type"] == "primary_bath"), None) if chosen["space_type"] ==
                "primary_suite" else None) or next(
            (s for s in spaces if s["space_type"] == acc["bath_space_type"] and s.get("household_role") == role), None)
    if bath is None:
        bath = next((s for s in spaces if s["space_type"] == acc["bath_space_type"]), None)
    if bath is not None:
        ground(bath)
        scale(bath, acc["bath_area_factor"])
    features = {"ground_floor_bedroom": None if chosen is None else chosen["space_id"],
                "ground_floor_full_bath": None if bath is None else bath["space_id"],
                "step_free_entry": acc["step_free_entry"], "passage_width_ft": acc["passage_width_ft"],
                "door_clear_width_in": acc["door_clear_width_in"], "turning_diameter_ft": acc["turning_diameter_ft"],
                "changes": changes, "status": acc["source"]["status"]}
    return out, features


def floor_feasibility(gross: float, far: float | None, one_floor_max: float | None,
                      stair_sqft: float) -> str:
    """Area-level feasibility: exceeds_normative / fits_one_floor / needs_two_floors / no_lot."""
    if far is None or one_floor_max is None:
        return "no_lot"
    if gross > far + 1e-6:
        return "exceeds_normative"
    if gross <= one_floor_max + 1e-6:
        return "fits_one_floor"
    return "needs_two_floors" if (gross + stair_sqft) / 2 <= one_floor_max + 1e-6 else "exceeds_footprint"


def public(profile: dict) -> dict:
    return {k: v for k, v in profile.items() if not k.startswith("_")}


def describe_curve_moves(points: list[dict]) -> list[str]:
    return [p["move"] for p in points[1:]]


def profile_programs(stages: dict, catalog, model, reference, far_sqft: float | None = None,
                     budget_fraction: float | None = None, strategy: str | None = None,
                     mean_slope: float | None = None, optimum_policy: str | None = None,
                     optimum_cap_sqft: float | None = None, maximum_fits: Callable[[dict], bool] | None = None,
                     maximum_trim_label: str | None = None) -> tuple[dict, dict]:
    """Expansion curve and the five program profiles of a household on one reading (shared with step 6.6).

    Moved from spaceplan.modules.profiles.main.run_profiles in refactor tanda 3 without changes, so the area
    analysis uses it through the profiles library (no main -> main chain)."""
    ci = catalog.data["cost_index"]
    common = {"catalog": catalog, "hcat": stages["hcat"], "reference": reference, "model": model,
              "far_sqft": far_sqft, "budget_fraction": budget_fraction, "strategy": strategy,
              "mean_slope": mean_slope}
    later_ctx = ProfileContext(derivation=stages["later"]["derivation"], needs=stages["later"]["needs"], **common)
    ctx = ProfileContext(derivation=stages["now"]["derivation"], needs=stages["now"]["needs"],
                         next_needs=stages["later"]["needs"], **common)
    exp = expansion_profiles(ctx, optimum_policy, optimum_cap_sqft, maximum_fits, maximum_trim_label)
    states = exp["_states"]
    profiles = {k: exp[k] for k in ("minimum", "optimum", "maximum")}

    acc_program, features = accessible_program(catalog, profiles["optimum"]["program"])
    acc_sheet = build_sheet(catalog, acc_program, "accessible", strategy=strategy, mean_slope=mean_slope)
    acc_index = relative_index(model, acc_sheet, reference, ci, ctx.point)
    profiles["accessible"] = {**{k: v for k, v in profiles["optimum"].items() if k not in ("program", "curve_step")},
                              "profile": "accessible", "program": acc_program,
                              "gross_area_sqft": round(acc_sheet.gross_area, 1), "index": round(acc_index, 4),
                              "accessibility": features}
    profiles["staged"] = staged_profile(ctx, later_ctx, states["minimum"], states["optimum"])
    return exp, profiles


__all__ = [
    "Any",
    "ProfileContext",
    "State",
    "accessible_program",
    "expansion_profiles",
    "floor_feasibility",
    "footprint_index",
    "get_cost_model",
    "profile_programs",
    "program_delta",
    "public",
    "staged_profile",
    "trimmed_index",
]
