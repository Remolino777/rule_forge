"""Single registry of modules and contracts (development optimization, 2026-10-09).

Every list of modules or contracts in the code, the tests and the tools derives from here, so adding a module is one
entry (written by `python tools/new_module.py`). Imports nothing: core, tests and tools all read it.

    MODULES             stage modules in pipeline order (core and pipeline are not stage modules)
    ALLOWED_IMPORTS     module -> modules it may import (acyclic; checked by tests/pipeline/test_architecture.py)
    CONTRACTS           contract -> {"producer": module, "consumers": [modules]}
"""

from __future__ import annotations

MODULES: tuple[str, ...] = ("lotcap", "site", "household", "cost", "profiles", "zoning", "areas", "stacking", "viz")

ALLOWED_IMPORTS: dict[str, set[str]] = {  # plan 3.2: module -> modules it may import (besides itself)
    "core": set(),
    "lotcap": {"core"},
    "household": {"core"},
    "cost": {"core"},
    "site": {"core", "lotcap"},
    "profiles": {"core", "household", "cost"},
    "zoning": {"core", "lotcap", "site"},
    "areas": {"core", "lotcap", "site", "household", "cost", "profiles"},
    "stacking": {"core", "lotcap", "site", "cost", "zoning", "areas"},  # step 6.7 (S0 uses core only)
    "viz": {"core", "lotcap"},  # contracts, plus lotcap types to draw the lot
    # new modules above this line (tools/new_module.py inserts here)
    "pipeline": {"core", *MODULES},
}

CONTRACTS: dict[str, dict] = {
    "lot_capacity": {"producer": "lotcap", "consumers": ["site", "zoning", "areas", "cost", "viz", "pipeline"]},
    "site_plan": {"producer": "site", "consumers": ["zoning", "areas", "cost", "viz", "pipeline"]},
    "program": {"producer": "household", "consumers": ["profiles", "zoning", "cost", "pipeline"]},
    "cost_report": {"producer": "cost", "consumers": ["profiles", "areas", "pipeline"]},
    "program_portfolio": {"producer": "profiles", "consumers": ["areas", "viz"]},
    "zoning_scheme": {"producer": "zoning", "consumers": ["viz", "pipeline"]},
    "area_matrix": {"producer": "areas", "consumers": ["viz", "stacking"]},
    "stack_plan": {"producer": "stacking", "consumers": ["viz", "pipeline"]},
    # new contracts above this line (tools/new_module.py inserts here)
}

CONTRACT_NAMES: tuple[str, ...] = tuple(CONTRACTS)
PRODUCERS: dict[str, str] = {name: c["producer"] for name, c in CONTRACTS.items()}
CONSUMERS: dict[str, list[str]] = {name: list(c["consumers"]) for name, c in CONTRACTS.items()}
CONTRACT_OF_MODULE: dict[str, str] = {m: name for name, m in PRODUCERS.items()}

__all__ = ["ALLOWED_IMPORTS", "CONSUMERS", "CONTRACTS", "CONTRACT_NAMES", "CONTRACT_OF_MODULE", "MODULES",
           "PRODUCERS"]
