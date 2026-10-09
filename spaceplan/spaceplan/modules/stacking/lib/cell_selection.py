"""Which area-matrix cells (step 6.6) go to the stacking layer.

Step 6.7 realizes the schemes that won in 6.6 instead of re-enumerating every floor count: inside each
(lot, household, profile) the ranked (feasible) cells with rank <= k are taken; k = None takes them all.
"""

from __future__ import annotations

from typing import Any


def select_cells(cells: list[dict[str, Any]], k: int | None) -> list[dict[str, Any]]:
    """Ranked cells with rank <= k, in the matrix order."""
    return [c for c in cells if c.get("rank") is not None and (k is None or c["rank"] <= k)]


def selection_label(cell: dict[str, Any]) -> str:
    return "best" if cell.get("rank") == 1 else f"rank_{cell.get('rank')}"


def selection_counts(cells: list[dict[str, Any]], selected: list[dict[str, Any]]) -> dict[str, int]:
    return {"matrix_cells": len(cells), "ranked_cells": sum(1 for c in cells if c.get("rank") is not None),
            "selected_cells": len(selected), "selected_two_floor": sum(1 for c in selected if c["floors"] > 1)}


__all__ = ["select_cells", "selection_counts", "selection_label"]
