"""Canonical JSON hashing for briefs, rulesets and packages."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_of(obj: Any) -> str:
    """SHA-256 of the canonical JSON form (key order and whitespace independent)."""
    return sha256_text(canonical_json(obj))
