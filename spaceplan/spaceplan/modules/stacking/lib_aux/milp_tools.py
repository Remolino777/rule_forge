"""A small mixed-integer linear model on scipy's HiGHS (step 6.7a S2.2g): named variables, rows and a solve.
Domain-free; the caller states what the variables mean."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp


@dataclass
class Model:
    """Minimize sum(cost * x) subject to rows lo <= sum(coef * x) <= hi; integer or continuous variables."""

    lo: list[float] = field(default_factory=list)
    hi: list[float] = field(default_factory=list)
    cost: list[float] = field(default_factory=list)
    integer: list[int] = field(default_factory=list)
    rows: list[tuple[dict[int, float], float, float]] = field(default_factory=list)

    def var(self, lo: float, hi: float, cost: float = 0.0, integer: bool = False) -> int:
        self.lo.append(float(lo))
        self.hi.append(float(hi))
        self.cost.append(float(cost))
        self.integer.append(1 if integer else 0)
        return len(self.lo) - 1

    def binary(self, cost: float = 0.0) -> int:
        return self.var(0.0, 1.0, cost, True)

    def row(self, coef: dict[int, float], lo: float = -np.inf, hi: float = np.inf) -> None:
        self.rows.append((dict(coef), float(lo), float(hi)))

    def abs_dev(self, coef: dict[int, float], const: float, weight: float) -> int:
        """A variable d >= |sum(coef * x) + const| costing `weight` per unit."""
        d = self.var(0.0, np.inf, weight)
        self.row({**coef, d: -1.0}, hi=-const)              # expr - d <= 0
        self.row({**{k: -v for k, v in coef.items()}, d: -1.0}, hi=const)   # -expr - d <= 0
        return d

    def solve(self, time_limit: float = 1.0) -> np.ndarray | None:
        n = len(self.lo)
        if n == 0:
            return np.zeros(0)
        cons = None
        if self.rows:
            a = np.zeros((len(self.rows), n))
            lo, hi = np.empty(len(self.rows)), np.empty(len(self.rows))
            for r, (coef, l_, h_) in enumerate(self.rows):
                for k, v in coef.items():
                    a[r, k] += v
                lo[r], hi[r] = l_, h_
            cons = LinearConstraint(a, lo, hi)
        res = milp(np.array(self.cost), constraints=cons, integrality=np.array(self.integer),
                   bounds=Bounds(np.array(self.lo), np.array(self.hi)),
                   options={"time_limit": time_limit, "presolve": False})   # tiny models: no presolve (quiet)
        return res.x if res.success and res.x is not None else None


__all__ = ["Model"]
