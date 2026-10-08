"""Household model (step 6.5a): who lives in the house, how they live and how the household changes.

A household is a vector of dimensions (members with age and mobility, social life, guests, cooking,
vehicles, pets, trajectory). An archetype is only a preset of that vector; the client can edit any
value. Nothing here limits occupancy: bedroom grouping is design guidance (fair housing), and every
valid household yields a program.

The cultural profile is stored because the client chose it; this module never reads it (6.5c does).
"""

from __future__ import annotations

import copy
from collections import Counter
from dataclasses import asdict, dataclass, field, replace
from typing import Any

from jsonschema import Draft202012Validator

from spaceplan.core.lib.enums import CULTURE_ASPECTS, UNSPECIFIED
from spaceplan.core.lib.enums import HOUSEHOLD_DIMENSIONS as DIMENSIONS
from spaceplan.core.lib.schema_validation import load_schema
from spaceplan.modules.household.lib.household_catalog import HouseholdCatalog

ACCESS_RANK = {"full": 0, "none": 0, "anticipated": 1, "reduced": 2}
ACCESS_LEVEL = {0: "none", 1: "anticipated", 2: "reduced"}
PRIMARY, ACCESSIBLE = "primary", "accessible"


class HouseholdError(ValueError):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("invalid household:\n  - " + "\n  - ".join(errors))


@dataclass(frozen=True)
class Member:
    member_id: str
    age_years: int
    mobility: str
    works_from_home: bool
    partner_id: str | None


@dataclass(frozen=True)
class Household:
    members: tuple[Member, ...]
    social_life: str
    guests: str
    cooking: str
    vehicles: int
    pets: int
    shared_rooms_ok: bool
    cultural_profile: str | None
    horizon_years: int
    events: tuple[dict, ...]
    archetype_id: str | None = None
    program_tier: str | None = None
    include_household: bool = False
    stage_offset_years: int = 0
    culture_aspects: dict = field(default_factory=dict)   # resolved: preset of the profile + client overrides
    kitchen_typology: str | None = None                   # explicit client choice; otherwise selected by rules

    def member(self, member_id: str) -> Member:
        return next(m for m in self.members if m.member_id == member_id)


@dataclass(frozen=True)
class Room:
    """One bedroom of a grouping: who sleeps there (ids stay internal) and the role it plays."""

    occupants: tuple[str, ...]
    bands: tuple[str, ...]
    role: str
    accessibility: str

    def public(self) -> dict:
        return {"occupants": len(self.occupants), "bands": list(self.bands), "role": self.role,
                "accessibility": self.accessibility}


@dataclass(frozen=True)
class Grouping:
    required: tuple[Room, ...]
    preferred: tuple[Room, ...]

    def for_tier(self, tier: str) -> tuple[Room, ...]:
        return self.required if tier == "required" else self.preferred


# ----------------------------------------------------------------------------------------- loading


def _schema_errors(raw: dict) -> list[str]:
    validator = Draft202012Validator(load_schema("household"))
    return [f"{'/'.join(map(str, e.absolute_path)) or '<root>'}: {e.message}"
            for e in sorted(validator.iter_errors(raw), key=lambda e: list(e.absolute_path))]


def merge_with_archetype(raw: dict, hcat: HouseholdCatalog) -> dict:
    """Archetype preset overlaid with the client's explicit values (members and trajectory replace whole)."""
    archetype_id = raw.get("archetype_id")
    merged = copy.deepcopy(hcat.archetype(archetype_id)["household"]) if archetype_id else {}
    for key, value in raw.items():
        merged[key] = copy.deepcopy(value)
    return merged


def band_entry(age_years: int, hcat: HouseholdCatalog) -> dict:
    for band in hcat.data["age_bands"]:
        hi = band["max_years"]
        if band["min_years"] <= age_years and (hi is None or age_years <= hi):
            return band
    raise HouseholdError([f"age {age_years} is outside every age band"])


def band_of(age_years: int, hcat: HouseholdCatalog) -> str:
    return band_entry(age_years, hcat)["band"]


def is_grown(age_years: int, hcat: HouseholdCatalog) -> bool:
    return band_entry(age_years, hcat)["grown"]


def semantic_errors(h: Household, hcat: HouseholdCatalog) -> list[str]:
    errors = [f"duplicate member_id {k!r}" for k, n in Counter(m.member_id for m in h.members).items() if n > 1]
    ids = {m.member_id for m in h.members}
    for m in h.members:
        if m.partner_id is None:
            continue
        if m.partner_id == m.member_id:
            errors.append(f"{m.member_id}: partner_id points to itself")
        elif m.partner_id not in ids:
            errors.append(f"{m.member_id}: partner {m.partner_id!r} is not a member")
        elif h.member(m.partner_id).partner_id != m.member_id:
            errors.append(f"{m.member_id}: partnership with {m.partner_id!r} is not mutual")
        elif not is_grown(m.age_years, hcat):
            errors.append(f"{m.member_id}: partners are modelled between adults only")
    for i, e in enumerate(h.events):
        if e["event"] in ("member_leaves", "mobility_change") and e.get("member_id") not in ids:
            errors.append(f"trajectory event {i} ({e['event']}): member_id must name a current member")
        if e["event"] == "mobility_change" and "mobility" not in e:
            errors.append(f"trajectory event {i}: mobility_change needs 'mobility'")
    return errors


