"""Scaffold a new stage module and its contract (development optimization, 2026-10-09).

    python tools/new_module.py NAME --contract CONTRACT [--deps core,areas] [--consumers viz,pipeline]
                               [--title "Step 6.8 ..."] [--dry-run]

Writes, following the rules of docs/architecture/modules.md:
  spaceplan/modules/NAME/{__init__, main/__init__, lib/__init__, lib_aux/__init__}.py
  spaceplan/modules/NAME/main/run_NAME.py        workflow stub returning {"meta": ...}
  spaceplan/modules/NAME/main/contract.py        NAME, to_contract, from_contract
  spaceplan/contracts/schemas/CONTRACT.schema.json   envelope + meta (add the module's blocks)
  tests/NAME/test_NAME_contract.py               schema, round trip, registry
and registers the module, its allowed imports and its contract in spaceplan/core/lib/registry.py (the single
registry every list derives from). Then: compose it in pipeline/main, add the CLI command, add a fixture in
tools/make_fixtures.py and run `python tools/module_graph.py write`.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")
MODULES_RE = re.compile(r'(MODULES: tuple\[str, \.\.\.\] = \()([^)]*)(\))')
ALLOWED_MARK = "    # new modules above this line"
CONTRACT_MARK = "    # new contracts above this line"


def registry_path(root: Path) -> Path:
    return root / "spaceplan" / "core" / "lib" / "registry.py"


def read_registry(root: Path) -> dict:
    """Load registry.py from `root` in isolation (it imports nothing) and return its names."""
    spec = importlib.util.spec_from_file_location("_scaffold_registry", registry_path(root))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return vars(module)


def _wrap(items: list[str], indent: int, width: int = 100) -> str:
    """Comma-joined items wrapped under the opening parenthesis (ruff line length)."""
    lines, line = [], ""
    for item in items:
        piece = item if not line else f", {item}"
        if line and indent + len(line) + len(piece) + 2 > width:
            lines.append(line + ",")
            line = item
        else:
            line += piece
    lines.append(line)
    return ("\n" + " " * indent).join(lines)


def registry_text(text: str, name: str, contract: str, deps: list[str], consumers: list[str]) -> str:
    """registry.py with the new module (before viz, which stays last), its imports and its contract."""
    m = MODULES_RE.search(text)
    if m is None or ALLOWED_MARK not in text or CONTRACT_MARK not in text:
        raise SystemExit("registry.py markers not found: edit it by hand")
    names = [n.strip().strip('"') for n in m.group(2).split(",") if n.strip()]
    at = names.index("viz") if "viz" in names else len(names)
    names.insert(at, name)
    text = text[:m.start()] + m.group(1) + _wrap([f'"{n}"' for n in names], len(m.group(1))) + m.group(3) \
        + text[m.end():]
    deps_text = ", ".join(f'"{d}"' for d in deps)
    text = text.replace(ALLOWED_MARK, f'    "{name}": {{{deps_text}}},\n{ALLOWED_MARK}', 1)
    consumers_text = ", ".join(f'"{c}"' for c in consumers)
    return text.replace(CONTRACT_MARK,
                        f'    "{contract}": {{"producer": "{name}", "consumers": [{consumers_text}]}},\n{CONTRACT_MARK}', 1)


def schema(contract: str, name: str, title: str) -> dict:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"https://municipal-permit-intelligence/spaceplan/contracts/{contract}/0.2.0",
        "title": title,
        "description": f"Output of the {name} module (scaffolded; add the module's blocks).",
        "type": "object",
        "additionalProperties": False,
        "required": ["contract", "version", "produced_by", "input_sha256", "meta"],
        "properties": {
            "contract": {"const": contract},
            "version": {"type": "string", "pattern": "^[0-9]+\\.[0-9]+\\.[0-9]+$"},
            "produced_by": {"const": name},
            "input_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$",
                             "description": "SHA-256 (canonical JSON) of the inputs the producer read."},
            "brief_id": {"type": ["string", "null"], "description": "Brief the contract belongs to (informative)."},
            "consumers": {"type": "array", "items": {"type": "string"}, "description": "Informative."},
            "meta": {"type": "object", "required": ["step"], "properties": {"step": {"type": "string"}}},
        },
    }


def files(name: str, contract: str, title: str) -> dict[str, str]:
    """Relative path -> content of every new file."""
    pkg = f"spaceplan/modules/{name}"
    return {
        f"{pkg}/__init__.py": f'"""{title}."""\n',
        f"{pkg}/main/__init__.py": f'"""Workflow of the {name} module."""\n',
        f"{pkg}/lib/__init__.py": f'"""Domain functions of the {name} module."""\n',
        f"{pkg}/lib_aux/__init__.py": f'"""Domain-free helpers of the {name} module."""\n',
        f"{pkg}/main/run_{name}.py": f'''"""Workflow of the {name} module ({title}).

    upstream contracts -> ... -> result {{meta, ...}} (contract {contract})

