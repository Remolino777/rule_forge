"""Registry of the design parameters (step 6.7a S2.2a): one place to list, explain and validate every value the
client or the designer may define.

Two origins, one interface:
  * references (data/design/registry_refs.json): values that already live in the residential catalog, the stacking
    catalog or the client rulesets, read through a dotted path into their store (never copied);
  * design parameters: parameter objects inside the design rulesets (data/rules/design_*.json), discovered by the
    `param_prefix` of each rule.

Each parameter carries its baseline value, type, unit, kind (hard / soft / weight / reference), who defines it
(client / designer / code), a range or the allowed choices, an optional code floor (a rule of a CRC ruleset the value
may not cross) and its source. The baseline is never edited: client changes live in a design profile
(lib/design_profile.py) and `materialize` writes them into copies of the stores.
"""

from __future__ import annotations

import copy
import difflib
from dataclasses import dataclass, field
from itertools import pairwise
from typing import Any

from spaceplan.core.lib.catalog import load_catalog_data
from spaceplan.core.lib_aux.hashing import sha256_of
from spaceplan.core.lib_aux.json_io import load_resource_json
from spaceplan.modules.design.lib_aux.param_paths import expand, get_path, set_path
from spaceplan.modules.design.lib_aux.units import convert

REFS_RESOURCE = ("data", "design", "registry_refs.json")
CATALOG, STACKING = "catalog", "stacking_catalog"
RULESET_PREFIX = "ruleset:"
KINDS = ("hard", "soft", "weight", "reference")
WHO = ("client", "designer", "code")
TYPES = ("number", "enum", "list", "bool")
DESIGN_SPACES = "design_spaces"
TOL = 1e-9


class DesignRegistryError(KeyError):
    pass


@dataclass(frozen=True)
class Floor:
    """Code limit of a parameter, already converted to the parameter unit."""
    ruleset: str
    rule_id: str
    key: str
    bound: str              # "min": value >= floor; "max": value <= floor
    value: float
    unit: str | None
    source: str

    def to_dict(self) -> dict[str, Any]:
        return {"ruleset": self.ruleset, "rule_id": self.rule_id, "key": self.key, "bound": self.bound,
                "value": self.value, "unit": self.unit, "source": self.source}


@dataclass(frozen=True)
class Param:
    id: str
    value: Any
    type: str
    unit: str | None
    kind: str
    kinds_allowed: tuple[str, ...]
    who: str
    range: tuple[float, float] | None
    choices: tuple[Any, ...] | None
    floor: Floor | None
    description: dict[str, str]
    store: str
    path: str
    kind_path: str | None
    source: dict[str, str]
    verified: bool
    origin: str             # "reference" | "design"
    note: str | None = None

    def to_dict(self, lang: str | None = None) -> dict[str, Any]:
        desc = self.description.get(lang) if lang else self.description
        return {"id": self.id, "value": self.value, "type": self.type, "unit": self.unit, "kind": self.kind,
                "kinds_allowed": list(self.kinds_allowed), "who": self.who,
                "range": list(self.range) if self.range else None,
                "choices": list(self.choices) if self.choices is not None else None,
                "floor": self.floor.to_dict() if self.floor else None, "description": desc, "store": self.store,
                "path": self.path, "source": self.source, "verified": self.verified, "origin": self.origin,
                "note": self.note}