def load_household(raw: dict, hcat: HouseholdCatalog) -> Household:
    """Validate the raw block, overlay it on its archetype, fill catalog defaults, check semantics."""
    errors = _schema_errors(raw)
    if errors:
        raise HouseholdError(errors)
    if raw.get("archetype_id") and not hcat.has_archetype(raw["archetype_id"]):
        raise HouseholdError([f"unknown archetype {raw['archetype_id']!r}; known: {', '.join(hcat.archetype_ids())}"])
    merged = merge_with_archetype(raw, hcat)
    if not merged.get("members"):
        raise HouseholdError(["members are required (directly or through archetype_id)"])
    defaults = hcat.data["member_defaults"]
    members = tuple(
        Member(m["member_id"], m["age_years"], m.get("mobility", defaults["mobility"]),
               m.get("works_from_home", defaults["works_from_home"]), m.get("partner_id", defaults["partner_id"]))
        for m in merged["members"]
    )
    dims = {d["dimension"]: merged.get(d["dimension"], d["default"]) for d in hcat.data["dimensions"]}
    trajectory = merged.get("trajectory", {})
    household = Household(
        members=members,
        social_life=dims["social_life"], guests=dims["guests"], cooking=dims["cooking"],
        vehicles=dims["vehicles"], pets=dims["pets"], shared_rooms_ok=dims["shared_rooms_ok"],
        cultural_profile=dims["cultural_profile"],
        horizon_years=trajectory.get("horizon_years", hcat.data["trajectory"]["default_horizon_years"]),
        events=tuple(trajectory.get("events", [])),
        archetype_id=raw.get("archetype_id"),
        program_tier=merged.get("program_tier"),
        include_household=merged.get("include_household", False),
        culture_aspects={**hcat.preset(dims["cultural_profile"]), **merged.get("culture_aspects", {})},
        kitchen_typology=merged.get("kitchen_typology"),
    )
    errors = semantic_errors(household, hcat)
    if errors:
        raise HouseholdError(errors)
    return household


def to_raw(h: Household) -> dict:
    """Explicit household block (no archetype): used to test that presets equal manual entry."""
    raw = {"members": [{k: v for k, v in asdict(m).items() if v is not None} for m in h.members],
           **{d: getattr(h, d) for d in DIMENSIONS},
           "culture_aspects": dict(h.culture_aspects), "kitchen_typology": h.kitchen_typology,
           "trajectory": {"horizon_years": h.horizon_years, "events": [dict(e) for e in h.events]}}
    return raw


# -------------------------------------------------------------------------------------- trajectory


def advance(h: Household, years: int, hcat: HouseholdCatalog) -> tuple[Household, list[dict]]:
    """Household `years` later: everyone ages, events due by then are applied in order.

    Returns the new household (with the remaining events shifted) and the events applied.
    """
    joining = hcat.data["trajectory"]["joining_defaults"]
    members = {m.member_id: replace(m, age_years=m.age_years + years) for m in h.members}
    due = sorted((e for e in h.events if e["in_years"] <= years), key=lambda e: (e["in_years"], h.events.index(e)))
    applied, joined = [], Counter()
    for e in due:
        kind = e["event"]
        if kind in joining:
            joined[kind] += 1
            base = joining[kind]
            new_id = f"{kind}_{joined[kind]}"
            age = e.get("age_years", base["age_years"]) + (years - e["in_years"])
            members[new_id] = Member(new_id, age, e.get("mobility", base["mobility"]), False, None)
        elif kind == "member_leaves":
            gone = members.pop(e["member_id"], None)
            if gone and gone.partner_id in members:
                members[gone.partner_id] = replace(members[gone.partner_id], partner_id=None)
        elif kind == "mobility_change" and e["member_id"] in members:
            members[e["member_id"]] = replace(members[e["member_id"]], mobility=e["mobility"])
        applied.append(dict(e))
    remaining = tuple({**e, "in_years": e["in_years"] - years} for e in h.events if e["in_years"] > years)
    later = replace(h, members=tuple(members[k] for k in sorted(members)), events=remaining,
                    stage_offset_years=h.stage_offset_years + years)
    return later, applied


# ----------------------------------------------------------------------------------------- rooms


def _accessibility(members: list[Member]) -> str:
    return ACCESS_LEVEL[max(ACCESS_RANK[m.mobility] for m in members)]


