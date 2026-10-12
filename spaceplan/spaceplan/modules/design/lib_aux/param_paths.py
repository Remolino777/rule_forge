"""Dotted paths into JSON stores, e.g. "space_types[space_type=bathroom].area.target" or
"rules[rule_id=S02-BEDROOM].parameters.aspect_max.value".

A segment "name[field=value]" selects the element of the list `name` whose `field` equals `value` (compared as
text); a plain segment is a dict key. get_path reads, set_path writes in place (callers pass a copy).
"""

from __future__ import annotations

import re
from typing import Any

SELECTOR = re.compile(r"(?P<key>[^\[\]]+)\[(?P<field>[^=\]]+)=(?P<value>[^\]]+)\]")  # used with fullmatch


class PathError(KeyError):
    pass


def split_path(path: str) -> list[str]:
    """Split on dots outside brackets (selector values may hold dots)."""
    parts, depth, cur = [], 0, []
    for ch in path:
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
        if ch == "." and depth == 0:
            parts.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    parts.append("".join(cur))
    return parts


def _step(node: Any, segment: str, path: str) -> Any:
    m = SELECTOR.fullmatch(segment)
    if m:
        items = node.get(m["key"]) if isinstance(node, dict) else None
        if not isinstance(items, list):
            raise PathError(f"{path}: '{m['key']}' is not a list")
        for item in items:
            if isinstance(item, dict) and str(item.get(m["field"])) == m["value"]:
                return item
        raise PathError(f"{path}: no element with {m['field']}={m['value']}")
    if not isinstance(node, dict) or segment not in node:
        raise PathError(f"{path}: missing key '{segment}'")
    return node[segment]


def get_path(obj: Any, path: str) -> Any:
    node = obj
    for segment in split_path(path):
        node = _step(node, segment, path)
    return node


def has_path(obj: Any, path: str) -> bool:
    try:
        get_path(obj, path)
        return True
    except PathError:
        return False


def set_path(obj: Any, path: str, value: Any) -> None:
    parts = split_path(path)
    node = obj
    for segment in parts[:-1]:
        node = _step(node, segment, path)
    last = parts[-1]
    if SELECTOR.fullmatch(last) or not isinstance(node, dict) or last not in node:
        raise PathError(f"{path}: cannot set '{last}'")
    node[last] = value


def expand(template: str, **values: str) -> str:
    out = template
    for key, value in values.items():
        out = out.replace("{" + key + "}", value)
    return out


__all__ = ["PathError", "expand", "get_path", "has_path", "set_path", "split_path"]
