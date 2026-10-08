"""Scope gate: phase-1 exclusions (zone, jurisdiction, overlays)."""

from __future__ import annotations

from dataclasses import dataclass

from spaceplan.core.lib.rules import RuleSet


@dataclass(frozen=True)
class ScopeResult:
    in_scope: bool
    reasons: tuple[str, ...]

    def to_dict(self) -> dict:
        return {"in_scope": self.in_scope, "reasons": list(self.reasons)}


def check_scope(brief: dict, rs: RuleSet) -> ScopeResult:
    meta, overlays = brief["meta"], brief["overlays"]
    reasons = []
    if meta["jurisdiction_id"] != rs.jurisdiction_id:
        reasons.append(f"jurisdiction {meta['jurisdiction_id']!r} not covered by {rs.ruleset_id}")
    if meta["zone"] != rs.zone:
        reasons.append(f"zone {meta['zone']!r} not covered by {rs.ruleset_id} ({rs.zone})")
    source = rs.scope["source"]
    for key in rs.scope["excluded_overlays"]:
        if overlays.get(key):
            reasons.append(f"overlay {key!r} is excluded in phase 1 ({source['document']}, {source['section']})")
    return ScopeResult(not reasons, tuple(reasons))
