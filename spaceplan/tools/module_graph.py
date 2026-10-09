"""Generate docs/architecture/modules.md from the code (refactor tanda 4).

    python tools/module_graph.py write    # regenerate the document
    python tools/module_graph.py check    # exit 1 if the document is out of date (tests/pipeline/test_docs.py)

The module graph is read from the imports of the real files (AST, deferred imports included); the contract table
from contracts/schemas and spaceplan.core.lib.contracts. Only the "how to add a module" section is fixed text.
"""

from __future__ import annotations

import ast
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "spaceplan"
DOC = ROOT / "docs" / "architecture" / "modules.md"
MODULES = ("lotcap", "site", "household", "cost", "profiles", "zoning", "areas", "stacking", "viz")
ORDER = ("core", *MODULES, "pipeline")


def _unit(dotted: str) -> str | None:
    parts = dotted.split(".")
    if len(parts) < 2 or parts[0] != "spaceplan":
        return None
    if parts[1] == "modules":
        return parts[2] if len(parts) > 2 else None
    return parts[1] if parts[1] in ("core", "pipeline") else None


def _files() -> list[Path]:
    return [p for p in sorted(PACKAGE.rglob("*.py")) if len(p.relative_to(PACKAGE).parts) > 1]


def _dotted(path: Path) -> str:
    return ".".join(("spaceplan", *path.relative_to(PACKAGE).with_suffix("").parts))


def _imports(path: Path) -> set[str]:
    names = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return {n for n in names if n.startswith("spaceplan.")}


def module_edges() -> dict[tuple[str, str], int]:
    """(from module, to module) -> number of importing files."""
    edges: Counter = Counter()
    for path in _files():
        src = _unit(_dotted(path))
        for dst in {_unit(m) for m in _imports(path)} - {None, src}:
            edges[(src, dst)] += 1
    return dict(edges)


def module_files() -> dict[str, dict[str, list[str]]]:
    out: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    for path in _files():
        if path.stem == "__init__":
            continue
        parts = _dotted(path).split(".")
        unit = _unit(_dotted(path))
        layer = parts[3] if parts[1] == "modules" else parts[2]
        out[unit][layer].append(path.stem)
    return out


def _contracts() -> list[dict]:
    sys.path.insert(0, str(ROOT))
    from spaceplan.core.lib.contracts import CONSUMERS, CONTRACT_VERSION, PRODUCERS
    from spaceplan.core.lib.schema_validation import CONTRACTS, load_contract_schema

    rows = []
    for name in CONTRACTS:
        schema = load_contract_schema(name)
        blocks = [k for k in schema["required"] if k not in ("contract", "version", "produced_by", "input_sha256")]
        optional = [k for k in schema["properties"] if k not in schema["required"]
                    and k not in ("consumers", "brief_id")]
        rows.append({"name": name, "producer": PRODUCERS[name], "consumers": CONSUMERS[name], "blocks": blocks,
                     "optional": optional, "version": CONTRACT_VERSION})
    return rows


HOW_TO_ADD = """## Cómo agregar un módulo (p. ej. `stacking`, paso 6.7)

1. Crear `spaceplan/modules/<m>/{__init__,main/__init__,lib/__init__,lib_aux/__init__}.py`: `lib/` funciones de
   dominio, `lib_aux/` utilidades sin dominio, `main/` el workflow del módulo.
2. Declarar sus dependencias permitidas en `ALLOWED` de `tests/pipeline/test_architecture.py` (el grafo debe seguir
   siendo acíclico) y sus archivos en `test_files_follow_plan_table`.
3. Escribir su contrato: `spaceplan/contracts/schemas/<contrato>.schema.json` (Draft 2020-12, sobre común,
   bloques por `$ref` al paquete o al brief cuando existan), agregarlo a `CONTRACTS`
   (`core/lib/schema_validation.py`) y a `PRODUCERS`/`CONSUMERS` (`core/lib/contracts.py`).
4. `modules/<m>/main/contract.py` con `NAME`, `to_contract(...)` (usa `make_contract`, que valida) y
   `from_contract(contract)` (usa `read_contract`). Serializar como el paquete: `package_json` para los bloques que
   el paquete redondea, `plain_json` para los que lleva tal cual.
5. Componerlo en `pipeline/main/` (nunca desde el `main/` de otro módulo); si alimenta el paquete, leerlo con
   `read_contract` en `pipeline/lib/package.py`.
6. CLI: subcomando en `pipeline/main/cli.py` que lea y escriba el contrato.
7. Pruebas en `tests/<m>/` con contratos fijos en `tests/<m>/fixtures/` (agregar el caso a
   `tools/make_fixtures.py`, que los verifica contra la instantánea dorada).
8. Regenerar este documento: `python tools/module_graph.py write`.
"""


