import pytest
from conftest import BRIEFS, load_brief

from spaceplan.core.lib.enums import BoundaryClass, Constraint, RelationType, Scale, Zone
from spaceplan.core.lib.relation_graph import alternative_groups, build_relation_graph
from spaceplan.core.lib.schema_validation import (
    BriefValidationError,
    load_schema,
    validate_brief,
    validate_package,
)


@pytest.mark.parametrize("name", BRIEFS)
def test_reference_briefs_are_valid(name):
    validate_brief(load_brief(name))


@pytest.mark.parametrize("name", BRIEFS)
def test_packages_are_valid_and_deterministic(name, packages, apartments):
    pkg = {**packages, **apartments}[name]
    validate_package(pkg)
    from spaceplan.pipeline.main.run_capacity import run_capacity

    assert run_capacity(load_brief(name)) == pkg


def test_enums_match_schemas():
    brief = load_schema("brief")["$defs"]
    package = load_schema("package")["$defs"]
    assert set(brief["edge"]["properties"]["boundary_class"]["enum"]) - {None} == {b.value for b in BoundaryClass}
    assert set(brief["space"]["properties"]["zone"]["enum"]) == {z.value for z in Zone}
    assert set(brief["space"]["properties"]["scale"]["enum"]) <= {s.value for s in Scale}
    relation_types = set(brief["relation"]["properties"]["type"]["enum"]) | {"alternative"}
    assert relation_types == {r.value for r in RelationType}
    assert set(package["constraint"]["enum"]) == {c.value for c in Constraint}


def _errors(brief):
    with pytest.raises(BriefValidationError) as info:
        validate_brief(brief)
    return " | ".join(info.value.errors)


def test_duplicate_edge_id_rejected():
    brief = load_brief("interior_50x100")
    brief["lot"]["edges"][1]["edge_id"] = "e0"
    assert "duplicate edge_id" in _errors(brief)


def test_unknown_relation_endpoint_rejected():
    brief = load_brief("interior_50x100")
    brief["relations"][0]["b"] = "swimming_pool"
    assert "unknown endpoint" in _errors(brief)


def test_street_edge_mismatch_rejected():
    brief = load_brief("interior_50x100")
    brief["lot"]["edges"][2]["street_id"] = "street_main"
    assert "does not list it as frontage" in _errors(brief)


def test_two_primary_streets_rejected():
    brief = load_brief("corner_55x100")
    brief["streets"][1]["role"] = "primary"
    assert "exactly one primary street" in _errors(brief)


def test_arc_edge_requires_arc_block():
    brief = load_brief("interior_50x100")
    brief["lot"]["edges"][0]["kind"] = "arc"
    assert "'arc' is a required property" in _errors(brief)


def test_alternative_group_is_a_hyperedge():
    graph = build_relation_graph(load_brief("interior_50x100"))
    groups = alternative_groups(graph)
    assert set(map(frozenset, groups["g01_garage_link"])) == {
        frozenset({"garage", "kitchen"}),
        frozenset({"garage", "service"}),
    }


def test_forbidden_member_makes_group_unsatisfiable():
    brief = load_brief("interior_50x100")
    for b in ("kitchen", "service"):
        brief["relations"].append(
            {"relation_id": f"rx_{b}", "type": "forbidden", "a": "garage", "b": b,
             "applies_to": "adjacency", "source": {"kind": "client", "status": "verified"}}
        )
    assert "only 0 allowed members" in _errors(brief)


def test_mandatory_and_forbidden_conflict():
    brief = load_brief("interior_50x100")
    brief["relations"].append(
        {"relation_id": "rx", "type": "forbidden", "a": "circulation", "b": "entry_deck",
         "applies_to": "adjacency", "source": {"kind": "client", "status": "verified"}}
    )
    assert "mandatory and forbidden" in _errors(brief)


def test_apartment_brief_cannot_carry_a_lot():
    brief = load_brief("apt_2br_interior")
    brief["lot"] = load_brief("interior_50x100")["lot"]
    with pytest.raises(BriefValidationError):
        validate_brief(brief)


def test_apartment_entrance_must_be_on_the_access_edge():
    brief = load_brief("apt_2br_interior")
    brief["unit"]["entrance"]["edge_id"] = "u2"
    assert "entrance must be on an edge with role 'access'" in _errors(brief)
