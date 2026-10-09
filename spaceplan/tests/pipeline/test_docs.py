"""docs/architecture/modules.md is generated from the code (refactor tanda 4) and must stay up to date."""

import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[2] / "tools"


def test_module_document_is_up_to_date():
    sys.path.insert(0, str(TOOLS))
    try:
        import module_graph
    finally:
        sys.path.remove(str(TOOLS))
    assert module_graph.DOC.read_text(encoding="utf-8") == module_graph.render(), \
        "run: python tools/module_graph.py write"


def test_document_graph_has_no_forbidden_edge():
    sys.path.insert(0, str(TOOLS))
    try:
        import module_graph
    finally:
        sys.path.remove(str(TOOLS))
    edges = module_graph.module_edges()
    assert ("core", "pipeline") not in edges and not any(src == "core" for src, _ in edges)
    assert not any(dst == "pipeline" for src, dst in edges)