def render() -> str:
    edges = module_edges()
    files = module_files()
    lines = ["# Arquitectura modular de `spaceplan`", "",
             "> Documento **generado** por `python tools/module_graph.py write` desde las importaciones del código y",
             "> los esquemas de contratos; `tests/pipeline/test_docs.py` falla si queda desactualizado.", "",
             "## Grafo de módulos (importaciones reales)", "",
             "Cada flecha `A --> B` significa que algún archivo de A importa B (el número es la cantidad de archivos).",
             "", "```mermaid", "graph LR"]
    for (src, dst), n in sorted(edges.items(), key=lambda e: (ORDER.index(e[0][0]), ORDER.index(e[0][1]))):
        lines.append(f"    {src} -->|{n}| {dst}")
    lines += ["```", "", "| Módulo | Importa | Importado por |", "|---|---|---|"]
    for unit in ORDER:
        out = sorted({d for s, d in edges if s == unit}, key=ORDER.index)
        into = sorted({s for s, d in edges if d == unit}, key=ORDER.index)
        lines.append(f"| `{unit}` | {', '.join(out) or '—'} | {', '.join(into) or '—'} |")
    lines += ["", "## Archivos por módulo y capa", "", "| Módulo | `main/` | `lib/` | `lib_aux/` |", "|---|---|---|---|"]
    for unit in ORDER:
        layers = files.get(unit, {})
        cells = [", ".join(f"`{n}`" for n in sorted(layers.get(layer, []))) or "—" for layer in ("main", "lib", "lib_aux")]
        lines.append(f"| `{unit}` | {' | '.join(cells)} |")
    contracts = _contracts()
    lines += ["", f"## Contratos (versión {contracts[0]['version']})", "",
              "Sobre común: `contract`, `version`, `produced_by`, `input_sha256` (SHA-256 de las entradas que leyó el",
              "productor), `brief_id` y `consumers` (informativos). Esquemas en `spaceplan/contracts/schemas/`.", "",
              "| Contrato | Produce | Consumen | Bloques obligatorios | Opcionales |", "|---|---|---|---|---|"]
    for c in contracts:
        lines.append(f"| `{c['name']}` | `{c['producer']}` | {', '.join(c['consumers'])} | "
                     f"{', '.join(f'`{b}`' for b in c['blocks'])} | {', '.join(f'`{b}`' for b in c['optional']) or '—'} |")
    lines += ["", "Cada productor tiene `modules/<m>/main/contract.py` con `to_contract` (valida al producir) y",
              "`from_contract` (valida al leer). El `pipeline` arma el paquete solo desde los contratos",
              "(`pipeline/lib/package.py:package_from_contracts`), `cost` lee `lot_capacity`, `site_plan` y `program`",
              "como JSON y `viz` dibuja desde los contratos.", "", HOW_TO_ADD]
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    mode = argv[1] if len(argv) > 1 else "check"
    text = render()
    if mode == "write":
        DOC.parent.mkdir(parents=True, exist_ok=True)
        DOC.write_text(text, encoding="utf-8")
        print(f"wrote {DOC.relative_to(ROOT)}")
        return 0
    ok = DOC.exists() and DOC.read_text(encoding="utf-8") == text
    print("MODULE DOC", "UP TO DATE" if ok else "OUT OF DATE")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
