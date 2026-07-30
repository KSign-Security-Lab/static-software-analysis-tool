"""Stage orchestration for the SSAT analysis pipeline.

The chain is::

    source -> CPG -> template -> per-function AST -> per-function def-use DFG

:func:`analyze_cpg` is the primary entry point: AST and DFG are produced together
because the DFG is derived from the AST, and every consumer wants both.
:func:`training_record` renders one function into the JSON schema the GNN dataset
loader (``agent.dataset.JsonDataset``) reads.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Sequence, Set, TypeVar, cast

from ..ast.extractor import ASTExtractor
from ..ast.validate import validate_ast_results
from ..cpg.backends import EmbeddedBackend, get_backend
from ..cpg.validate import validate_cpg_root
from ..dfg.extractor import DFGExtractor
from ..template.converter import TemplateConverter
from ..template.extractor import TemplateExtractor
from ..template.planation_tool import PlanationTool
from ..template.post_processor import PostProcessor
from ..types.ast import IASTResult
from ..types.cpg import CPGRoot, TreeNode
from ..types.node import TemplateNodes
from ..types.template import TemplateFlattenedGraph
from ..types.template.BaseNode.base_types import TemplateNodeTypes
from ..utils import get_functions_from_template
from ..utils.tree_to_text import TreeToText

#: In-process Joern by default -- no Docker daemon or container required.
DEFAULT_BACKEND = EmbeddedBackend.name


T = TypeVar("T")


def _with_context(fn_name: str, fn: Callable[[], T]) -> T:
    """Run a stage, tagging any failure with which stage it was."""
    try:
        return fn()
    except Exception as err:
        msg = str(err)
        raise RuntimeError(f"{fn_name} failed: {msg}") from err


def _collect_ids_from_flatten(graph: TemplateFlattenedGraph) -> List[int]:
    """Collect IDs from flattened graph."""
    ids: List[int] = []
    for node in graph.get("nodes", []):
        node_id = node.get("id")
        if isinstance(node_id, int):
            ids.append(node_id)
    return ids


def _build_template_artifacts(root: CPGRoot) -> Dict[str, Any]:
    """Build template artifacts from CPG root."""
    extractor = TemplateExtractor()
    converter = TemplateConverter()
    post_processor = PostProcessor()
    planation_tool = PlanationTool(
        [
            TemplateNodeTypes.VariableDeclaration,
            TemplateNodeTypes.ArrayDeclaration,
            TemplateNodeTypes.PointerDeclaration,
            TemplateNodeTypes.ParameterDeclaration,
            TemplateNodeTypes.AssignmentExpression,
            TemplateNodeTypes.FunctionDeclaration,
            TemplateNodeTypes.FunctionDefinition,
            TemplateNodeTypes.StandardLibCall,
            TemplateNodeTypes.UserDefinedCall,
            TemplateNodeTypes.CastExpression,
            TemplateNodeTypes.MemberAccess,
            TemplateNodeTypes.PointerDereference,
            TemplateNodeTypes.AddressOfExpression,
            TemplateNodeTypes.ArraySubscriptExpression,
            TemplateNodeTypes.BinaryExpression,
            TemplateNodeTypes.UnaryExpression,
            TemplateNodeTypes.SizeOfExpression,
            TemplateNodeTypes.Identifier,
            TemplateNodeTypes.Literal,
        ]
    )
    tree_to_text = TreeToText(["properties", "line_no", "code"])

    export_data = root.get("export", {})
    template: List[TreeNode] = _with_context("getTemplateTree", lambda: extractor.get_template_tree(export_data))
    converted = _with_context("convertTree", lambda: converter.convert_tree(template))
    template_result: List[TemplateNodes] = _with_context(
        "removeInvalidNodes", lambda: post_processor.remove_invalid_nodes(converted)
    )
    root_data = cast(CPGRoot, dict(root))
    template_result = _with_context(
        "addCodeProperties", lambda: post_processor.add_code_properties(template_result, root_data)
    )

    text_lines = [tree_to_text.convert(root_node) for root_node in template_result]
    flatten = planation_tool.flatten(template_result)

    if flatten:
        flatten_ids = _collect_ids_from_flatten(flatten[0])
        flatten_unique_ids: Set[int] = set(flatten_ids)
        if len(flatten_ids) != len(flatten_unique_ids):
            duplicates = [id_val for idx, id_val in enumerate(flatten_ids) if flatten_ids.index(id_val) != idx]
            raise RuntimeError(
                f"Duplicate node ids found in flattened template: {', '.join(map(str, set(duplicates)))}"
            )

    return {
        "template": template,
        "templateResult": template_result,
        "textLines": text_lines,
        "flatten": flatten,
    }


def generate_cpg(
    source: str,
    *,
    backend: str = DEFAULT_BACKEND,
    filename: str = "main.c",
    representation: str = "all",
) -> CPGRoot:
    """Generate a validated CPG document from source text.

    ``backend`` is ``"jpype"`` (in-process) or ``"docker"``; see
    :mod:`ssat.cpg.backends`. Returns the ``{"export": ...}`` shape the rest of
    the pipeline consumes.
    """
    result = get_backend(backend).generate(source, filename=filename, representation=representation)
    validate_cpg_root([result.graphson])
    return CPGRoot(export=result.graphson)


def generate_cpg_from_file(
    file_path: str | Path,
    *,
    backend: str = DEFAULT_BACKEND,
    representation: str = "all",
) -> CPGRoot:
    """Generate a validated CPG document from a source file on disk."""
    path = Path(file_path)
    return generate_cpg(
        path.read_text(encoding="utf-8", errors="replace"),
        backend=backend,
        filename=path.name,
        representation=representation,
    )


def generate_template(cpg: CPGRoot) -> List[TemplateNodes]:
    """Generate template from CPG."""
    export_data = cpg.get("export", {})
    validate_cpg_root([export_data])
    artifacts = _build_template_artifacts(cpg)
    result: List[TemplateNodes] = artifacts["templateResult"]
    return result


@dataclass
class FunctionGraphs:
    """AST and def-use DFG for one function, plus where it came from."""

    name: str
    ast: Dict[str, Any]
    dfg: Dict[str, Any]
    code: str = ""
    source: str = ""
    template: Dict[str, Any] = field(default_factory=dict)


def _template_functions(template: Sequence[Mapping[str, Any]], skip_main: bool) -> List[Dict[str, Any]]:
    """Function definitions with a body, in template order.

    Uses the general extractor, not the Juliet-specific
    :func:`ssat.ast.utils.get_juliet_benchmark_functions`.
    """
    functions = [
        f
        for f in get_functions_from_template(template)
        if f.get("nodeType") == "FunctionDefinition" and f.get("children")
    ]
    if skip_main:
        functions = [f for f in functions if f.get("name") != "main"]
    return functions


def analyze_template(
    template: List[TemplateNodes], *, source: str = "", skip_main: bool = True
) -> List[FunctionGraphs]:
    """Extract AST and def-use DFG for every function in a template.

    The DFG is derived from the AST, so the two are always produced together --
    computing them separately would mean walking the template twice and risks
    the halves drifting out of sync.
    """
    if not isinstance(template, list):
        raise ValueError("analyze_template expects a list of TemplateNodes")

    results: List[FunctionGraphs] = []
    for function in _template_functions(template, skip_main):
        ast_result = ASTExtractor(function).run()
        dfg_result = DFGExtractor(function, ast_result, sink_mode="k1").run()
        results.append(
            FunctionGraphs(
                name=function.get("name", ""),
                ast=ast_result,
                dfg=dfg_result,
                code=function.get("code", ""),
                source=source,
                template=function,
            )
        )
    return results


def analyze_cpg(cpg: CPGRoot, *, source: str = "", skip_main: bool = True) -> List[FunctionGraphs]:
    """Run the whole chain: CPG -> template -> per-function AST + DFG."""
    return analyze_template(generate_template(cpg), source=source, skip_main=skip_main)


def generate_ast(template: List[TemplateNodes]) -> List[IASTResult]:
    """AST for every function in a template.

    Was ``async`` and returned nothing on non-Juliet code; both were incidental.
    """
    return validate_ast_results([fg.ast for fg in analyze_template(template)])


def generate_dfg(template: List[TemplateNodes]) -> List[Dict[str, Any]]:
    """Def-use DFG for every function in a template.

    Previously this took ``(cpg, asts)`` and ran ``DFGBuilder``, which projected
    CPG ``REF`` edges rather than tracking memory reads and writes -- and passed
    ``templateResult[0]`` for every AST regardless of which function it belonged
    to. Both are gone; this is the def-use analysis the GNN consumes.
    """
    return [fg.dfg for fg in analyze_template(template)]


def training_record(
    graphs: FunctionGraphs,
    *,
    include_template: bool = True,
    include_label: bool = False,
) -> Dict[str, Any]:
    """Render one function into the schema ``agent.dataset.JsonDataset`` reads.

    The loader looks for top-level ``ast`` and ``dfg`` keys
    (``juliet_json_to_sample``). The CLI's old ``full`` mode wrote
    ``ast_result``/``dfg_result`` instead, so its output was silently unreadable
    by the trainer.

    ``include_label`` defaults to False on purpose: ``_infer_label_from_json``
    treats an explicit ``label`` as highest priority and otherwise falls back to
    filename heuristics. Emitting a name-derived label by default would silently
    relabel any dataset whose ground truth lives in the *filename* rather than
    the function name.
    """
    record: Dict[str, Any] = {
        "source_template": graphs.source,
        "function_name": graphs.name,
        "ast": graphs.ast,
        "dfg": graphs.dfg,
        "code": graphs.code,
    }
    if include_template:
        record["template"] = graphs.template
    if include_label:
        record["label"] = 1 if "bad" in graphs.name.lower() else 0
    return record
