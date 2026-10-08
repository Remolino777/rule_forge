"""Weighted sums, factor products and one-at-a-time sensitivity (no domain knowledge)."""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping


def weighted_sum(amounts: Mapping[str, float], weights: Mapping[str, float]) -> tuple[float, dict[str, float]]:
    """Sum of amount x weight and the contribution of each key. Every key needs a weight."""
    missing = sorted(set(amounts) - set(weights))
    if missing:
        raise KeyError(f"no weight for {missing}")
    parts = {k: amounts[k] * weights[k] for k in sorted(amounts)}
    return math.fsum(parts.values()), parts


def product(factors: Mapping[str, float]) -> float:
    return math.prod(factors[k] for k in sorted(factors))


def one_at_a_time(
    evaluate: Callable[[Mapping[str, float]], float],
    ranges: Mapping[str, tuple[float, float, float]],
) -> list[dict]:
    """Tornado rows: each parameter moved to its low and high ends, the others at their mode.

    ranges: name -> (low, mode, high). Rows sorted by swing (largest first, ties by name);
    parameters with low == high are skipped.
    """
    base_point = {k: v[1] for k, v in ranges.items()}
    base = evaluate(base_point)
    rows = []
    for name in sorted(ranges):
        low, _, high = ranges[name]
        if low == high:
            continue
        at_low = evaluate({**base_point, name: low})
        at_high = evaluate({**base_point, name: high})
        rows.append({"parameter": name, "low_input": low, "high_input": high, "at_low": at_low, "at_high": at_high,
                     "swing": abs(at_high - at_low), "base": base})
    rows.sort(key=lambda r: (-r["swing"], r["parameter"]))
    return rows
