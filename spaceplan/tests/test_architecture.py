"""Layering and anti-circularity guards (plan v3.0 / planogen v2 critique)."""

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1] / "spaceplan"
FORBIDDEN_TOP_LEVEL = {"geom", "vision", "engine", "ruleforge"}  # extractor / verifier packages


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def _files(sub: str):
    return sorted((ROOT / sub).rglob("*.py"))


@pytest.mark.parametrize("path", _files("lib_aux"), ids=lambda p: p.name)
def test_lib_aux_is_leaf(path):
    assert not any(m.startswith(("spaceplan.lib.", "spaceplan.main")) or m == "spaceplan.lib" for m in _imports(path))


@pytest.mark.parametrize("path", _files("lib"), ids=lambda p: p.name)
def test_lib_does_not_import_main(path):
    assert not any(m.startswith("spaceplan.main") for m in _imports(path))


# ------------------------------------------------------------------ architecture v2 (refactor tanda 1)


def _spaceplan_imports(path: Path) -> set[str]:
    return {m for m in _imports(path) if m == "spaceplan" or m.startswith("spaceplan.")}


@pytest.mark.parametrize("path", _files("core"), ids=lambda p: str(p.relative_to(ROOT)))
def test_core_imports_only_core(path):
    """spaceplan.core is shared by every module and imports nothing outside spaceplan.core."""
    outside = {m for m in _spaceplan_imports(path) if not m.startswith("spaceplan.core")}
    assert outside == set()


@pytest.mark.parametrize("path", _files("core/lib_aux"), ids=lambda p: p.name)
def test_core_lib_aux_is_leaf(path):
    assert not {m for m in _spaceplan_imports(path) if not m.startswith("spaceplan.core.lib_aux")}


def test_core_has_the_planned_files():
    names = {p.stem for p in _files("core") if p.stem != "__init__"}
    assert {"enums", "rules", "catalog", "schema_validation", "relation_graph", "geometry", "quantity", "hashing",
            "json_io", "tolerances", "section", "predicates", "knee", "weighted", "allocation", "pareto"} <= names


@pytest.mark.parametrize("path", [p for p in _files("lib_aux") if p.stem != "__init__"] +
                         [ROOT / "lib" / f"{m}.py" for m in ("enums", "rules", "catalog", "schema_validation",
                                                              "relation_graph")], ids=lambda p: p.name)
def test_bridge_modules_reexport_core(path):
    """Old paths are bridges (removed in tanda 4): they only re-export the core module, same objects."""
    import importlib

    layer = path.parent.name
    old = importlib.import_module(f"spaceplan.{layer}.{path.stem}")
    new = importlib.import_module(f"spaceplan.core.{layer}.{path.stem}")
    assert _spaceplan_imports(path) == {f"spaceplan.core.{layer}.{path.stem}"}
    public = getattr(new, "__all__", [n for n in vars(new) if not n.startswith("_")])
    assert public and all(getattr(old, n) is getattr(new, n) for n in public)


@pytest.mark.parametrize("path", sorted(ROOT.rglob("*.py")), ids=lambda p: p.name)
def test_no_extractor_imports(path):
    assert not {m.split(".")[0] for m in _imports(path)} & FORBIDDEN_TOP_LEVEL


def test_no_normative_numbers_in_rule_variants():
    """Setback/FAR values must come from the ruleset, not from literals in the decision code."""
    source = (ROOT / "modules" / "lotcap" / "lib" / "rule_variants.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    literals = {n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, (int, float))}
    assert not literals & {15, 13, 4, 5, 0.08, 0.6, 0.59, 24, 30, 50, 100, 150}


def test_no_crc_numbers_in_program_review():
    tree = ast.parse((ROOT / "modules" / "household" / "lib" / "program_review.py").read_text(encoding="utf-8"))
    literals = {n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, (int, float))}
    assert not literals & {70, 7, 0.08, 0.04}


# ------------------------------------------------------------------ architecture v3 (refactor tanda 2)
# REFACTOR_PLAN.md section 3: modules/<m>/{main,lib,lib_aux} + pipeline, acyclic module graph (3.2).

