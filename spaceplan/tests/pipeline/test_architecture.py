"""Layering and anti-circularity guards (plan v3.0 / planogen v2 critique)."""

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2] / "spaceplan"
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


def test_old_packages_are_gone():
    """Tanda 4 removed the bridge packages spaceplan.lib, spaceplan.lib_aux and spaceplan.main."""
    import importlib.util

    for name in ("lib", "lib_aux", "main"):
        assert not (ROOT / name).exists(), name
        assert importlib.util.find_spec(f"spaceplan.{name}") is None, name


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
# Temporary exceptions (2026-10-08, refactor tanda 2): dependencies that broke the 3.2 graph or the "no main
# imports another module's main" rule. Refactor tanda 3 (2026-10-09) resolved all of them: the list stays empty
# and a dependency that breaks the graph fails the test.
TEMPORARY_EXCEPTIONS: set[tuple[str, str]] = set()
BRIDGE_PACKAGES = ("lib", "lib_aux", "main")  # old paths: bridge modules until tanda 3, removed in tanda 4


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
        "lotcap/main": {"run_lotcap", "contract"},  # contract: tanda 4 (to_contract / from_contract)
        "site/lib": {"site_partition", "orientation", "backyard"},
        "household/lib": {"household", "household_catalog", "household_rules", "culture", "program_builder",
                          "program_review"},
        "household/main": {"run_household", "run_program", "contract"},
        "cost/lib": {"quantities", "cost_models", "budget", "cost_sensitivity"},
        "cost/main": {"run_cost", "contract"},
        "profiles/lib": {"program_profiles"},
        "profiles/main": {"run_profiles", "contract"},
        "site/main": {"run_site", "contract"},  # run_site: tanda 3
        "zoning/lib": {"zoning", "space_layout", "circulation", "relation_matrix", "realization", "polygonal",
                       "corrections", "unit", "band_enumeration"},  # band_enumeration: tanda 3 (cycle broken)
        "zoning/main": {"run_corrections", "run_zoning", "contract"},  # run_zoning: tanda 3
        "areas/lib": {"vertical_split", "building_indices", "area_budget", "area_matrix"},
        "areas/main": {"run_area_matrix", "contract"},
        "viz/lib": {"review_notes", "lot_site_plots", "zoning_plots", "review_sheets", "portfolio_sheet",
                    "area_matrix_plots"},  # tanda 3: visualize split by topic; tanda 4: facade removed
        "viz/main": {"run_viz"},  # tanda 4: figures from contracts
    }
    for sub, names in planned.items():
        assert {p.stem for p in (ROOT / "modules" / sub).glob("*.py") if p.stem != "__init__"} == names, sub
    assert {p.stem for p in (ROOT / "pipeline" / "lib").glob("*.py")} >= {"package", "catalog_table"}
    assert {p.stem for p in (ROOT / "pipeline" / "main").glob("*.py")} >= {
        "run_capacity", "cli", "run_household_report", "run_catalog", "run_portfolio", "run_area_analysis",
        "run_modules"}


@pytest.mark.parametrize("path", _real_files(), ids=lambda p: str(p.relative_to(ROOT)))
def test_real_modules_do_not_import_bridges(path):
    """Code imports the canonical paths (the old spaceplan.lib/lib_aux/main bridges were removed in tanda 4)."""
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


def test_temporary_exceptions_are_resolved():
    """Tanda 3 resolved every temporary exception of tanda 2: the list is empty."""
    assert TEMPORARY_EXCEPTIONS == set()


def test_allowed_graph_is_acyclic():
    import networkx as nx

    graph = nx.DiGraph([(src, dst) for src, dsts in ALLOWED.items() for dst in dsts])
    assert nx.is_directed_acyclic_graph(graph)


def test_module_graph_has_no_cycles():
    """Real dependency graph between modules (core, the 8 modules, pipeline), bridges excluded."""
    import networkx as nx

    graph = nx.DiGraph([(src, dst) for _, _, src, dst in _module_edges()])
    assert list(nx.simple_cycles(graph)) == []


def _file_graph():
    """Import graph between real files (module-level and deferred imports, `from pkg import module` included)."""
    import networkx as nx

    files = {_dotted(p): p for p in _real_files()}
    graph = nx.DiGraph()
    graph.add_nodes_from(files)
    for name, path in files.items():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("spaceplan."):
                targets = [node.module, *(f"{node.module}.{a.name}" for a in node.names)]
            elif isinstance(node, ast.Import):
                targets = [a.name for a in node.names]
            else:
                continue
            for target in targets:
                if target in files and target != name:
                    graph.add_edge(name, target)
    return graph


def test_file_import_graph_has_no_cycles():
    """No import cycle between files, deferred imports included (tanda 3 broke zoning <-> space_layout)."""
    import networkx as nx

    assert list(nx.simple_cycles(_file_graph())) == []


