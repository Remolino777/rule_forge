"""Relative budget (step 6.5b): a level or a fraction of the lot's normative maximum, never money.

The buildable maximum is the smaller of the normative ceiling (index 1) and the budget fraction;
the block says which one governs. When even the minimum program exceeds the budget, staged
construction is suggested (step 6.5d builds that option).
"""

from __future__ import annotations

NORMATIVE, BUDGET = "normative", "budget"


def resolve_budget(cost_index: dict, budget: dict | None) -> dict | None:
    if not budget:
        return None
    if "fraction_of_max" in budget:
        return {"level": None, "fraction_of_max": float(budget["fraction_of_max"]), "origin": "client_fraction"}
    levels = cost_index["budget_levels"]
    if budget["level"] not in levels:
        raise ValueError(f"unknown budget level {budget['level']!r}; known: {', '.join(levels)}")
    return {"level": budget["level"], "fraction_of_max": levels[budget["level"]], "origin": "catalog_level",
            "status": cost_index["source"]["status"]}


def assess_budget(resolved: dict | None, indices: dict[str, float], reading: str,
                  minimum_label: str | None = None) -> dict:
    """Governing ceiling and per-option verdicts. `indices`: label -> index under the selected model."""
    if reading != "lot":
        return {"applies": False, "reason": "budget is a fraction of the lot maximum; no lot in this reading",
                "budget": resolved}
    ceiling = 1.0 if resolved is None else min(1.0, resolved["fraction_of_max"])
    governing = NORMATIVE if resolved is None or resolved["fraction_of_max"] >= 1.0 else BUDGET
    verdicts = {label: {"index": round(i, 4), "within_normative": i <= 1.0 + 1e-9,
                        "within_budget": None if resolved is None else i <= resolved["fraction_of_max"] + 1e-9,
                        "headroom": round(ceiling - i, 4)}
                for label, i in indices.items()}
    suggestions = []
    if resolved is not None and minimum_label in indices and indices[minimum_label] > resolved["fraction_of_max"]:
        suggestions.append("staged_construction: even the minimum program exceeds the budget; build the minimum in "
                           "stages or lower the program (step 6.5d)")
    if any(not v["within_normative"] for v in verdicts.values()):
        suggestions.append("some options exceed the normative maximum of the lot (index > 1)")
    return {"applies": True, "budget": resolved, "buildable_max_index": ceiling, "governing": governing,
            "verdicts": verdicts, "suggestions": suggestions}
