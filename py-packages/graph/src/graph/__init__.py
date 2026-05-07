import os
import re
import json
import argparse
from pathlib import Path
from typing import List, Dict, Any

from utils import (
    recursivelyGetFunctionsFromTemplate,
    recursvely_get_json_files,
)
from .dfg import DFGExtractorV1_12
from .ast import ASTExtractorV1_12


def arg_parser() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--data",
        type=str,
        required=True,
        help="Directory containing input template JSON files.",
    )
    parser.add_argument(
        "--save",
        type=str,
        default="results",
        help="Output directory for generated files.",
    )
    parser.add_argument(
        "--emit-md",
        action="store_true",
        help="If set, also emit a Notion-friendly Markdown file per extracted function.",
    )
    parser.add_argument(
        "--keep-name",
        action="store_true",
        help="If set, keep original filename structure. If false, append function name to filename.",
    )
    return parser.parse_args()


_SAFE_CHARS = re.compile(r"[^A-Za-z0-9._-]+")


def _sanitize_filename(name: str, fallback: str, maxlen: int = 120) -> str:
    """Make a filesystem-safe component; fallback used if name is empty after sanitization."""
    cleaned = _SAFE_CHARS.sub("_", name or "")
    cleaned = cleaned.strip("._-")
    if not cleaned:
        cleaned = _SAFE_CHARS.sub("_", fallback or "fn")
    return cleaned[:maxlen]


def _to_markdown(code: str, ast_obj: Any, dfg_obj: Any) -> str:
    """Render a Notion-friendly markdown section with Code, AST (json), and DFG (json)."""
    # Ensure code is a string (fall back to empty)
    code_str = code if isinstance(code, str) else ""
    ast_json = json.dumps(ast_obj, ensure_ascii=False, indent=2)
    dfg_json = json.dumps(dfg_obj, ensure_ascii=False, indent=2)

    parts = []
    parts.append("### Code")
    parts.append("```c")
    parts.append(code_str)
    parts.append("```")
    parts.append("")
    parts.append("### AST")
    parts.append("```json")
    parts.append(ast_json)
    parts.append("```")
    parts.append("")
    parts.append("### DFG")
    parts.append("```json")
    parts.append(dfg_json)
    parts.append("```")
    parts.append("")

    return "\n".join(parts)


def process_dfg_file(
    template_path: str, data_root: str, save_root: str, emit_md: bool, keep_name: bool
) -> None:
    """
    Process a single template JSON and emit one result JSON per function,
    preserving directory structure relative to data_root. Optionally emit Markdown.
    """
    with open(template_path, "r", encoding="utf-8") as f:
        template_json = json.load(f)

    if isinstance(template_json, list):
        functions = recursivelyGetFunctionsFromTemplate(template_json)
    else:
        functions = recursivelyGetFunctionsFromTemplate([template_json])

    rel_path = os.path.relpath(template_path, data_root)
    rel_dir = os.path.dirname(rel_path)
    input_stem = Path(template_path).stem

    out_dir = os.path.join(save_root, rel_dir)
    os.makedirs(out_dir, exist_ok=True)

    # Track duplicates of function names for uniqueness
    name_counts: Dict[str, int] = {}

    for idx, function in enumerate(functions):
        fn_name = function.get("name") or f"function_{idx}"
        if fn_name == "main":
            continue
        safe_fn = _sanitize_filename(fn_name, fallback=f"function_{idx}")

        # de-duplicate if the same function name appears multiple times
        n = name_counts.get(safe_fn, 0)
        name_counts[safe_fn] = n + 1
        suffix = f"_{n}" if n > 0 else ""

        # Build output file base path (without extension)
        if keep_name:
            # Keep original filename structure
            out_base = os.path.join(out_dir, f"{input_stem}{suffix}")
        else:
            # Append function name to filename (current behavior)
            out_base = os.path.join(out_dir, f"{input_stem}__{safe_fn}{suffix}")

        # Extract AST & DFG for this single function
        ast_ext = ASTExtractorV1_12(function)
        ast_result = ast_ext.run()

        dfg_ext = DFGExtractorV1_12(function, ast_result, sink_mode="k1")
        dfg_result = dfg_ext.run()

        payload = {
            "source_template": str(rel_path),
            "function_name": fn_name,
            "ast": ast_result,
            "dfg": dfg_result,
            "code": function.get("code", ""),
            "template": function,
        }

        # Write JSON
        out_json = f"{out_base}.dfg.json"
        with open(out_json, "w", encoding="utf-8") as wf:
            json.dump(payload, wf, ensure_ascii=False, indent=2)

        # Optionally write Notion-friendly Markdown
        if emit_md:
            md_text = _to_markdown(
                payload.get("code", ""), payload["ast"], payload["dfg"]
            )
            out_md = f"{out_base}.md"
            with open(out_md, "w", encoding="utf-8") as mf:
                mf.write(md_text)


def dfg() -> None:
    args = arg_parser()
    template_files = recursvely_get_json_files(args.data)

    # Basic visibility in CLI runs
    print(f"Input root: {args.data}")
    print(f"Found {len(template_files)} template file(s)")
    print(f"Output root: {args.save}")
    print(f"Emit Markdown: {args.emit_md}")
    print(f"Keep original name: {args.keep_name}")

    for template in template_files:
        process_dfg_file(template, args.data, args.save, args.emit_md, args.keep_name)


if __name__ == "__main__":
    dfg()
