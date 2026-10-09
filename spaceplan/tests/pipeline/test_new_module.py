"""tools/new_module.py: scaffolding a module writes valid files and one registry entry (dev optimization)."""

import ast
import json
import shutil
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

from new_module import read_registry, scaffold


@pytest.fixture()
def root(tmp_path):
    reg = tmp_path / "spaceplan" / "core" / "lib" / "registry.py"
    reg.parent.mkdir(parents=True)
    shutil.copy(ROOT / "spaceplan" / "core" / "lib" / "registry.py", reg)
    return tmp_path


def test_scaffold_writes_files_and_registers(root):
    written = scaffold(root, "scoring", "quality_score", ["core", "areas", "stacking"], ["viz", "pipeline"],
                       "Step 6.8 common quality score")
    rel = {str(p.relative_to(root)) for p in written}
    assert "spaceplan/modules/scoring/main/contract.py" in rel
    assert "spaceplan/contracts/schemas/quality_score.schema.json" in rel
    assert "tests/scoring/test_scoring_contract.py" in rel
    for path in written:
        if path.suffix == ".py":
            ast.parse(path.read_text(encoding="utf-8"))
    schema = json.loads((root / "spaceplan/contracts/schemas/quality_score.schema.json").read_text())
    Draft202012Validator.check_schema(schema)
    assert schema["properties"]["produced_by"] == {"const": "scoring"}
    assert 'STEP = "6.8"' in (root / "spaceplan/modules/scoring/main/run_scoring.py").read_text()
    reg = read_registry(root)
    assert reg["MODULES"][-2:] == ("scoring", "viz")  # inserted before viz, which stays last
    assert reg["ALLOWED_IMPORTS"]["scoring"] == {"core", "areas", "stacking"}
    assert "scoring" in reg["ALLOWED_IMPORTS"]["pipeline"]
    assert reg["PRODUCERS"]["quality_score"] == "scoring" and reg["CONSUMERS"]["quality_score"] == ["viz", "pipeline"]
    assert list(reg["CONTRACTS"])[-1] == "quality_score"


def test_scaffold_dry_run_writes_nothing(root):
    before = (root / "spaceplan/core/lib/registry.py").read_text()
    written = scaffold(root, "scoring", "quality_score", ["core"], ["viz"], "Module scoring", dry_run=True)
    assert written and not any(p.exists() for p in written if p.name != "registry.py")
    assert (root / "spaceplan/core/lib/registry.py").read_text() == before


@pytest.mark.parametrize("name, contract, deps, message", [
    ("stacking", "x_plan", ["core"], "already exists"),
    ("scoring", "area_matrix", ["core"], "already exists"),
    ("scoring", "quality_score", ["areas"], "--deps"),
    ("scoring", "quality_score", ["core", "nope"], "--deps"),
    ("Scoring", "quality_score", ["core"], "snake_case"),
])
def test_scaffold_rejects_bad_requests(root, name, contract, deps, message):
    with pytest.raises(SystemExit, match=message):
        scaffold(root, name, contract, deps, ["viz"], "Module x")
