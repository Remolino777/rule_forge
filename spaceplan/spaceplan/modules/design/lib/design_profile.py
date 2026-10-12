"""Design profiles (step 6.7a S2.2a): the client's changes on top of the registry baseline, versioned and traceable.

A profile is plain JSON:
    {"profile_id", "profile_version", "registry_id", "registry_version", "base_stores_sha256",
     "changes": [{"id", "value"?, "kind"?, "author", "date", "reason"}], "note"}
The baseline (catalogs and rulesets) is never edited. Every change is validated against the parameter (type, range,
choices, code floor, allowed kinds) and the cross-parameter constraints before it enters the profile.

    propose(reg, profile, id, value, kind)   validation and context of one change, profile unchanged
    apply(reg, profile, changes, author, date, reason)   new profile (raises ProfileError with the problems)
    effective_values / materialize / diff / snapshot
"""

from __future__ import annotations

import copy
from typing import Any

from spaceplan.core.lib_aux.hashing import sha256_of
from spaceplan.modules.design.lib.design_registry import DesignRegistry

PROFILE_VERSION = "0.1.0"
UNSET = object()


class ProfileError(ValueError):
    def __init__(self, problems: list[str]):
        super().__init__("; ".join(problems))
        self.problems = problems


def new_profile(reg: DesignRegistry, profile_id: str, note: str = "") -> dict[str, Any]:
    return {"profile_id": profile_id, "profile_version": PROFILE_VERSION, "registry_id": reg.registry_id,
            "registry_version": reg.version, "base_stores_sha256": reg.stores_sha256, "changes": [], "note": note}


def profile_sha256(profile: dict[str, Any]) -> str:
    return sha256_of(profile)


def change_map(profile: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    return {c["id"]: c for c in (profile or {}).get("changes", [])}


def effective_values(reg: DesignRegistry, profile: dict[str, Any] | None) -> dict[str, Any]:
    return reg.values(change_map(profile))


def materialize(reg: DesignRegistry, profile: dict[str, Any] | None) -> dict[str, Any]:
    """Copies of the stores with the profile written in (input for a pipeline run with this profile)."""
    return reg.materialize(change_map(profile))


def check_profile(reg: DesignRegistry, profile: dict[str, Any]) -> tuple[list[str], list[str]]:
    """(problems, warnings) of a whole profile against the registry."""
    problems, warnings = [], []
    if profile.get("registry_id") != reg.registry_id:
        problems.append(f"profile is for registry {profile.get('registry_id')!r}, not {reg.registry_id!r}")
    if profile.get("base_stores_sha256") != reg.stores_sha256:
        warnings.append("the baseline changed since the profile was made (catalog or ruleset versions); "
                        "re-check the changes")
    seen = set()
    for c in profile.get("changes", []):
        if c["id"] in seen:
            problems.append(f"{c['id']}: changed twice")
        seen.add(c["id"])
        if c["id"] not in reg.params:
            problems.append(f"{c['id']}: unknown parameter")
            continue
        problems += reg.check_value(c["id"], c.get("value", reg.params[c["id"]].value), c.get("kind"))
    problems += reg.check_constraints(effective_values(reg, profile))
    return problems, warnings


def propose(reg: DesignRegistry, profile: dict[str, Any] | None, param_id: str, value: Any = UNSET,
            kind: str | None = None, lang: str = "es") -> dict[str, Any]:
    """Validation of one change in the context of the profile; nothing is written."""
    p = reg.get(param_id)
    current = effective_values(reg, profile)
    new_value = current[param_id] if value is UNSET else value
    problems = reg.check_value(param_id, new_value, kind)
    trial = dict(current)
    trial[param_id] = new_value
    problems += [x for x in reg.check_constraints(trial) if param_id in x]
    warnings = []
    if p.who == "designer":
        warnings.append(f"{param_id}: designer parameter; changing it alters how the generator scores or searches")
    if not p.verified:
        warnings.append(f"{param_id}: baseline value not verified yet ({p.source.get('document', '')})")
    if p.kind == "reference":
        warnings.append(f"{param_id}: reference value (informative); no check uses it directly")
    kinds = reg.kinds(change_map(profile))
    return {"ok": not problems, "id": param_id, "baseline": p.value, "current": current[param_id],
            "proposed": new_value, "kind": kind or kinds[param_id], "unit": p.unit, "problems": problems,
            "warnings": warnings, "explain": reg.explain(param_id, lang)}


def apply(reg: DesignRegistry, profile: dict[str, Any], changes: list[dict[str, Any]], author: str, date: str,
          reason: str = "") -> dict[str, Any]:
    """New profile with the changes (each {"id", "value"?, "kind"?, "reason"?}); a change back to the baseline
    removes the entry. Raises ProfileError listing every problem."""
    out = copy.deepcopy(profile)
    cmap = change_map(out)
    problems: list[str] = []
    for ch in changes:
        pid = ch["id"]
        if pid not in reg.params:
            problems.append(f"{pid}: unknown parameter")
            continue
        p = reg.params[pid]
        entry = {**cmap.get(pid, {"id": pid}), "author": author, "date": date,
                 "reason": ch.get("reason") or reason}
        if "value" in ch:
            entry["value"] = ch["value"]
        if ch.get("kind"):
            entry["kind"] = ch["kind"]
        problems += reg.check_value(pid, entry.get("value", p.value), entry.get("kind"))
        same_value = entry.get("value", p.value) == p.value
        same_kind = entry.get("kind", p.kind) == p.kind
        if same_value and same_kind:
            cmap.pop(pid, None)
        else:
            cmap[pid] = entry
    out["changes"] = sorted(cmap.values(), key=lambda c: c["id"])
    problems += reg.check_constraints(effective_values(reg, out))
    if problems:
        raise ProfileError(problems)
    return out


def diff(reg: DesignRegistry, a: dict[str, Any] | None, b: dict[str, Any] | None) -> list[dict[str, Any]]:
    va, vb = effective_values(reg, a), effective_values(reg, b)
    ka, kb = reg.kinds(change_map(a)), reg.kinds(change_map(b))
    return [{"id": pid, "a": va[pid], "b": vb[pid], "kind_a": ka[pid], "kind_b": kb[pid], "unit": reg.params[pid].unit}
            for pid in sorted(reg.params) if va[pid] != vb[pid] or ka[pid] != kb[pid]]


def snapshot(reg: DesignRegistry, profile: dict[str, Any] | None, lang: str = "es") -> list[dict[str, Any]]:
    """Every parameter with its effective value and kind, flagged when the profile changed it."""
    cmap = change_map(profile)
    values, kinds = reg.values(cmap), reg.kinds(cmap)
    return [{**reg.explain(pid, lang), "value": values[pid], "kind": kinds[pid], "baseline": reg.params[pid].value,
             "changed": pid in cmap} for pid in sorted(reg.params)]


__all__ = ["PROFILE_VERSION", "UNSET", "ProfileError", "apply", "change_map", "check_profile", "diff",
           "effective_values", "materialize", "new_profile", "profile_sha256", "propose", "snapshot"]