MODULES = ("lotcap", "site", "household", "cost", "profiles", "zoning", "areas", "viz")
ALLOWED = {  # plan 3.2: module -> modules it may import (besides itself)
    "core": set(),
    "lotcap": {"core"},
    "household": {"core"},
    "cost": {"core"},
    "site": {"core", "lotcap"},
    "profiles": {"core", "household", "cost"},
    "zoning": {"core", "lotcap", "site"},
    "areas": {"core", "lotcap", "site", "household", "cost", "profiles"},
    "viz": {"core", "lotcap"},  # contracts, plus lotcap types to draw the lot
    "pipeline": {"core", *MODULES},
}
# Temporary exceptions (2026-10-08, refactor tanda 2): current dependencies that break the 3.2 graph or the
# "no main imports another module's main" rule. Each one is (importing file, imported module); they are
# resolved and removed in tanda 3. A dependency not listed here that breaks the graph fails the test.
TEMPORARY_EXCEPTIONS = {
    # areas workflow runs the capacity pipeline, the household and profile workflows and draws its sheets
    ("modules/areas/main/run_area_matrix.py", "spaceplan.pipeline.main.run_capacity"),
    ("modules/areas/main/run_area_matrix.py", "spaceplan.modules.viz.lib.review_notes"),
    ("modules/areas/main/run_area_matrix.py", "spaceplan.modules.viz.lib.visualize"),
    ("modules/areas/main/run_area_matrix.py", "spaceplan.modules.household.main.run_household"),
    ("modules/areas/main/run_area_matrix.py", "spaceplan.modules.profiles.main.run_profiles"),
    ("modules/areas/main/run_area_matrix.py", "spaceplan.modules.lotcap.main.run_lotcap"),
    # household workflow prices the derived programs and prints the parameter table
    ("modules/household/main/run_household.py", "spaceplan.modules.cost.main.run_cost"),
    ("modules/household/main/run_program.py", "spaceplan.pipeline.lib.catalog_table"),
    # profiles workflow runs the capacity pipeline on the lot, builds a lot and draws its sheets
    ("modules/profiles/main/run_profiles.py", "spaceplan.pipeline.main.run_capacity"),
    ("modules/profiles/main/run_profiles.py", "spaceplan.modules.lotcap.lib.lot"),
    ("modules/profiles/main/run_profiles.py", "spaceplan.modules.viz.lib.review_notes"),
    ("modules/profiles/main/run_profiles.py", "spaceplan.modules.viz.lib.visualize"),
    ("modules/profiles/main/run_profiles.py", "spaceplan.modules.household.main.run_household"),
}
BRIDGE_PACKAGES = ("lib", "lib_aux", "main")  # old paths: bridge modules only (removed in tanda 4)


def _unit(dotted: str) -> str | None:
    """Module (graph node) of a dotted name: core, one of MODULES, pipeline; 'bridge' for the old paths."""
    parts = dotted.split(".")
    if len(parts) < 2 or parts[0] != "spaceplan":
        return None
    if parts[1] == "modules":
        return parts[2] if len(parts) > 2 else None
    if parts[1] in BRIDGE_PACKAGES:
        return "bridge"
    return parts[1] if parts[1] in ("core", "pipeline") else None


def _layer(dotted: str) -> str | None:
    parts = dotted.split(".")
    if parts[1] == "modules":
        return parts[3] if len(parts) > 3 else None
    if parts[1] in ("core", "pipeline"):
        return parts[2] if len(parts) > 2 else None
    return None


def _real_files():
    """Every module file except the bridges at the old paths."""
    return [p for p in sorted(ROOT.rglob("*.py"))
            if len(p.relative_to(ROOT).parts) > 1 and p.relative_to(ROOT).parts[0] not in BRIDGE_PACKAGES]


def _dotted(path: Path) -> str:
    return ".".join(("spaceplan", *path.relative_to(ROOT).with_suffix("").parts))


def _module_edges():
    """(importing file, imported module, from unit, to unit) for every cross-module import (bridges excluded)."""
    edges = []
    for path in _real_files():
        src = _unit(_dotted(path))
        for target in _spaceplan_imports(path):
            dst = _unit(target)
            if dst is not None and dst != src:
                edges.append((str(path.relative_to(ROOT)), target, src, dst))
    return edges


def test_every_module_has_main_lib_lib_aux():
    for name in MODULES:
        for layer in ("", "main", "lib", "lib_aux"):
            assert (ROOT / "modules" / name / layer / "__init__.py").is_file(), (name, layer)
    for layer in ("", "main", "lib"):
        assert (ROOT / "pipeline" / layer / "__init__.py").is_file(), layer


