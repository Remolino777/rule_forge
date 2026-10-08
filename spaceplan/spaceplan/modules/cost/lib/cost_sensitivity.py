"""Tornado sensitivity of the relative index (step 6.5b).

Each provisional parameter is moved to its catalog minimum and maximum, the others at their
most likely value. With one option the quantity is its index; with two it is the decision
quantity index(B) - index(A), and a row that crosses zero is a parameter able to reverse the
choice on its own. Rows are sorted by swing: the top rows are what to validate first.
"""

from __future__ import annotations

from spaceplan.core.lib_aux.weighted import one_at_a_time
from spaceplan.modules.cost.lib.cost_models import CostModel, relative_index
from spaceplan.modules.cost.lib.quantities import QuantitySheet


def tornado(model: CostModel, cost_index: dict, reference: QuantitySheet, sheet_a: QuantitySheet,
            sheet_b: QuantitySheet | None = None, top: int | None = None) -> dict | None:
    ranges = model.parameters(cost_index)
    if not ranges:
        return None

    def quantity(point):
        a = relative_index(model, sheet_a, reference, cost_index, point)
        return a if sheet_b is None else relative_index(model, sheet_b, reference, cost_index, point) - a

    rows = one_at_a_time(quantity, ranges)
    base = rows[0]["base"] if rows else quantity({k: v[1] for k, v in ranges.items()})
    for r in rows:
        r["crosses_zero"] = sheet_b is not None and min(r["at_low"], r["at_high"]) < 0 < max(r["at_low"], r["at_high"])
        for k in ("at_low", "at_high", "swing", "base"):
            r[k] = round(r[k], 5)
    rows = [r for r in rows if r["swing"] > 0]
    return {
        "model": model.name,
        "quantity": "index" if sheet_b is None else "index_b_minus_a",
        "a": sheet_a.label,
        "b": None if sheet_b is None else sheet_b.label,
        "base": round(base, 5),
        "rows": rows[:top] if top else rows,
        "decisive_parameters": [r["parameter"] for r in rows if r["crosses_zero"]],
        "note": "one parameter at a time; interactions are left to the Monte Carlo interval (step 6.8)",
    }