def _group(h: Household, hcat: HouseholdCatalog, mode: str) -> list[tuple[list[Member], str]]:
    """Occupant groups (list of members, kind) in a canonical order independent of member order."""
    policy = hcat.data["bedroom_policy"]
    members = sorted(h.members, key=lambda m: m.member_id)
    groups: list[tuple[list[Member], str]] = []
    assigned: set[str] = set()
    if policy["partners_share"]:
        for m in members:
            if m.partner_id and m.member_id < m.partner_id and m.partner_id in {x.member_id for x in members}:
                groups.append(([m, h.member(m.partner_id)], "couple"))
                assigned |= {m.member_id, m.partner_id}
    share_groups = policy["required_share_groups"] if mode == "required" else (
        policy["preferred_share_groups"] if h.shared_rooms_ok else [])
    pools: dict[int, list[Member]] = {i: [] for i in range(len(share_groups))}
    for m in members:
        if m.member_id in assigned:
            continue
        band = band_of(m.age_years, hcat)
        pool = next((i for i, g in enumerate(share_groups) if band in g), None)
        if band in policy["own_room_bands"] or m.mobility != "full" or pool is None:
            groups.append(([m], "single"))
        else:
            pools[pool].append(m)
    size = policy["max_per_shared_room"]
    for i in sorted(pools):
        kids = sorted(pools[i], key=lambda m: (m.age_years, m.member_id))
        groups += [(kids[j:j + size], "shared") for j in range(0, len(kids), size)]
    return groups


def _primary_index(groups: list[tuple[list[Member], str]], hcat: HouseholdCatalog) -> int | None:
    couples = [i for i, (_, kind) in enumerate(groups) if kind == "couple"]
    if couples:
        return min(couples, key=lambda i: (ACCESS_RANK[_accessibility(groups[i][0])],
                                           tuple(m.member_id for m in groups[i][0])))
    grown = [i for i, (ms, _) in enumerate(groups) if is_grown(ms[0].age_years, hcat)]
    return grown[0] if len(grown) == 1 else None


def group_bedrooms(h: Household, hcat: HouseholdCatalog, mode: str) -> tuple[Room, ...]:
    groups = _group(h, hcat, mode)
    primary = _primary_index(groups, hcat)
    rooms = []
    for i, (ms, _) in enumerate(groups):
        access = _accessibility(ms)
        bands = tuple(band_of(m.age_years, hcat) for m in ms)
        if i == primary:
            role = PRIMARY
        elif access != "none":
            role = ACCESSIBLE
        else:
            role = band_entry(ms[0].age_years, hcat)["room_role"]
        rooms.append(Room(tuple(m.member_id for m in ms), bands, role, access))
    return tuple(rooms)


def bedrooms(h: Household, hcat: HouseholdCatalog) -> Grouping:
    return Grouping(group_bedrooms(h, hcat, "required"), group_bedrooms(h, hcat, "preferred"))


# ----------------------------------------------------------------------------------------- facts




def household_facts(h: Household, hcat: HouseholdCatalog, grouping: Grouping) -> dict[str, Any]:
    bands = Counter(band_of(m.age_years, hcat) for m in h.members)
    grown = sum(is_grown(m.age_years, hcat) for m in h.members)

    def secondary(rooms):
        return sum(r.role not in (PRIMARY, ACCESSIBLE) for r in rooms)

    primary = [r for r in grouping.preferred if r.role == PRIMARY]
    accessible = [r for r in grouping.preferred if r.role == ACCESSIBLE]
    values = {
        "members": len(h.members),
        "adults": grown,
        "seniors": bands["senior"],
        "children_0_5": bands["child_0_5"],
        "children_6_12": bands["child_6_12"],
        "teens": bands["teen_13_18"],
        "minors": bands["child_0_5"] + bands["child_6_12"] + bands["teen_13_18"],
        "couples": sum(1 for m in h.members if m.partner_id and m.member_id < m.partner_id),
        "unpartnered_adults": sum(1 for m in h.members if not m.partner_id and is_grown(m.age_years, hcat)),
        "wfh_count": sum(m.works_from_home for m in h.members),
        "bedrooms_required": len(grouping.required),
        "bedrooms_preferred": len(grouping.preferred),
        "primary_rooms": len(primary),
        "non_primary_bedrooms_required": len(grouping.required) - len(primary),
        "non_primary_bedrooms_preferred": len(grouping.preferred) - len(primary),
        "secondary_bedrooms_required": secondary(grouping.required),
        "secondary_bedrooms_preferred": secondary(grouping.preferred),
        "accessible_rooms_reduced": sum(r.accessibility == "reduced" for r in accessible),
        "accessible_rooms_any": len(accessible),
        "primary_accessible": primary[0].accessibility if primary else "none",
        **{d: getattr(h, d) for d in DIMENSIONS},
    }
    values["cultural_profile"] = values["cultural_profile"] or UNSPECIFIED
    values.update({a: h.culture_aspects.get(a, UNSPECIFIED) for a in CULTURE_ASPECTS})
    return values


def composition(h: Household, hcat: HouseholdCatalog) -> dict[str, int]:
    """Counts by age band only (what the package may show without include_household)."""
    counts = Counter(band_of(m.age_years, hcat) for m in h.members)
    return {b["band"]: counts.get(b["band"], 0) for b in hcat.data["age_bands"]}
