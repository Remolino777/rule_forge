"""One-dimensional allocation with minimums (no domain knowledge)."""

from __future__ import annotations


def fit_lengths(lengths: list[float], mins: list[float]) -> list[float] | None:
    """Raise every length to its minimum, taking the deficit from the others' slack (proportionally).

    The total is preserved; returns None when the minimums cannot all fit.
    """
    total = sum(lengths)
    if sum(mins) > total + 1e-9:
        return None
    out = list(lengths)
    for _ in range(len(out) + 1):
        deficit = sum(max(0.0, m - l) for l, m in zip(out, mins))
        if deficit <= 1e-9:
            return out
        out = [max(l, m) for l, m in zip(out, mins)]
        slack = [max(0.0, l - m) for l, m in zip(out, mins)]
        total_slack = sum(slack)
        if total_slack <= 1e-12:
            return None
        out = [l - deficit * sl / total_slack for l, sl in zip(out, slack)]
    return out




def ranked_product(sizes: list[int], limit: int):
    """Index tuples of the Cartesian product of lists of the given sizes, in increasing order of the sum of
    indices (best-first when every list is sorted best first), up to limit tuples.

    Unlike itertools.product, every list's later options appear early instead of only the last list's.
    """
    import heapq

    if not sizes or any(n == 0 for n in sizes):
        return
    start = tuple(0 for _ in sizes)
    heap = [(0, start)]
    seen = {start}
    count = 0
    while heap and count < limit:
        total, idx = heapq.heappop(heap)
        yield idx
        count += 1
        for i, n in enumerate(sizes):
            if idx[i] + 1 < n:
                nxt = idx[:i] + (idx[i] + 1,) + idx[i + 1:]
                if nxt not in seen:
                    seen.add(nxt)
                    heapq.heappush(heap, (total + 1, nxt))


__all__ = ["fit_lengths", "ranked_product"]
