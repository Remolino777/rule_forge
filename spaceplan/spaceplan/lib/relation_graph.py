"""Typed relation graph of a brief (NetworkX MultiGraph).

Alternative relations are hyperedges "at least k of n": each member pair becomes a candidate
edge carrying the group id, so the graph stays a plain MultiGraph and groups are checked apart.
"""

from __future__ import annotations

from collections import defaultdict

import networkx as nx

from spaceplan.lib.enums import NodeKind, RelationType, SiteZone, Zone


def node_namespace(brief: dict) -> dict[str, NodeKind]:
    """Every id a relation may reference, with its node kind."""
    namespace: dict[str, NodeKind] = {z.value: NodeKind.ZONE for z in Zone}
    namespace.update({s.value: NodeKind.SITE_ZONE for s in SiteZone})
    namespace.update({s["street_id"]: NodeKind.CONTEXT for s in brief.get("streets", [])})
    namespace.update({s["space_id"]: NodeKind.SPACE for s in brief["program"]["spaces"]})
    return namespace


def build_relation_graph(brief: dict) -> nx.MultiGraph:
    namespace = node_namespace(brief)
    graph = nx.MultiGraph()

    def add_node(node_id: str) -> None:
        if node_id not in graph:
            graph.add_node(node_id, kind=namespace.get(node_id))

    for space in brief["program"]["spaces"]:
        add_node(space["space_id"])
        graph.nodes[space["space_id"]].update(zone=space["zone"], scale=space["scale"])
    for rel in brief["relations"]:
        add_node(rel["a"])
        add_node(rel["b"])
        graph.add_edge(
            rel["a"],
            rel["b"],
            key=rel["relation_id"],
            type=rel["type"],
            weight=rel.get("weight", 1.0),
            requires_door=rel.get("requires_door", False),
            applies_to=rel.get("applies_to", "adjacency"),
            group_id=None,
        )
    for group in brief["relation_groups"]:
        for index, member in enumerate(group["members"]):
            add_node(member["a"])
            add_node(member["b"])
            graph.add_edge(
                member["a"],
                member["b"],
                key=f"{group['group_id']}:{index}",
                type=RelationType.ALTERNATIVE.value,
                weight=1.0,
                requires_door=group.get("requires_door", False),
                applies_to="adjacency",
                group_id=group["group_id"],
                k=group["k"],
            )
    return graph


def alternative_groups(graph: nx.MultiGraph) -> dict[str, list[tuple[str, str]]]:
    groups: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for a, b, data in graph.edges(data=True):
        if data.get("group_id"):
            groups[data["group_id"]].append((a, b))
    return dict(groups)


def relation_conflicts(graph: nx.MultiGraph) -> list[str]:
    """Contradictions: a pair forbidden for adjacency yet required, or a group left unsatisfiable."""
    forbidden = {
        frozenset((a, b))
        for a, b, d in graph.edges(data=True)
        if d["type"] == RelationType.FORBIDDEN and d["applies_to"] == "adjacency"
    }
    forbidden_openings = {
        frozenset((a, b))
        for a, b, d in graph.edges(data=True)
        if d["type"] == RelationType.FORBIDDEN and d["applies_to"] == "opening"
    }
    errors = []
    for a, b, key, d in graph.edges(keys=True, data=True):
        pair = frozenset((a, b))
        if d["type"] == RelationType.MANDATORY and pair in forbidden:
            errors.append(f"relation {key}: {a}-{b} is mandatory and forbidden")
        if d["type"] == RelationType.MANDATORY and d["requires_door"] and pair in forbidden_openings:
            errors.append(f"relation {key}: {a}-{b} requires a door but openings are forbidden")
    for group_id, members in alternative_groups(graph).items():
        k = next(d["k"] for _, _, d in graph.edges(data=True) if d.get("group_id") == group_id)
        allowed = [m for m in members if frozenset(m) not in forbidden]
        if len(allowed) < k:
            errors.append(f"group {group_id}: only {len(allowed)} allowed members for k={k}")
    return errors
