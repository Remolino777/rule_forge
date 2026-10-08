"""Access to a ruleset written in the project DSL (golden-rule subset used by capacity).

Normative numbers live in the ruleset JSON, never in the code: functions in rule_variants
read thresholds and values from here.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from spaceplan.core.lib_aux.hashing import sha256_of
from spaceplan.core.lib_aux.json_io import load_json, load_resource_json
from spaceplan.core.lib_aux.quantity import PROVISIONAL, VERIFIED

DEFAULT_RULESET = ("data", "rules", "sdmc_rs_1_7_capacity.json")
CRC_RULESET = ("data", "rules", "crc_2025_habitability.json")
BASE_VARIANT = "base"


class RuleSetError(KeyError):
    pass


@dataclass(frozen=True)
class RuleSet:
    data: dict[str, Any]
    sha256: str

    @property
    def ruleset_id(self) -> str:
        return self.data["ruleset_id"]

    @property
    def version(self) -> str:
        return self.data["ruleset_version"]

    @property
    def zone(self) -> str:
        return self.data["zone"]

    @property
    def jurisdiction_id(self) -> str:
        return self.data["jurisdiction_id"]

    @property
    def code_edition(self) -> str:
        return self.data["code_edition"]

    @property
    def measurement(self) -> dict[str, Any]:
        return self.data["lot_measurement"]

    @property
    def scope(self) -> dict[str, Any]:
        return self.data["scope"]

    def rule(self, rule_id: str) -> dict[str, Any]:
        for rule in self.data["rules"]:
            if rule["rule_id"] == rule_id:
                return rule
        raise RuleSetError(f"rule {rule_id!r} not found in {self.ruleset_id}")

    def variant(self, rule_id: str, variant_id: str) -> dict[str, Any]:
        for variant in self.rule(rule_id).get("variants", []):
            if variant["variant_id"] == variant_id:
                return variant
        raise RuleSetError(f"variant {variant_id!r} not found in rule {rule_id!r}")

    def params(self, rule_id: str, variant_id: str | None = None) -> dict[str, Any]:
        if variant_id in (None, BASE_VARIANT):
            return self.rule(rule_id).get("parameters", {})
        return self.variant(rule_id, variant_id).get("parameters", {})

    def _entry(self, rule_id: str, variant_id: str | None) -> dict[str, Any]:
        if variant_id in (None, BASE_VARIANT):
            return self.rule(rule_id)
        return self.variant(rule_id, variant_id)

    def status(self, rule_id: str, variant_id: str | None = None) -> str:
        entry = self._entry(rule_id, variant_id)
        verified = entry.get("verified", self.rule(rule_id).get("verified", False))
        return VERIFIED if verified else PROVISIONAL

    def source_tag(self, rule_id: str, variant_id: str | None = None) -> str:
        entry = self._entry(rule_id, variant_id)
        source = entry.get("source") or self.rule(rule_id)["source"]
        return f"{source['document']} {source['section']}"


def load_ruleset(path: str | Path | None = None) -> RuleSet:
    data = load_json(path) if path else load_resource_json("spaceplan", *DEFAULT_RULESET)
    return RuleSet(data=data, sha256=sha256_of(data))


def load_ruleset_resource(*parts: str) -> RuleSet:
    """Load a ruleset shipped with the package, e.g. load_ruleset_resource(*CRC_RULESET)."""
    data = load_resource_json("spaceplan", *parts)
    return RuleSet(data=data, sha256=sha256_of(data))
