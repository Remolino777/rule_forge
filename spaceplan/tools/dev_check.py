"""Tiered checks for development (development optimization, 2026-10-09).

    python tools/dev_check.py quick [MODULE ...]   while developing (seconds): tests of the module(s), of the modules
                                                    that consume their contracts, and the architecture / contract /
                                                    doc guards; contract fixtures and module doc checks
    python tools/dev_check.py changed [--base REF] quick for the modules touched since REF (default origin/spaceplan-modular);
                                                    a change in core, data, tools or the pipeline escalates to full
    python tools/dev_check.py full                 when a step closes (CI runs it on every push): the whole suite in
                                                    parallel (pytest-xdist), golden check, fixtures, module doc

Exit code 0 only if every stage passes. Stage times are printed so slow stages are visible.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from spaceplan.core.lib.registry import CONSUMERS, CONTRACT_OF_MODULE, MODULES

GUARDS = ["tests/pipeline/test_architecture.py", "tests/core/test_contracts.py", "tests/pipeline/test_docs.py",
          "tests/pipeline/test_new_module.py"]
FULL_TRIGGERS = ("spaceplan/core/", "spaceplan/data/", "spaceplan/pipeline/", "tools/", "tests/conftest.py",
                 "pyproject.toml")


def _run(label: str, cmd: list[str]) -> bool:
    t0 = time.time()
    print(f"== {label}: {' '.join(cmd)}", flush=True)
    ok = subprocess.run(cmd, cwd=ROOT, check=False).returncode == 0
    print(f"== {label}: {'ok' if ok else 'FAILED'} in {time.time() - t0:.1f} s", flush=True)
    return ok


def _xdist() -> list[str]:
    try:
        import xdist  # noqa: F401
    except ImportError:
        return []
    return ["-n", "auto"]


def test_targets(modules: list[str]) -> list[str]:
    """Test folders of the modules and of the modules that read their contracts (pipeline excluded: full)."""
    unknown = sorted(set(modules) - set(MODULES))
    if unknown:
        raise SystemExit(f"unknown module(s) {unknown}; expected one of {', '.join(MODULES)}")
    targets = set(modules)
    for m in modules:
        contract = CONTRACT_OF_MODULE.get(m)
        targets |= {c for c in CONSUMERS.get(contract, []) if c in MODULES}
    return [f"tests/{m}" for m in MODULES if m in targets and (ROOT / "tests" / m).is_dir()]


def quick(modules: list[str]) -> bool:
    py = sys.executable
    ok = _run("tests", [py, "-m", "pytest", "-q", "-p", "no:cacheprovider", *test_targets(modules), *GUARDS])
    ok &= _run("fixtures", [py, "tools/make_fixtures.py", "check"])
    ok &= _run("module doc", [py, "tools/module_graph.py", "check"])
    return ok


def full() -> bool:
    py = sys.executable
    ok = _run("suite", [py, "-m", "pytest", "-q", "-p", "no:cacheprovider", *_xdist(), "tests"])
    ok &= _run("golden", [py, "tools/golden_check.py", "check"])
    ok &= _run("fixtures", [py, "tools/make_fixtures.py", "check"])
    ok &= _run("module doc", [py, "tools/module_graph.py", "check"])
    return ok


def changed_paths(base: str) -> list[str]:
    out = subprocess.run(["git", "diff", "--name-only", base, "--", "."], cwd=ROOT, capture_output=True, text=True,
                         check=True).stdout.splitlines()
    untracked = subprocess.run(["git", "ls-files", "--others", "--exclude-standard", "."], cwd=ROOT,
                               capture_output=True, text=True, check=True).stdout.splitlines()
    prefix = subprocess.run(["git", "rev-parse", "--show-prefix"], cwd=ROOT, capture_output=True, text=True,
                            check=True).stdout.strip()
    return sorted({p.removeprefix(prefix) for p in out} | set(untracked))


def plan_for(paths: list[str]) -> tuple[str, list[str]]:
    """('full', []) when a shared area changed; else ('quick', modules) from modules/<m>/ and tests/<m>/ paths."""
    if any(p.startswith(FULL_TRIGGERS) for p in paths):
        return "full", []
    modules = set()
    for p in paths:
        parts = p.split("/")
        if p.startswith("spaceplan/modules/") and len(parts) > 2:
            modules.add(parts[2])
        elif p.startswith("tests/") and len(parts) > 1 and parts[1] in MODULES:
            modules.add(parts[1])
    return "quick", sorted(modules & set(MODULES))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="tier", required=True)
    q = sub.add_parser("quick")
    q.add_argument("modules", nargs="*")
    c = sub.add_parser("changed")
    c.add_argument("--base", default="origin/spaceplan-modular")
    sub.add_parser("full")
    args = p.parse_args(argv)
    t0 = time.time()
    if args.tier == "full":
        ok = full()
    elif args.tier == "quick":
        ok = quick(args.modules)
    else:
        tier, modules = plan_for(changed_paths(args.base))
        print(f"== changed since {args.base}: {tier} {' '.join(modules)}")
        ok = full() if tier == "full" else quick(modules)
    print(f"== {'PASSED' if ok else 'FAILED'} ({args.tier}) in {time.time() - t0:.1f} s")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
