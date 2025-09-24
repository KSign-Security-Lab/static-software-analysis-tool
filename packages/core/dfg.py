import json
import os
import sys
from pathlib import Path

# Make imports resilient whether run as module or directly
_here = Path(__file__).resolve()
_core_dir = _here.parent
_packages_dir = _core_dir.parent
_repo_root = _packages_dir.parent

for p in {str(_packages_dir), str(_core_dir), str(_repo_root)}:
    if p not in sys.path:
        sys.path.append(p)

# Prefer fully-qualified package imports to avoid stdlib 'ast' shadowing
try:
    from core.ast.ASTExtractor import ASTExtractorV1_12  # type: ignore
except Exception:
    try:
        from ast.ASTExtractor import ASTExtractorV1_12  # type: ignore
    except Exception:
        from ASTExtractor import ASTExtractorV1_12  # type: ignore

# DFG extractor may live in different locations in this repo; try a few
try:
    from core.__tests__.DFGExtractor import DFGExtractorV1_12  # type: ignore
except Exception:
    try:
        from dfg.DFGExtractor import DFGExtractorV1_12  # type: ignore
    except Exception as _e:
        raise ImportError(
            "Could not import DFGExtractorV1_12. Ensure it exists (e.g., core/__tests__/DFGExtractor.py) "
            "or adjust the import path in packages/core/dfg.py."
        ) from _e


class FuncGraph:
    def __init__(self, ast_path: Path, label: int, sink_mode: str = "k1"):
        with open(ast_path, "r", encoding="utf-8") as f:
            ast_json = json.load(f)

        # Some template files are arrays with a single TranslationUnit at index 0
        if isinstance(ast_json, list):
            if len(ast_json) == 0:
                raise ValueError(f"Empty template file: {ast_path}")
            ast_json = ast_json[0]

        # If 조건식에서 atoi/strtol 같은 부작용 없는 파서 호출까지 리프팅하고 싶을 때만 LIFT_PURE_COND_CALLS를 True로 설정하세요\
        # 기본은 False(리프팅 대상: ext_input/mem_copy/mem_set/net_* 등 부작용 있는 API).
        # ast_ext = ASTExtractorV1_12(ast_json, lift_pure_cond_calls=True)

        ast_ext = ASTExtractorV1_12(ast_json)
        ast_result = ast_ext.run()

        # out_path = "ast_result.json"
        # with open(out_path, "w", encoding="utf-8") as f:
        #    json.dump(ast_result, f, ensure_ascii=False, indent=2)

        dfg_ext = DFGExtractorV1_12(ast_json, ast_result, sink_mode=sink_mode)
        dfg_result = dfg_ext.run()
        self.ast_result = ast_result
        self.dfg_result = dfg_result
        self.label = label


# ----------------------------
# main()
# ----------------------------
def _preprocess_template_file(file_path: str):
    with open(file_path, "r", encoding="utf-8") as f:
        ast_json = json.load(f)
    if isinstance(ast_json, list):
        if not ast_json:
            raise ValueError(f"Empty template file: {file_path}")
        ast_json = ast_json[0]
    return ast_json


def _recursively_get_functions(node):
    functions = []
    if isinstance(node, dict):
        node_type = node.get("nodeType") or node.get("type")
        if node_type in ("FunctionDeclaration", "FunctionDefinition"):
            functions.append(node)
        children = node.get("children")
        if isinstance(children, list):
            for child in children:
                functions.extend(_recursively_get_functions(child))
    elif isinstance(node, list):
        for item in node:
            functions.extend(_recursively_get_functions(item))
    return functions


def main(template_dir: str, output_root: str = "../../data/dfg-python"):
    template_dir = os.path.abspath(template_dir)
    output_root = os.path.abspath(output_root)

    json_files = []
    for root, _dirs, filenames in os.walk(template_dir):
        for name in filenames:
            # Only process template JSON files
            if name.endswith("_template.json"):
                json_files.append(os.path.join(root, name))

    for file_path in json_files:
        ast_json = _preprocess_template_file(file_path)
        function_nodes = _recursively_get_functions(ast_json)

        dfg_results = []
        # If no explicit functions found, fall back to whole AST
        targets = function_nodes if function_nodes else [ast_json]
        for func_node in targets:
            ast_ext = ASTExtractorV1_12(func_node)
            ast_result = ast_ext.run()
            dfg_ext = DFGExtractorV1_12(func_node, ast_result, sink_mode="k1")
            dfg_results.append(dfg_ext.run())

        rel_path = os.path.relpath(file_path, template_dir)
        out_path = os.path.join(output_root, rel_path)
        base, _ext = os.path.splitext(out_path)
        save_path = base + "_dfg.json"

        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        with open(save_path, "w", encoding="utf-8") as f:
            json.dump(dfg_results, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    template_dir = "../../data/template"
    output_root = "../../data/dfg-python"
    main(template_dir, output_root)
