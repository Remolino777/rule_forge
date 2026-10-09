"""Band enumeration of the zoning layer: ordered columns of stacked zones (shared by zones and spaces).

Extracted from zoning.py in refactor tanda 3 (without changes) to break the zoning <-> space_layout import
cycle: both the zone level (zoning.py) and the space level (space_layout.py) enumerate arrangements here.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass


def _compositions(n: int, max_part: int):
    if n == 0:
        yield ()
        return
    for part in range(1, min(max_part, n) + 1):
        for rest in _compositions(n - part, max_part):
            yield (part, *rest)


def _set_partitions(items: list[str], max_block: int):
    """Unordered partitions of items into blocks of at most max_block elements."""
    if not items:
        yield []
        return
    first, rest = items[0], items[1:]
    for partition in _set_partitions(rest, max_block):
        for i, block in enumerate(partition):
            if len(block) < max_block:
                yield partition[:i] + [[first, *block]] + partition[i + 1:]
        yield [[first], *partition]


@dataclass(frozen=True)
class BandGeometry:
    """What a column needs to know to be checked before any ordering: band width, depth and area."""

    width: float
    depth: float
    area: float


def _column_ok(column: tuple[str, ...], areas: dict[str, float], min_width: dict[str, float],
               band: BandGeometry, vehicle_cells: set[str], vehicle_depth: float) -> bool:
    col_area = sum(areas[c] for c in column)
    col_width = band.width * col_area / band.area
    for c in column:
        depth = band.depth * areas[c] / col_area
        if col_width < min_width[c] - 1e-9 or depth < min_width[c] - 1e-9:
            return False
        if c in vehicle_cells and depth < vehicle_depth - 1e-9:
            return False
    return True


def band_arrangements(zones: list[str], max_per_column: int, first_in_column: set[str], last_in_column: set[str],
                      column_ok=None, columns_ok=None):
    """Ordered columns of stacked zones. Columns are checked once (dimensions do not depend on column order);
    columns_ok(columns) rejects a whole set of columns before their orderings are generated."""
    for partition in _set_partitions(sorted(zones), max_per_column):
        orders_per_block = []
        for block in partition:
            orders = [
                o for o in itertools.permutations(block)
                if all(o.index(z) == 0 for z in o if z in first_in_column)
                and all(o.index(z) == len(o) - 1 for z in o if z in last_in_column)
                and (column_ok is None or column_ok(o))
            ]
            if not orders:
                break
            orders_per_block.append(orders)
        else:
            for chosen in itertools.product(*orders_per_block):
                if columns_ok is not None and not columns_ok(chosen):
                    continue
                for columns in itertools.permutations(chosen):
                    yield tuple(columns)


__all__ = ["BandGeometry", "band_arrangements"]
