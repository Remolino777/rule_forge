"""Small declarative expression language over a flat dict of facts (no domain knowledge).

Predicates (JSON):
    {"always": true}
    {"all": [p, ...]}   {"any": [p, ...]}   {"not": p}
    {"fact": "name", "op": "eq|ne|gt|ge|lt|le|in|not_in", "value": v}

Numeric expressions (JSON):
    3                                   literal
    {"fact": "name"}                    value of a fact
    {"fact": "name", "multiply": k, "divide_by": d, "add": a, "round": "ceil|floor|nearest",
     "min": lo, "max": hi}              applied in that order

Every function is pure; unknown facts raise KeyError so a typo in a data file never
silently evaluates to False.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

COMPARATORS = {
    "eq": lambda a, b: a == b,
    "ne": lambda a, b: a != b,
    "gt": lambda a, b: a > b,
    "ge": lambda a, b: a >= b,
    "lt": lambda a, b: a < b,
    "le": lambda a, b: a <= b,
    "in": lambda a, b: a in b,
    "not_in": lambda a, b: a not in b,
}
ROUNDING = {"ceil": math.ceil, "floor": math.floor, "nearest": round}
NUMERIC_KEYS = {"fact", "multiply", "divide_by", "add", "round", "min", "max"}


class ExpressionError(ValueError):
    pass


def _fact(facts: Mapping[str, Any], name: str) -> Any:
    if name not in facts:
        raise KeyError(f"unknown fact {name!r}")
    return facts[name]


def evaluate(predicate: Mapping[str, Any], facts: Mapping[str, Any]) -> bool:
    if "always" in predicate:
        return bool(predicate["always"])
    if "all" in predicate:
        return all(evaluate(p, facts) for p in predicate["all"])
    if "any" in predicate:
        return any(evaluate(p, facts) for p in predicate["any"])
    if "not" in predicate:
        return not evaluate(predicate["not"], facts)
    if "fact" in predicate:
        return COMPARATORS[predicate["op"]](_fact(facts, predicate["fact"]), predicate["value"])
    raise ExpressionError(f"unknown predicate form: {sorted(predicate)}")


def facts_used(predicate: Mapping[str, Any]) -> set[str]:
    if "all" in predicate or "any" in predicate:
        return set().union(*(facts_used(p) for p in predicate.get("all", predicate.get("any", []))))
    if "not" in predicate:
        return facts_used(predicate["not"])
    if "fact" in predicate:
        return {predicate["fact"]}
    return set()


def predicate_errors(predicate: Any, known_facts: set[str] | None = None, path: str = "") -> list[str]:
    """Structural check of a predicate (and fact names when known_facts is given)."""
    if not isinstance(predicate, Mapping) or len(predicate) == 0:
        return [f"{path or '<root>'}: predicate must be a non-empty object"]
    if "always" in predicate:
        return [] if len(predicate) == 1 else [f"{path}: 'always' takes no siblings"]
    for key in ("all", "any"):
        if key in predicate:
            items = predicate[key]
            if len(predicate) != 1 or not isinstance(items, list) or not items:
                return [f"{path}: '{key}' needs a non-empty list and no siblings"]
            return [e for i, p in enumerate(items) for e in predicate_errors(p, known_facts, f"{path}/{key}[{i}]")]
    if "not" in predicate:
        if len(predicate) != 1:
            return [f"{path}: 'not' takes no siblings"]
        return predicate_errors(predicate["not"], known_facts, f"{path}/not")
    if "fact" in predicate:
        errors = []
        if set(predicate) != {"fact", "op", "value"}:
            errors.append(f"{path}: comparison needs exactly fact, op, value")
        if predicate.get("op") not in COMPARATORS:
            errors.append(f"{path}: unknown operator {predicate.get('op')!r}")
        if known_facts is not None and predicate["fact"] not in known_facts:
            errors.append(f"{path}: unknown fact {predicate['fact']!r}")
        return errors
    return [f"{path or '<root>'}: unknown predicate form {sorted(predicate)}"]


def evaluate_number(expression: Any, facts: Mapping[str, Any]) -> float:
    if isinstance(expression, bool):
        raise ExpressionError("booleans are not numbers")
    if isinstance(expression, (int, float)):
        return expression
    if not isinstance(expression, Mapping) or "fact" not in expression:
        raise ExpressionError(f"bad numeric expression: {expression!r}")
    value = float(_fact(facts, expression["fact"]))
    value *= expression.get("multiply", 1)
    if "divide_by" in expression:
        value /= expression["divide_by"]
    value += expression.get("add", 0)
    if "round" in expression:
        value = ROUNDING[expression["round"]](value)
    if "min" in expression:
        value = max(value, expression["min"])
    if "max" in expression:
        value = min(value, expression["max"])
    return value


def number_errors(expression: Any, known_facts: set[str] | None = None, path: str = "") -> list[str]:
    if isinstance(expression, bool):
        return [f"{path}: booleans are not numbers"]
    if isinstance(expression, (int, float)):
        return []
    if not isinstance(expression, Mapping) or "fact" not in expression:
        return [f"{path}: numeric expression must be a number or an object with 'fact'"]
    errors = [f"{path}: unknown key {k!r}" for k in sorted(set(expression) - NUMERIC_KEYS)]
    if expression.get("round", "ceil") not in ROUNDING:
        errors.append(f"{path}: unknown rounding {expression['round']!r}")
    if expression.get("divide_by", 1) == 0:
        errors.append(f"{path}: divide_by is zero")
    if known_facts is not None and expression["fact"] not in known_facts:
        errors.append(f"{path}: unknown fact {expression['fact']!r}")
    return errors