def test_files_follow_plan_table():
    """REFACTOR_PLAN.md table 3.1."""
    planned = {
        "lotcap/lib": {"lot", "boundaries", "lot_metrics", "rule_variants", "scope", "capacity", "flag_lot"},
        "lotcap/main": {"run_lotcap"},
        "site/lib": {"site_partition", "orientation", "backyard"},
        "household/lib": {"household", "household_catalog", "household_rules", "culture", "program_builder",
                          "program_review"},
        "household/main": {"run_household", "run_program"},
        "cost/lib": {"quantities", "cost_models", "budget", "cost_sensitivity"},
        "cost/main": {"run_cost"},
        "profiles/lib": {"program_profiles"},
        "profiles/main": {"run_profiles"},
        "zoning/lib": {"zoning", "space_layout", "circulation", "relation_matrix", "realization", "polygonal",
                       "corrections", "unit"},
        "zoning/main": {"run_corrections"},
        "areas/lib": {"vertical_split", "building_indices", "area_budget", "area_matrix"},
        "areas/main": {"run_area_matrix"},
        "viz/lib": {"visualize", "review_notes"},
    }
    for sub, names in planned.items():
        assert {p.stem for p in (ROOT / "modules" / sub).glob("*.py") if p.stem != "__init__"} == names, sub
    assert {p.stem for p in (ROOT / "pipeline" / "lib").glob("*.py")} >= {"package", "catalog_table"}
    assert {p.stem for p in (ROOT / "pipeline" / "main").glob("*.py")} >= {"run_capacity", "cli"}


@pytest.mark.parametrize("path", _real_files(), ids=lambda p: str(p.relative_to(ROOT)))
def test_real_modules_do_not_import_bridges(path):
    """Code imports the canonical paths; the old spaceplan.lib/lib_aux/main paths are only for callers."""
    assert not {m for m in _spaceplan_imports(path) if _unit(m) == "bridge" or m in ("spaceplan.lib", "spaceplan.main")}


@pytest.mark.parametrize("path", _real_files(), ids=lambda p: str(p.relative_to(ROOT)))
def test_layers_inside_each_module(path):
    """lib_aux imports no lib/main; lib imports no main (of any module)."""
    layer = _layer(_dotted(path))
    imported = {_layer(m) for m in _spaceplan_imports(path) if _unit(m) not in (None, "bridge")}
    if layer == "lib_aux":
        assert not imported & {"lib", "main"}
    elif layer == "lib":
        assert "main" not in imported


def test_module_graph_follows_plan():
    """Plan 3.2, counted per module without the bridges; temporary exceptions are listed above."""
    violations = {(f, m) for f, m, src, dst in _module_edges() if dst not in ALLOWED[src]}
    assert violations - TEMPORARY_EXCEPTIONS == set()


def test_no_main_imports_another_modules_main():
    """Only the pipeline composes workflows."""
    chains = {(f, m) for f, m, src, dst in _module_edges()
              if src in MODULES and _layer(_dotted(ROOT / f)) == "main" and _layer(m) == "main"}
    assert chains - TEMPORARY_EXCEPTIONS == set()


def test_temporary_exceptions_are_still_needed():
    """An exception that no longer exists must be removed from the list (tanda 3 empties it)."""
    current = {(f, m) for f, m, _, _ in _module_edges()}
    assert TEMPORARY_EXCEPTIONS <= current


def test_allowed_graph_is_acyclic():
    import networkx as nx

    graph = nx.DiGraph([(src, dst) for src, dsts in ALLOWED.items() for dst in dsts])
    assert nx.is_directed_acyclic_graph(graph)


TANDA2_BRIDGES = sorted(p for sub in ("lib", "main") for p in (ROOT / sub).glob("*.py")
                        if p.stem != "__init__" and "spaceplan.core." not in p.read_text(encoding="utf-8"))


@pytest.mark.parametrize("path", TANDA2_BRIDGES, ids=lambda p: f"{p.parent.name}/{p.name}")
def test_tanda2_bridges_reexport_their_module(path):
    """spaceplan.lib.* / spaceplan.main.* bridges import only their new module and re-export the same objects."""
    import importlib

    targets = _spaceplan_imports(path)
    assert len(targets) == 1
    (target,) = targets
    assert _unit(target) in (*MODULES, "pipeline") and target.rsplit(".", 1)[1] == path.stem
    old = importlib.import_module(f"spaceplan.{path.parent.name}.{path.stem}")
    new = importlib.import_module(target)
    public = getattr(new, "__all__", [n for n in vars(new) if not n.startswith("_")])
    assert public and all(getattr(old, n) is getattr(new, n) for n in public)


def test_tanda2_bridges_cover_the_old_files():
    assert len(TANDA2_BRIDGES) == 45  # 37 lib + 8 main files (the 5 core bridges of tanda 1 are not counted)


def test_prepare_lot_lives_in_lotcap():
    from spaceplan.main.run_capacity import LotSetup as OldSetup
    from spaceplan.main.run_capacity import prepare_lot as old_prepare
    from spaceplan.modules.lotcap.main.run_lotcap import LotSetup, prepare_lot

    assert old_prepare is prepare_lot and OldSetup is LotSetup
    assert prepare_lot.__module__ == "spaceplan.modules.lotcap.main.run_lotcap"
