"""Unit conversion between the units the design parameters use (lengths and areas; ratios pass through)."""

from __future__ import annotations

LENGTH_FT = {"ft": 1.0, "in": 1.0 / 12.0, "m": 3.280839895}
AREA_SQFT = {"sq_ft": 1.0, "sqft": 1.0, "sq_m": 10.763910417}


class UnitError(ValueError):
    pass


def convert(value: float, unit_from: str | None, unit_to: str | None) -> float:
    if unit_from == unit_to or unit_from is None or unit_to is None:
        return float(value)
    for table in (LENGTH_FT, AREA_SQFT):
        if unit_from in table and unit_to in table:
            return float(value) * table[unit_from] / table[unit_to]
    raise UnitError(f"cannot convert {unit_from} to {unit_to}")


__all__ = ["UnitError", "convert"]
