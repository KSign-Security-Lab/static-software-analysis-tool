from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Sequence, Set, TypeVar, cast

from ..ast.extractor import ASTExtractor
from ..ast.validate import validate_ast_results
from ..cpg.backends import EmbeddedBackend
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


T = TypeVar("T")


def _with_context(fn_name: str, fn: Callable[[], T]) -> T:
    try:
        return fn()
    except Exception as err:
        msg = str(err)
        raise RuntimeError(f"{fn_name} failed: {msg}") from err


def _collect_ids_from_flatten(graph: TemplateFlattenedGraph) -> List[int]:
    ids: List[int] = []
    for node in graph.get("nodes", []):
        node_id = node.get("id")
        if isinstance(node_id, int):
            ids.append(node_id)
    return ids


def _build_template_artifacts(root: CPGRoot, *, replace_macro: bool = True) -> Dict[str, Any]:
    extractor = TemplateExtractor()
    converter = TemplateConverter(replace_macro=replace_macro)
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
    filename: str = "main.c",
    representation: str = "all",
) -> CPGRoot:
    result = EmbeddedBackend().generate(source, filename=filename, representation=representation)
    validate_cpg_root([result.graphson])
    return CPGRoot(export=result.graphson)


def generate_cpg_from_file(
    file_path: str | Path,
    *,
    representation: str = "all",
) -> CPGRoot:
    path = Path(file_path)
    return generate_cpg(
        path.read_text(encoding="utf-8", errors="replace"),
        filename=path.name,
        representation=representation,
    )


def generate_template(cpg: CPGRoot, *, replace_macro: bool = True) -> List[TemplateNodes]:
    export_data = cpg.get("export", {})
    validate_cpg_root([export_data])
    artifacts = _build_template_artifacts(cpg, replace_macro=replace_macro)
    result: List[TemplateNodes] = artifacts["templateResult"]
    return result


@dataclass
class FunctionGraphs:
    name: str
    ast: Dict[str, Any]
    dfg: Dict[str, Any]
    code: str = ""
    source: str = ""
    template: Dict[str, Any] = field(default_factory=dict)


def _template_functions(template: Sequence[Mapping[str, Any]], skip_main: bool) -> List[Dict[str, Any]]:
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


def analyze_cpg(
    cpg: CPGRoot, *, source: str = "", skip_main: bool = True, replace_macro: bool = True
) -> List[FunctionGraphs]:
    return analyze_template(generate_template(cpg, replace_macro=replace_macro), source=source, skip_main=skip_main)


def generate_ast(template: List[TemplateNodes]) -> List[IASTResult]:
    return validate_ast_results([fg.ast for fg in analyze_template(template)])


def generate_dfg(template: List[TemplateNodes]) -> List[Dict[str, Any]]:
    return [fg.dfg for fg in analyze_template(template)]


def training_record(
    graphs: FunctionGraphs,
    *,
    include_template: bool = True,
    include_label: bool = False,
) -> Dict[str, Any]:
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
