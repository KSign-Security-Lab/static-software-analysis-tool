"""Core endpoint functions for conversion pipelines."""

import json
import os
import subprocess
from typing import Any, Dict, List, Optional, Set

from ..ast.utils import recursively_get_functions_from_template
from ..ast.validate import validate_ast_results
from ..cpg.generator import CPGGenerator
from ..cpg.validate import validate_cpg_root
from ..dfg.builder import DFGBuilder
from ..template.converter import TemplateConverter
from ..template.extractor import TemplateExtractor
from ..template.planation_tool import PlanationTool
from ..template.post_processor import PostProcessor
from ..types.ast import IASTResult
from ..types.cpg import CPGRoot, TreeNode
from ..types.dfg import IDFGGraph
from ..types.node import TemplateNodes
from ..types.template.BaseNode.base_types import TemplateNodeTypes
from ..utils.path_resolver import get_path, get_validated_path
from ..utils.tree_to_text import TreeToText


def _with_context(fn_name: str, fn):
    """Execute function with error context."""
    try:
        return fn()
    except Exception as err:
        msg = str(err)
        raise RuntimeError(f"{fn_name} failed: {msg}") from err


def _collect_ids_from_flatten(graph) -> List[int]:
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
    planation_tool = PlanationTool([
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
    ])
    tree_to_text = TreeToText(["properties", "line_no", "code"])

    template: List[TreeNode] = _with_context("getTemplateTree", lambda: extractor.get_template_tree(root.get("export", {})))
    converted = _with_context("convertTree", lambda: converter.convert_tree(template))
    template_result: List[TemplateNodes] = _with_context("removeInvalidNodes", lambda: post_processor.remove_invalid_nodes(converted))
    template_result = _with_context("addCodeProperties", lambda: post_processor.add_code_properties(template_result, root))

    text_lines = [tree_to_text.convert(root_node) for root_node in template_result]
    flatten = planation_tool.flatten(template_result)

    if flatten:
        flatten_ids = _collect_ids_from_flatten(flatten[0])
        flatten_unique_ids: Set[int] = set(flatten_ids)
        if len(flatten_ids) != len(flatten_unique_ids):
            duplicates = [id_val for idx, id_val in enumerate(flatten_ids) if flatten_ids.index(id_val) != idx]
            raise RuntimeError(f"Duplicate node ids found in flattened template: {', '.join(map(str, set(duplicates)))}")

    return {
        "template": template,
        "templateResult": template_result,
        "textLines": text_lines,
        "flatten": flatten,
    }


async def generate_cpg(file_path: str, file_type: Optional[str] = None) -> CPGRoot:
    """Generate CPG from a file path."""
    cpg_generator = CPGGenerator()
    cpg_result = await cpg_generator.convert_to_cpg_docker(
        file_path,
        {"filename": file_path, "isFilePath": True} if file_type == "file" else None,
    )
    validate_cpg_root([cpg_result.cpg_data.get("export", {})])
    return cpg_result.cpg_data


def generate_template(cpg: CPGRoot) -> List[TemplateNodes]:
    """Generate template from CPG."""
    validate_cpg_root([cpg.get("export", {})])
    artifacts = _build_template_artifacts(cpg)
    return artifacts["templateResult"]


async def generate_ast(template: List[TemplateNodes]) -> List[IASTResult]:
    """Generate AST from template."""
    if not isinstance(template, list):
        raise ValueError("generate_ast expects a list of TemplateNodes")

    # Resolve absolute path to ASTExtractor.py
    extractor_path = await get_validated_path("AST_EXTRACTOR")

    functions = recursively_get_functions_from_template(template)
    python_exe = os.environ.get("PYTHON_PATH") or os.environ.get("PYTHON", "python3")

    # Create Python code that loads the extractor
    py_code = "\n".join([
        "import sys, json, importlib.util",
        f'mod_path = r"{extractor_path}"',
        "spec = importlib.util.spec_from_file_location('ast_extractor', mod_path)",
        "mod = importlib.util.module_from_spec(spec)",
        "spec.loader.exec_module(mod)",
        "Extractor = getattr(mod, 'ASTExtractorV1_12')",
        f"roots = {json.dumps(functions)}",
        "ast_result = []",
        "for root in roots:",
        "    try:",
        "        ext = Extractor(root)",
        "        ast_result.append(ext.run())",
        "    except Exception as e:",
        "        ast_result.append({'error': str(e)})",
        "print(json.dumps(ast_result, ensure_ascii=False))",
    ])

    # Run Python code
    result = subprocess.run(
        [python_exe, "-u", "-c", py_code],
        capture_output=True,
        text=True,
        timeout=60,
    )

    if result.returncode != 0:
        raise RuntimeError(f"Python AST extraction failed: {result.stderr}")

    output = result.stdout
    if not output or not output.strip():
        raise RuntimeError("Python AST extraction failed: No output received")

    try:
        parsed = json.loads(output)
        graph = validate_ast_results(parsed)
        return graph
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"Invalid JSON from Python AST extractor: {e}. "
            f"Output length: {len(output)}, Output preview: {output[:200]}..."
        )


def generate_dfg(cpg: CPGRoot, asts: List[IASTResult]) -> List[IDFGGraph]:
    """Generate DFG from CPG and AST."""
    validate_cpg_root([cpg.get("export", {})])
    templates = _build_template_artifacts(cpg)
    dfgs: List[IDFGGraph] = []
    for ast in asts:
        dfg_builder = DFGBuilder(cpg, ast, templates["templateResult"][0])
        dfg = dfg_builder.build_dfg_from_cpg()
        dfgs.append(dfg)
    return dfgs


# Use the robust path resolver for consistent path resolution
DFG_EXTRACTOR_PATH = get_path("DFG_EXTRACTOR")
