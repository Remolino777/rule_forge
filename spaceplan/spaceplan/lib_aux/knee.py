"""Knee (elbow) of a monotone increasing curve and greedy ratio search (no domain knowledge).

knee_index: Kneedle-style rule. Both axes are normalized to [0, 1]; the knee is the point with the
largest vertical distance above the chord joining the first and last points (diminishing returns).
"""

from __future__ import annotations

from collections.abc import Callable, Hashable, Iterable, Sequence
from typing import TypeVar

S = TypeVar("S")
M = TypeVar("M", bound=Hashable)


def knee_index(xs: Sequence[float], ys: Sequence[float], min_gain: float = 0.0) -> int:
    """Index of the knee of y(x); the last index when the curve has fewer than 3 points or is straight.

    min_gain: smallest normalized distance above the chord that counts as a knee.
    """
    n = len(xs)
    if n != len(ys):
        raise ValueError("xs and ys differ in length")
    if n < 3:
        return n - 1
    x0, x1, y0, y1 = xs[0], xs[-1], ys[0], ys[-1]
    if x1 - x0 <= 0 or y1 - y0 <= 0:
        return n - 1
    best, best_d = n - 1, min_gain
    for i in range(1, n - 1):
        xn, yn = (xs[i] - x0) / (x1 - x0), (ys[i] - y0) / (y1 - y0)
        d = yn - xn
        if d > best_d + 1e-12:
            best, best_d = i, d
    return best


def greedy_ratio_path(
    start: S,
    moves: Callable[[S], Iterable[M]],
    apply: Callable[[S, M], S],
    gain: Callable[[S], float],
    cost: Callable[[S], float],
    feasible: Callable[[S], tuple[bool, str | None]],
    max_steps: int = 500,
) -> tuple[list[tuple[S, M | None, float, float]], str | None]:
    """Repeatedly apply the feasible move with the best gain/cost ratio.

    Returns the path [(state, move, cost, gain)] starting at `start` and the reason the path stopped:
    None when no move was left, else the blocking reason of the best rejected move. Ties are broken by
    the move order of `moves` (deterministic). Moves that do not raise the gain are ignored.
    """
    state = start
    path = [(start, None, cost(start), gain(start))]
    stop = None
    for _ in range(max_steps):
        g0, c0 = path[-1][3], path[-1][2]
        best = None
        blocked = None
        for move in moves(state):
            nxt = apply(state, move)
            dg = gain(nxt) - g0
            if dg <= 1e-12:
                continue
            ok, why = feasible(nxt)
            dc = cost(nxt) - c0
            ratio = dg / dc if dc > 1e-12 else float("inf")
            if not ok:
                if blocked is None or ratio > blocked[0]:
                    blocked = (ratio, why)
                continue
            if best is None or ratio > best[0] + 1e-12:
                best = (ratio, move, nxt, dc)
        if best is None:
            stop = None if blocked is None else blocked[1]
            break
        _, move, state, _ = best
        path.append((state, move, cost(state), gain(state)))
    return path, stop
