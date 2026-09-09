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
    return sorted(CPG_FIXTURES.glob("*.json"))


def _load_cpg(cpg_path: Path) -> Dict[str, Any]:
    return {"export": json.loads(cpg_path.read_text(encoding="utf-8"))}


def _as_dicts(nodes: List[Any]) -> List[Dict[str, Any]]:
    return [n if isinstance(n, dict) else n.model_dump() for n in nodes]


def build_template(cpg_path: Path) -> List[Dict[str, Any]]:
    from ssat.pipeline import generate_template

    with contextlib.redirect_stdout(io.StringIO()):
        return _as_dicts(generate_template(_load_cpg(cpg_path)))


def function_names(template: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    from ssat.ast.utils import get_juliet_benchmark_functions
    from ssat.utils import get_functions_from_template

    return {
        "unfiltered": [f.get("name", "") for f in get_functions_from_template(template)],
        "filtered": [f.get("name", "") for f in get_juliet_benchmark_functions(template)],
    }


def build_graphs(cpg_path: Path) -> Dict[str, Any]:
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
    return GOLDEN_DIR / f"{cpg_path.name.removesuffix('.json')}.golden.json"


def dump(snapshot: Dict[str, Any]) -> str:
    return json.dumps(snapshot, indent=2, sort_keys=True, default=str) + "\n"
