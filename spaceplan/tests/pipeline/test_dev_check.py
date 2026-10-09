"""tools/dev_check.py: which tier and which tests a change needs (dev optimization)."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

from dev_check import plan_for
from dev_check import test_targets as targets_for


def test_module_changes_stay_quick():
    assert plan_for(["spaceplan/modules/stacking/lib/levels.py", "tests/stacking/test_x.py"]) == ("quick", ["stacking"])
    assert plan_for(["spaceplan/modules/areas/lib/area_matrix.py", "HANDOFF_spaceplan.md"]) == ("quick", ["areas"])


def test_shared_changes_escalate_to_full():
    for path in ("spaceplan/core/lib/registry.py", "spaceplan/data/rules/x.json", "spaceplan/pipeline/main/cli.py",
                 "tools/golden_check.py", "tests/conftest.py"):
        assert plan_for([path]) == ("full", [])


def test_targets_include_contract_consumers():
    assert targets_for(["areas"]) == ["tests/areas", "tests/stacking", "tests/viz"]
    assert targets_for(["stacking"]) == ["tests/stacking", "tests/viz"]
