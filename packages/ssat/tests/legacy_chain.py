"""The legacy (pre-F2-A) analysis chain, expressed as one callable.

This module exists to pin down what the legacy pipeline *currently* does, so the
refactor can move and delete code without silently changing behaviour. It is
imported by ``test_characterization.py`` and by ``generate_golden.py``.

The chain is::

    CPG (GraphSON)
      -> generate_template          ssat.pipeline
      -> get_functions_from_template  ssat.utils   (unfiltered)
      -> ASTExtractor.run()         per function
      -> DFGExtractor.run()         per function

Note the function-extraction step deliberately uses the *unfiltered* helper from
``ssat.utils``. The other helper, ``ssat.ast.utils.get_juliet_benchmark_functions``,
additionally requires the function name to match ``bad|good|sink`` -- a filter
specific to the Juliet benchmark that drops every function in real-world code.
Both are recorded by :func:`function_names` so the refactor can see the gap.
"""

from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
from typing import Any, Dict, List

TESTS_DIR = Path(__file__).parent
CPG_FIXTURES = TESTS_DIR / "fixtures" / "f2a" / "cpg"
JAVA_FIXTURE = TESTS_DIR / "fixtures" / "java" / "Sample.json"
GOLDEN_DIR = TESTS_DIR / "golden" / "legacy"


def all_fixtures() -> List[Path]:
    """Every CPG fixture, sorted for deterministic test ordering.

    All of them convert. Four used to raise -- any assignment with an
    ``<operator>.alloc`` child crashed ``TemplateConverter`` because its GraphSON
    unwrapper returned the property list rather than the scalar inside it. Fixed
    by :meth:`TemplateConverter._unwrap_graphson_scalar`.
    """
    return sorted(CPG_FIXTURES.glob("*.json"))


def _load_cpg(cpg_path: Path) -> Dict[str, Any]:
    """Wrap a raw GraphSON document in the ``{"export": ...}`` shape the
    pipeline layer expects."""
    return {"export": json.loads(cpg_path.read_text(encoding="utf-8"))}


def _as_dicts(nodes: List[Any]) -> List[Dict[str, Any]]:
    """Normalise pydantic models and TypedDicts to plain dicts."""
    return [n if isinstance(n, dict) else n.model_dump() for n in nodes]


def build_template(cpg_path: Path) -> List[Dict[str, Any]]:
    """Run CPG -> template. Silences the pipeline's debug prints."""
    from ssat.pipeline import generate_template

    with contextlib.redirect_stdout(io.StringIO()):
        return _as_dicts(generate_template(_load_cpg(cpg_path)))


def function_names(template: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    """Names found by each of the two function-extraction helpers.

    The ``filtered`` list is what ``generate_ast`` used to see before the
    refactor made it use the general extractor;
    it is empty for any code that does not follow Juliet naming.
    """
    from ssat.ast.utils import get_juliet_benchmark_functions
    from ssat.utils import get_functions_from_template

    return {
        "unfiltered": [f.get("name", "") for f in get_functions_from_template(template)],
        "filtered": [f.get("name", "") for f in get_juliet_benchmark_functions(template)],
    }


def build_graphs(cpg_path: Path) -> Dict[str, Any]:
    """Run the whole chain and return a JSON-serialisable snapshot.

    Only ``FunctionDefinition`` nodes with a body are analysed; declarations
    have nothing for the extractors to walk.
    """
    from ssat.ast.extractor import ASTExtractor
    from ssat.dfg.extractor import DFGExtractor
    from ssat.utils import get_functions_from_template

    template = build_template(cpg_path)
    functions = [
        f
        for f in get_functions_from_template(template)
        if f.get("nodeType") == "FunctionDefinition" and f.get("children")
    ]

    snapshot: Dict[str, Any] = {
        "template_root_count": len(template),
        "function_names": function_names(template),
        "functions": [],
    }

    for function in functions:
        # The extractors print debug lines to stdout; keep the snapshot clean.
        with contextlib.redirect_stdout(io.StringIO()):
            ast_result = ASTExtractor(function).run()
            dfg_result = DFGExtractor(function, ast_result, sink_mode="k1").run()
        snapshot["functions"].append(
            {
                "name": function.get("name", ""),
                "ast": ast_result,
                "dfg": dfg_result,
            }
        )

    return snapshot


def golden_path(cpg_path: Path) -> Path:
    """Where the snapshot for a given fixture lives."""
    return GOLDEN_DIR / f"{cpg_path.name.removesuffix('.json')}.golden.json"


def dump(snapshot: Dict[str, Any]) -> str:
    """Stable serialisation: sorted keys so diffs are meaningful."""
    return json.dumps(snapshot, indent=2, sort_keys=True, default=str) + "\n"
