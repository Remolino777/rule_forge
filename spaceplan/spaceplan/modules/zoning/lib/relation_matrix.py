"""Space relation matrix D / I / N by dwelling type (catalog), with brief overrides.

D  direct: shared door, or both open onto the same foyer or hall (immediate connection through circulation)
I  indirect: no shared door, reachable through exactly one intermediate space
N  no constraint (pairs absent from the matrix)
Roles map space types to the matrix rows (Acceso, Sala, Comedor, ...). "@patio" is the backyard.
"""

from __future__ import annotations

from dataclasses import dataclass

from spaceplan.core.lib.catalog import Catalog

PATIO = "@patio"
ENTRY = "@entry"


@dataclass(frozen=True)
class MatrixPair:
    a: str
    b: str
    type: str
    kind: str
    weight: float
    source: str

    @property
    def pair_id(self) -> str:
        return f"{self.type}:{self.a}-{self.b}"


@dataclass(frozen=True)
class MatrixGroup:
    group_id: str
    pair_ids: tuple[str, ...]
    k: int


@dataclass(frozen=True)
class RelationMatrix:
    dwelling_type: str
    roles: dict[str, frozenset[str]]
    pairs: tuple[MatrixPair, ...]
    groups: tuple[MatrixGroup, ...] = ()

    def roles_of(self, space_type: str) -> frozenset[str]:
        return frozenset(r for r, types in self.roles.items() if space_type in types)

    def d_directed(self, t1: str, t2: str) -> bool:
        """A D pair whose row role is t1's and column role is t2's (bedroom -> its bath, not the reverse)."""
        r1, r2 = self.roles_of(t1), self.roles_of(t2)
        return any(p.type == "D" and p.a in r1 and p.b in r2 for p in self.pairs)

    def d_between_types(self, t1: str, t2: str) -> bool:
        """Is there any D pair linking these two space types (used to allow doors between terminal rooms)?"""
        r1, r2 = self.roles_of(t1), self.roles_of(t2)
        return any(p.type == "D" and ((p.a in r1 and p.b in r2) or (p.a in r2 and p.b in r1)) for p in self.pairs)


def load_matrix(catalog: Catalog, dwelling_type: str, overrides: list[dict] | None = None) -> RelationMatrix:
    data = catalog.data["relation_matrix"]
    roles = {r: frozenset(t) for r, t in data["roles"].items()}
    pairs = {frozenset((p["a"], p["b"])) if p["a"] != p["b"] else frozenset((p["a"],)): p for p in data[dwelling_type]}
    for o in overrides or []:
        for role in (o["a"], o["b"]):
            if role not in roles:
                raise ValueError(f"relation_overrides: unknown role {role!r}; roles are {sorted(roles)}")
        key = frozenset((o["a"], o["b"])) if o["a"] != o["b"] else frozenset((o["a"],))
        if o["type"] == "N":
            pairs.pop(key, None)
            continue
        base = pairs.get(key, {})
        pairs[key] = {"a": o["a"], "b": o["b"], "type": o["type"], "kind": o.get("kind", base.get("kind", "soft")),
                      "weight": o.get("weight", base.get("weight", 1.0 if o["type"] == "D" else 0.5)),
                      "source": {"citation": "brief:relation_overrides"}}
    out = tuple(
        MatrixPair(p["a"], p["b"], p["type"], p["kind"], p["weight"], p["source"]["citation"])
        for p in pairs.values()
    )
    groups = tuple(MatrixGroup(g["group_id"], tuple(g["pairs"]), g["k"])
                   for g in data["hard_groups"][dwelling_type]
                   if sum(any(p.pair_id == pid for p in out) for pid in g["pairs"]) >= g["k"])
    return RelationMatrix(dwelling_type, roles, out, groups)
