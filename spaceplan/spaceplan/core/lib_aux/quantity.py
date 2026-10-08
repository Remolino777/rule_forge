"""Traceable quantities: a value with unit, verification status and sources."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, replace

VERIFIED = "verified"
PROVISIONAL = "provisional"
UNDETERMINABLE = "undeterminable"
STATUSES = (VERIFIED, PROVISIONAL, UNDETERMINABLE)
_RANK = {status: rank for rank, status in enumerate(STATUSES)}


def worst_status(*statuses: str) -> str:
    """Return the least reliable status (verified < provisional < undeterminable)."""
    if not statuses:
        return VERIFIED
    return max(statuses, key=_RANK.__getitem__)


def merge_sources(sources: Iterable[str]) -> tuple[str, ...]:
    """Deduplicate sources keeping first-seen order."""
    return tuple(dict.fromkeys(s for s in sources if s))


@dataclass(frozen=True)
class Quantity:
    value: float | None
    unit: str
    status: str = VERIFIED
    sources: tuple[str, ...] = ()
    note: str | None = None

    def __post_init__(self) -> None:
        if self.status not in _RANK:
            raise ValueError(f"unknown status {self.status!r}")

    @classmethod
    def derived(
        cls,
        value: float | None,
        unit: str,
        inputs: Iterable[Quantity | None] = (),
        sources: Iterable[str] = (),
        status: str = VERIFIED,
        note: str | None = None,
    ) -> Quantity:
        """Build a quantity whose status is the worst of its inputs and whose sources are merged."""
        used = [q for q in inputs if q is not None]
        merged = merge_sources([s for q in used for s in q.sources] + list(sources))
        final = worst_status(status, *(q.status for q in used))
        return cls(None if value is None else float(value), unit, final, merged, note)

    def with_status(self, status: str, note: str | None = None) -> Quantity:
        """Degrade (never upgrade) the status and optionally attach a note."""
        return replace(self, status=worst_status(self.status, status), note=note or self.note)

    def to_dict(self) -> dict:
        return {
            "value": self.value,
            "unit": self.unit,
            "status": self.status,
            "sources": list(self.sources),
            "note": self.note,
        }
