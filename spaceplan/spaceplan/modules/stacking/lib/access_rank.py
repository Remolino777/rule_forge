"""Choice among stair candidates of stage S1.2 (step 6.7a), in three levels (client decisions 2026-10-10).

  1. hard      the candidate was zoned by S2 (doors, circulation, light K06 where required, an allowed arrival, the
               stair hall) and every route target is reachable;
  2. quality   the route length from the vestibule (client step 7) and the occupied area: the Pareto front is
               reported, and the candidates whose route is within the catalog tolerance of the shortest one form the
               near-best set (a preferred strategy may cost a few feet of walking, never a long detour);
  3. client    inside the near-best set: strategy preference (K07), arrival preference (K01), half bath under the
               stair (K09), then route and area.
The tolerance is applied to every feasible candidate, not only to the Pareto front: the straight stair at the centre
dominates both criteria in most cells, so a front-only tolerance would never let a preferred strategy win.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Ranked:
    trial: Any
    route_ft: float
    occupied_sqft: float
    pareto: bool
    near_best: bool
    key: tuple
    reason: str


def _dominated(a: tuple[float, float], b: tuple[float, float]) -> bool:
    return b[0] <= a[0] and b[1] <= a[1] and b != a


def rank_stair_candidates(trials: list[dict[str, Any]], tolerance_ft: float, strategy_order: list[str],
                          arrival_order: list[str] | None = None) -> list[Ranked]:
    """Order the feasible trials, best first. A trial is a dict with route_ft, occupied_sqft, strategy and,
    optionally, arrival_kind and half_bath (True when the half bath sits under the stair)."""
    feasible = [t for t in trials if t.get("route_ft") is not None]
    if not feasible:
        return []
    pts = [(t["route_ft"], t["occupied_sqft"]) for t in feasible]
    best = min(p[0] for p in pts)
    out = []
    for t, p in zip(feasible, pts):
        pareto = not any(_dominated(p, q) for q in pts)
        near = p[0] <= best + tolerance_ft + 1e-9
        s_rank = strategy_order.index(t["strategy"]) if t["strategy"] in strategy_order else len(strategy_order)
        a_order = arrival_order or []
        kind = t.get("arrival_kind")
        a_rank = a_order.index(kind) if kind in a_order else len(a_order)
        key = (0 if near else 1, s_rank if near else 0, a_rank if near else 0,
               0 if t.get("half_bath") else 1, round(p[0], 2), round(p[1], 1))
        reason = (f"{'near-best' if near else 'outside tolerance'} (route {p[0]:.1f} ft, best {best:.1f} + "
                  f"{tolerance_ft:g}); strategy {t['strategy']}; arrival {kind}; "
                  f"half bath {'under stair' if t.get('half_bath') else 'no'}; area {p[1]:.0f} sq ft"
                  + ("; Pareto" if pareto else ""))
        out.append(Ranked(t, p[0], p[1], pareto, near, key, reason))
    return sorted(out, key=lambda r: r.key)


__all__ = ["Ranked", "rank_stair_candidates"]