def test_zoning_and_space_layout_share_band_enumeration():
    graph = _file_graph()
    zoning, layout = "spaceplan.modules.zoning.lib.zoning", "spaceplan.modules.zoning.lib.space_layout"
    bands = "spaceplan.modules.zoning.lib.band_enumeration"
    assert not graph.has_edge(layout, zoning)
    assert graph.has_edge(layout, bands) and graph.has_edge(zoning, bands)


def _cross_module_names():
    """(importing file, imported module, name) for every `from X import name` across modules (bridges excluded)."""
    out = []
    for path in _real_files():
        src = _unit(_dotted(path))
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("spaceplan."):
                dst = _unit(node.module)
                if dst not in (None, "bridge", src):
                    out.extend((str(path.relative_to(ROOT)), node.module, a.name) for a in node.names)
    return out


def test_no_private_names_across_modules():
    """Modules talk through public names only (tanda 3: site publishes what areas needs)."""
    assert [(f, m, n) for f, m, n in _cross_module_names() if n.startswith("_")] == []


def test_cross_module_imports_use_declared_interfaces():
    """When a file declares __all__ (its public interface), other modules import only names listed there."""
    import importlib

    wrong = []
    for f, m, n in _cross_module_names():
        module = importlib.import_module(m)
        exported = getattr(module, "__all__", None)
        if exported is not None and n not in exported and not hasattr(importlib.import_module(m), "__path__"):
            wrong.append((f, m, n))
    assert wrong == []


def test_site_interface_is_declared():
    from spaceplan.modules.site.lib import site_partition

    assert {"site_context", "measure_footprint", "front_yard_area", "build_site_partition"} <= set(
        site_partition.__all__)
    assert all(not n.startswith("_") for n in site_partition.__all__)


def test_capacity_pipeline_is_a_thin_orchestrator():
    """run_capacity composes module workflows: household, cost, flag lot, site and zoning go through their main/
    (tanda 4: cost through its contract module, which reads the upstream contracts)."""
    imported = _spaceplan_imports(ROOT / "pipeline" / "main" / "run_capacity.py")
    assert {"spaceplan.modules.household.main.run_household", "spaceplan.modules.cost.main.contract",
            "spaceplan.modules.lotcap.main.run_lotcap", "spaceplan.modules.site.main.run_site",
            "spaceplan.modules.zoning.main.run_zoning"} <= imported
    assert not {m for m in imported if m.startswith(("spaceplan.modules.cost.lib", "spaceplan.modules.site.lib",
                                                     "spaceplan.modules.zoning.lib",
                                                     "spaceplan.modules.lotcap.lib.flag_lot",
                                                     "spaceplan.modules.lotcap.lib.capacity"))}


def test_visualize_facade_is_gone():
    """Tanda 4 removed the visualize.py facade: code imports the figure file of each topic or viz/main."""
    assert not (ROOT / "modules" / "viz" / "lib" / "visualize.py").exists()


def test_prepare_lot_lives_in_lotcap():
    from spaceplan.modules.lotcap.main.run_lotcap import prepare_lot

    assert prepare_lot.__module__ == "spaceplan.modules.lotcap.main.run_lotcap"


# ------------------------------------------------------------------ executable contracts (refactor tanda 4)

CONTRACT_OWNERS = {"lotcap": "lot_capacity", "site": "site_plan", "household": "program", "cost": "cost_report",
                   "profiles": "program_portfolio", "zoning": "zoning_scheme", "areas": "area_matrix"}


@pytest.mark.parametrize("module", sorted(CONTRACT_OWNERS))
def test_every_producer_has_to_and_from_contract(module):
    import importlib

    contract = importlib.import_module(f"spaceplan.modules.{module}.main.contract")
    assert contract.NAME == CONTRACT_OWNERS[module]
    assert callable(contract.to_contract) and callable(contract.from_contract)
    assert {"NAME", "to_contract", "from_contract"} <= set(contract.__all__)


def test_package_assembly_reads_only_contracts():
    """pipeline/lib/package.py builds the package from the contracts: it imports no module code."""
    imported = _spaceplan_imports(ROOT / "pipeline" / "lib" / "package.py")
    assert imported and all(m == "spaceplan" or m.startswith("spaceplan.core") for m in imported)  # __version__
    assert "spaceplan.core.lib.contracts" in imported


def test_capacity_pipeline_chains_contracts():
    imported = _spaceplan_imports(ROOT / "pipeline" / "main" / "run_capacity.py")
    assert {f"spaceplan.modules.{m}.main.contract" for m in ("lotcap", "site", "zoning", "household", "cost")} <= imported


def test_cost_reads_upstream_contracts_without_their_code():
    """cost consumes lot_capacity, site_plan and program as JSON: no import of lotcap, site or household."""
    for path in (ROOT / "modules" / "cost").rglob("*.py"):
        assert not {_unit(m) for m in _spaceplan_imports(path)} & {"lotcap", "site", "household"}, path


def test_viz_main_draws_from_contracts():
    imported = _spaceplan_imports(ROOT / "modules" / "viz" / "main" / "run_viz.py")
    assert "spaceplan.core.lib.contracts" in imported
    assert {_unit(m) for m in imported} <= {"core", "viz", "lotcap"}