Reads contracts only (spaceplan.core.lib.contracts.read_contract); domain code goes in lib/, domain-free helpers in
lib_aux/. Normative numbers live in data/rules, design parameters in a catalog, never in the code.
"""

from __future__ import annotations

from typing import Any

STEP = "{title.split()[1] if title.lower().startswith("step ") else "0.0"}"


def run_{name}(**inputs: Any) -> dict[str, Any]:
    """Scaffold: replace with the module workflow."""
    return {{"meta": {{"step": STEP}}}}


__all__ = ["STEP", "run_{name}"]
''',
        f"{pkg}/main/contract.py": f'''"""Contract of the {name} module: `{contract}`.

    to_contract(result, inputs)   run_{name} result -> {contract}, validated
    from_contract(contract)       validated blocks for the consumers
"""

from __future__ import annotations

from spaceplan.core.lib.contracts import make_contract, package_json, read_contract

NAME = "{contract}"


def to_contract(result: dict, inputs=None) -> dict:
    return make_contract(NAME, result["meta"] if inputs is None else inputs, package_json(result))


def from_contract(contract: dict) -> dict:
    return read_contract(contract, NAME)


__all__ = ["NAME", "from_contract", "to_contract"]
''',
        f"spaceplan/contracts/schemas/{contract}.schema.json": json.dumps(schema(contract, name, title), indent=2)
        + "\n",
        f"tests/{name}/test_{name}_contract.py": f'''"""{name} module through its contract `{contract}` (scaffolded by tools/new_module.py)."""

from spaceplan.core.lib.contracts import contract_problems
from spaceplan.core.lib.registry import ALLOWED_IMPORTS, CONTRACT_OF_MODULE, MODULES
from spaceplan.modules.{name}.main.contract import from_contract, to_contract
from spaceplan.modules.{name}.main.run_{name} import run_{name}


def test_module_is_registered():
    assert "{name}" in MODULES and CONTRACT_OF_MODULE["{name}"] == "{contract}"
    assert "core" in ALLOWED_IMPORTS["{name}"]


def test_contract_validates_and_round_trips():
    contract = to_contract(run_{name}())
    assert contract_problems(contract, "{contract}") == []
    assert from_contract(contract)["meta"] == contract["meta"]
''',
    }


def scaffold(root: Path, name: str, contract: str, deps: list[str], consumers: list[str], title: str,
             dry_run: bool = False) -> list[Path]:
    if not NAME_RE.match(name) or not NAME_RE.match(contract):
        raise SystemExit("module and contract names must be snake_case identifiers")
    reg = read_registry(root)
    if name in reg["MODULES"] or name in ("core", "pipeline"):
        raise SystemExit(f"module {name!r} already exists")
    if contract in reg["CONTRACTS"]:
        raise SystemExit(f"contract {contract!r} already exists")
    unknown = set(deps) - {"core", *reg["MODULES"]}
    if unknown or "core" not in deps:
        raise SystemExit(f"--deps must include core and only existing modules (unknown: {sorted(unknown)})")
    new = files(name, contract, title)
    clashes = [p for p in new if (root / p).exists()]
    if clashes:
        raise SystemExit(f"files already exist: {clashes}")
    reg_file = registry_path(root)
    reg_new = registry_text(reg_file.read_text(encoding="utf-8"), name, contract, deps, consumers)
    written = [root / p for p in new] + [reg_file]
    if dry_run:
        return written
    for rel, content in new.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    reg_file.write_text(reg_new, encoding="utf-8")
    return written


NEXT_STEPS = """next:
  1. domain code in lib/, workflow in main/run_{name}.py, blocks in contracts/schemas/{contract}.schema.json
  2. compose it in spaceplan/pipeline/main/run_modules.py ({contract}_contract_for) and add the CLI command
  3. fixture: tools/make_fixtures.py, then `python tools/make_fixtures.py write`
  4. `python tools/module_graph.py write`; quick tests: `python tools/dev_check.py quick {name}`"""


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("name")
    p.add_argument("--contract", required=True)
    p.add_argument("--deps", default="core", help="comma list of modules it may import (core required)")
    p.add_argument("--consumers", default="viz,pipeline", help="comma list of modules that read the contract")
    p.add_argument("--title", help="one-line description, e.g. 'Step 6.8 common quality score'")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args(argv)
    split = lambda s: [x.strip() for x in s.split(",") if x.strip()]
    title = args.title or f"Module {args.name}"
    written = scaffold(ROOT, args.name, args.contract, split(args.deps), split(args.consumers), title, args.dry_run)
    print(("would write" if args.dry_run else "wrote") + "\n  " + "\n  ".join(str(w.relative_to(ROOT)) for w in written))
    print(NEXT_STEPS.format(name=args.name, contract=args.contract))
    return 0


if __name__ == "__main__":
    sys.exit(main())
