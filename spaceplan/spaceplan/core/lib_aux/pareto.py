"""Pareto front over numeric objectives (no domain knowledge)."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import TypeVar

T = TypeVar("T")


def dominates(a: Sequence[float], b: Sequence[float], senses: Sequence[str]) -> bool:
    """True if a is at least as good as b on every objective and strictly better on one.

    senses: "max" or "min" per objective."""
    better = False
    for x, y, s in zip(a, b, senses, strict=True):
        if s == "min":
            x, y = -x, -y
        elif s != "max":
            raise ValueError(f"unknown sense {s!r}")
        if x < y:
            return False
        if x > y:
            better = True
    return better


def pareto_front(items: Sequence[T], key: Callable[[T], Sequence[float]], senses: Sequence[str]) -> list[T]:
    """Non-dominated items, in input order (O(n^2), fine for a few thousand items)."""
    vectors = [tuple(key(i)) for i in items]
    return [item for i, item in enumerate(items)
            if not any(dominates(vectors[j], vectors[i], senses) for j in range(len(items)) if j != i)]


__all__ = ["dominates", "pareto_front"]