@dataclass
class DesignRegistry:
    stores: dict[str, Any]
    refs: dict[str, Any]
    params: dict[str, Param] = field(default_factory=dict)
    constraints: list[tuple[tuple[str, ...], dict[str, str]]] = field(default_factory=list)

    # ------------------------------------------------------------------ identity
    @property
    def registry_id(self) -> str:
        return self.refs["registry_id"]

    @property
    def version(self) -> str:
        return self.refs["registry_version"]

    @property
    def stores_sha256(self) -> str:
        return sha256_of({k: sha256_of(v) for k, v in sorted(self.stores.items())})

    # ------------------------------------------------------------------ lookup
    def get(self, param_id: str) -> Param:
        if param_id not in self.params:
            close = difflib.get_close_matches(param_id, list(self.params), n=3)
            raise DesignRegistryError(f"unknown parameter {param_id!r}" + (f"; did you mean {close}?" if close else ""))
        return self.params[param_id]

    def list(self, prefix: str | None = None, who: str | None = None, kind: str | None = None,
             text: str | None = None) -> list[Param]:
        out = []
        for p in self.params.values():
            if prefix and not p.id.startswith(prefix):
                continue
            if who and p.who != who:
                continue
            if kind and p.kind != kind:
                continue
            if text:
                blob = " ".join([p.id, *p.description.values()]).lower()
                if text.lower() not in blob:
                    continue
            out.append(p)
        return sorted(out, key=lambda p: p.id)

    def explain(self, param_id: str, lang: str = "es") -> dict[str, Any]:
        return self.get(param_id).to_dict(lang)

    def baseline(self) -> dict[str, Any]:
        return {pid: p.value for pid, p in self.params.items()}

    # ------------------------------------------------------------------ validation
    def check_value(self, param_id: str, value: Any, kind: str | None = None) -> list[str]:
        """Problems of setting `value` (and optionally `kind`) on one parameter; empty when valid."""
        p = self.get(param_id)
        problems: list[str] = []
        if p.who == "code":
            return [f"{param_id}: set by code ({p.source.get('document', '')}); it cannot be changed"]
        if kind is not None and kind not in p.kinds_allowed:
            problems.append(f"{param_id}: kind {kind!r} not allowed (allowed: {list(p.kinds_allowed)})")
        if p.type == "number":
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                return [*problems, f"{param_id}: expects a number"]
            if p.range and not (p.range[0] - TOL <= value <= p.range[1] + TOL):
                problems.append(f"{param_id}: {value} outside the allowed range {list(p.range)} {p.unit or ''}".strip())
            if p.floor:
                f = p.floor
                if (f.bound == "min" and value < f.value - TOL) or (f.bound == "max" and value > f.value + TOL):
                    word = "below" if f.bound == "min" else "above"
                    problems.append(f"{param_id}: {value} is {word} the code limit {f.value:g} {p.unit or ''} "
                                    f"({f.rule_id}, {f.source})")
        elif p.type == "enum":
            if value not in (p.choices or ()):
                problems.append(f"{param_id}: {value!r} not in {list(p.choices or ())}")
        elif p.type == "list":
            if not isinstance(value, list) or not value:
                return [*problems, f"{param_id}: expects a non-empty list"]
            extra = [v for v in value if v not in (p.choices or ())]
            if extra:
                problems.append(f"{param_id}: {extra} not in {list(p.choices or ())}")
            if len(set(map(str, value))) != len(value):
                problems.append(f"{param_id}: repeated items")
        elif p.type == "bool":
            if not isinstance(value, bool):
                problems.append(f"{param_id}: expects true or false")
        return problems

    def check_constraints(self, values: dict[str, Any]) -> list[str]:
        problems = []
        for ids, desc in self.constraints:
            chain = [(i, values[i]) for i in ids if i in values]
            for (a, va), (b, vb) in pairwise(chain):
                if isinstance(va, (int, float)) and isinstance(vb, (int, float)) and va > vb + TOL:
                    problems.append(f"{a} ({va}) must be <= {b} ({vb}): {desc.get('en', '')}")
        return problems

    def self_check(self) -> list[str]:
        """The baseline itself must be valid (who=code parameters are checked against range only)."""
        problems = []
        for p in self.params.values():
            if p.type not in TYPES or p.kind not in KINDS or p.who not in WHO:
                problems.append(f"{p.id}: bad type/kind/who")
            if p.kind not in p.kinds_allowed:
                problems.append(f"{p.id}: kind {p.kind} not in kinds_allowed")
            if not p.description.get("es") or not p.description.get("en"):
                problems.append(f"{p.id}: description es/en missing")
            if not p.source:
                problems.append(f"{p.id}: source missing")
            if p.who != "code":
                problems += self.check_value(p.id, p.value)
            if p.type == "number" and p.range is None:
                problems.append(f"{p.id}: number without range")
        return problems + self.check_constraints(self.baseline())

    # ------------------------------------------------------------------ effective values and stores
    def values(self, changes: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
        out = self.baseline()
        for pid, ch in (changes or {}).items():
            if "value" in ch:
                out[pid] = ch["value"]
        return out

    def kinds(self, changes: dict[str, dict[str, Any]] | None = None) -> dict[str, str]:
        out = {pid: p.kind for pid, p in self.params.items()}
        for pid, ch in (changes or {}).items():
            if ch.get("kind"):
                out[pid] = ch["kind"]
        return out

    def materialize(self, changes: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
        """Copies of the stores with the changes written in (value and, for design parameters, kind)."""
        out = {name: copy.deepcopy(data) for name, data in self.stores.items()}
        for pid, ch in (changes or {}).items():
            p = self.get(pid)
            if "value" in ch:
                set_path(out[p.store], p.path, copy.deepcopy(ch["value"]))
            if ch.get("kind") and p.kind_path:
                set_path(out[p.store], p.kind_path, ch["kind"])
        return out


# ---------------------------------------------------------------------------------------------- loading


def _ruleset(name: str) -> dict[str, Any]:
    return load_resource_json("spaceplan", "data", "rules", name)


def default_stores(refs: dict[str, Any]) -> dict[str, Any]:
    stores: dict[str, Any] = {CATALOG: load_catalog_data(),
                              STACKING: load_resource_json("spaceplan", "data", "catalog", "stacking_catalog.json")}
    names = set(refs["design_rulesets"])
    for ref in refs["refs"]:
        if ref["store"].startswith(RULESET_PREFIX):
            names.add(ref["store"][len(RULESET_PREFIX):])
    for name in sorted(names):
        stores[RULESET_PREFIX + name] = _ruleset(name)
    return stores


def _floor(stores: dict[str, Any], spec: dict[str, Any] | None, unit: str | None) -> Floor | None:
    if not spec:
        return None
    key = RULESET_PREFIX + spec["ruleset"]
    if key not in stores:
        stores[key] = _ruleset(spec["ruleset"])
    rule = get_path(stores[key], f"rules[rule_id={spec['rule_id']}]")
    raw = get_path(rule, spec["key"])
    src = rule.get("source") or {}
    return Floor(spec["ruleset"], spec["rule_id"], spec["key"], spec.get("bound", "min"),
                 round(convert(raw, spec.get("unit"), unit), 6), unit,
                 f"{src.get('document', '')} {src.get('section', '')}".strip())


def _range(spec: dict[str, Any], value: Any) -> tuple[float, float] | None:
    if spec.get("range") is not None:
        return float(spec["range"][0]), float(spec["range"][1])
    if spec.get("range_rel") is not None and isinstance(value, (int, float)):
        a, b = spec["range_rel"]
        return round(value * a, 2), round(value * b, 2)
    return None


def _store_source(stores: dict[str, Any], store: str, path: str) -> tuple[dict[str, str], bool]:
    if store.startswith(RULESET_PREFIX):
        rid = path.split("]")[0].split("=")[-1] if path.startswith("rules[") else None
        if rid:
            rule = get_path(stores[store], f"rules[rule_id={rid}]")
            return dict(rule.get("source") or {}), bool(rule.get("verified", False))
    if store == CATALOG:
        src = stores[CATALOG].get("default_source") or {}
        return {"document": src.get("citation", "residential catalog"), "section": path}, src.get("status") == "verified"
    return {"document": "stacking catalog", "section": path}, False


def _expanded(entry: dict[str, Any], design_spaces: list[str]) -> list[dict[str, Any]]:
    targets = entry.get("for")
    if targets is None:
        return [entry]
    if targets == DESIGN_SPACES:
        targets = design_spaces
    out = []
    for t in targets:
        e = copy.deepcopy(entry)
        e.pop("for")
        for k in ("id", "path"):
            if k in e:
                e[k] = expand(e[k], t=t)
        if "le" in e:
            e["le"] = [expand(i, t=t) for i in e["le"]]
        if "description" in e:
            e["description"] = {lang: expand(txt, t=t) for lang, txt in e["description"].items()}
        out.append(e)
    return out


def _design_params(stores: dict[str, Any], name: str) -> list[Param]:
    data = stores[RULESET_PREFIX + name]
    out = []
    for rule in data["rules"]:
        prefix = rule["param_prefix"]
        for key, obj in rule.get("parameters", {}).items():
            if not (isinstance(obj, dict) and "value" in obj and "kind" in obj):
                continue
            pid = f"{prefix}.{key}"
            base = f"rules[rule_id={rule['rule_id']}].parameters.{key}"
            out.append(Param(
                id=pid, value=obj["value"], type=obj["type"], unit=obj.get("unit"), kind=obj["kind"],
                kinds_allowed=tuple(obj.get("kinds_allowed") or (obj["kind"],)), who=obj["who"],
                range=tuple(obj["range"]) if obj.get("range") else None,
                choices=tuple(obj["choices"]) if obj.get("choices") is not None else None,
                floor=_floor(stores, obj.get("floor"), obj.get("unit")), description=obj["description"],
                store=RULESET_PREFIX + name, path=f"{base}.value", kind_path=f"{base}.kind",
                source=dict(obj.get("source") or rule.get("source") or {}), verified=bool(rule.get("verified")),
                origin="design", note=obj.get("note")))
    return out


def build_registry(refs: dict[str, Any], stores: dict[str, Any]) -> DesignRegistry:
    reg = DesignRegistry(stores=stores, refs=refs)
    for name in refs["design_rulesets"]:
        for p in _design_params(stores, name):
            if p.id in reg.params:
                raise DesignRegistryError(f"duplicate parameter {p.id}")
            reg.params[p.id] = p
    design_spaces = sorted({p.id.split(".")[1] for p in reg.params.values()
                            if p.id.startswith("space.") and p.id.endswith(".aspect_max")})
    for entry in refs["refs"]:
        for e in _expanded(entry, design_spaces):
            value = get_path(stores[e["store"]], e["path"])
            source, verified = _store_source(stores, e["store"], e["path"])
            p = Param(id=e["id"], value=value, type=e["type"], unit=e.get("unit"), kind=e["kind"],
                      kinds_allowed=tuple(e.get("kinds_allowed") or (e["kind"],)), who=e["who"],
                      range=_range(e, value), choices=tuple(e["choices"]) if e.get("choices") is not None else None,
                      floor=_floor(stores, e.get("floor"), e.get("unit")), description=e["description"],
                      store=e["store"], path=e["path"], kind_path=None, source=source, verified=verified,
                      origin="reference", note=e.get("note"))
            if p.id in reg.params:
                raise DesignRegistryError(f"duplicate parameter {p.id}")
            reg.params[p.id] = p
    for entry in refs.get("constraints", []):
        for e in _expanded(entry, design_spaces):
            reg.constraints.append((tuple(e["le"]), e.get("description", {})))
    return reg


def load_registry(stores: dict[str, Any] | None = None, refs: dict[str, Any] | None = None) -> DesignRegistry:
    """Registry over the shipped stores (or the given ones, e.g. materialized by a profile)."""
    refs = refs or load_resource_json("spaceplan", *REFS_RESOURCE)
    return build_registry(refs, stores if stores is not None else default_stores(refs))


__all__ = ["CATALOG", "DESIGN_SPACES", "KINDS", "RULESET_PREFIX", "STACKING", "TYPES", "WHO", "DesignRegistry",
           "DesignRegistryError", "Floor", "Param", "build_registry", "default_stores", "load_registry"]
