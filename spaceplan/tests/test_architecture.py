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
    source = (ROOT / "lib" / "rule_variants.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    literals = {n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, (int, float))}
    assert not literals & {15, 13, 4, 5, 0.08, 0.6, 0.59, 24, 30, 50, 100, 150}


def test_no_crc_numbers_in_program_review():
    tree = ast.parse((ROOT / "lib" / "program_review.py").read_text(encoding="utf-8"))
    literals = {n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, (int, float))}
    assert not literals & {70, 7, 0.08, 0.04}
