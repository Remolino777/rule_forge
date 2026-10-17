"""Shortest routes over a small graph of spaces (step V6.8 k2): door-to-door walks and candidate links.

Pure graph helpers with no design values: the caller gives the nodes it may cross, the edges and their lengths.
"""

from __future__ import annotations

import heapq
import math
from collections.abc import Callable, Hashable, Iterable


def dijkstra(sources: dict[Hashable, float], edges: Callable[[Hashable], Iterable[tuple[Hashable, float]]],
             is_target: Callable[[Hashable], bool]) -> tuple[float, list[Hashable]] | None:
    """Cheapest path from any source (with its start cost) to the first target reached: (cost, path) or None."""
    dist = dict(sources)
    prev: dict[Hashable, Hashable] = {}
    heap = [(c, i, n) for i, (n, c) in enumerate(sources.items())]
    heapq.heapify(heap)
    seen = set()
    tie = len(heap)
    while heap:
        d0, _, x = heapq.heappop(heap)
        if x in seen:
            continue
        seen.add(x)
        if is_target(x):
            path = [x]
            while path[-1] in prev:
                path.append(prev[path[-1]])
            return d0, path[::-1]
        for y, w in edges(x):
            nd = d0 + w
            if nd < dist.get(y, math.inf) - 1e-12:
                dist[y] = nd
                prev[y] = x
                tie += 1
                heapq.heappush(heap, (nd, tie, y))
    return None


def distance(p: tuple[float, float] | None, q: tuple[float, float] | None) -> float:
    """Straight distance between two points (0 when either is missing)."""
    if p is None or q is None:
        return 0.0
    return math.hypot(p[0] - q[0], p[1] - q[1])


__all__ = ["dijkstra", "distance"]
