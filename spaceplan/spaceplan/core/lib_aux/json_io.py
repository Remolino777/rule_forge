"""JSON reading/writing, packaged resources and float rounding."""

from __future__ import annotations

import json
from importlib import resources
from pathlib import Path
from typing import Any


def load_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def dump_json(obj: Any, path: str | Path, indent: int = 2) -> None:
    Path(path).write_text(json.dumps(obj, indent=indent, ensure_ascii=False) + "\n", encoding="utf-8")


def load_resource_json(package: str, *parts: str) -> Any:
    node = resources.files(package)
    for part in parts:
        node = node.joinpath(part)
    return json.loads(node.read_text(encoding="utf-8"))


def to_json_compatible(obj: Any) -> Any:
    """Round-trip through JSON so tuples become lists (jsonschema needs real lists)."""
    return json.loads(json.dumps(obj))


def round_floats(obj: Any, decimals: int) -> Any:
    """Round every float in a nested structure; ints, bools and strings are untouched."""
    if isinstance(obj, float):
        rounded = round(obj, decimals)
        return 0.0 if rounded == 0 else rounded
    if isinstance(obj, dict):
        return {k: round_floats(v, decimals) for k, v in obj.items()}
    if isinstance(obj, list):
        return [round_floats(v, decimals) for v in obj]
    return obj
