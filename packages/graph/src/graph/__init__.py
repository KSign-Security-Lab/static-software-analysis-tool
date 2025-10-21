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
    parser.add_argument("--data", type=str, required=True)
    parser.add_argument("--save", type=str, default="results")
    return parser.parse_args()


_SAFE_CHARS = re.compile(r"[^A-Za-z0-9._-]+")


def _sanitize_filename(name: str, fallback: str, maxlen: int = 120) -> str:
    """Make a filesystem-safe component; fallback used if name is empty after sanitization."""
    cleaned = _SAFE_CHARS.sub("_", name or "")
    cleaned = cleaned.strip("._-")
    if not cleaned:
        cleaned = _SAFE_CHARS.sub("_", fallback or "fn")
    return cleaned[:maxlen]


def process_dfg_file(template_path: str, data_root: str, save_root: str) -> None:
    """
    Process a single template JSON and emit one result JSON per function,
    preserving directory structure relative to data_root.
    """
    with open(template_path, "r", encoding="utf-8") as f:
        template_json = json.load(f)

    functions: List[Dict[str, Any]] = recursivelyGetFunctionsFromTemplate(template_json)

    rel_path = os.path.relpath(template_path, data_root)
    rel_dir = os.path.dirname(rel_path)
    input_stem = Path(template_path).stem

    out_dir = os.path.join(save_root, rel_dir)
    os.makedirs(out_dir, exist_ok=True)

    # Track duplicates of function names for uniqueness
    name_counts: Dict[str, int] = {}

    for idx, function in enumerate(functions):
        fn_name = function.get("name") or f"function_{idx}"
        safe_fn = _sanitize_filename(fn_name, fallback=f"function_{idx}")

        # de-duplicate if the same function name appears multiple times
        n = name_counts.get(safe_fn, 0)
        name_counts[safe_fn] = n + 1
        suffix = f"_{n}" if n > 0 else ""

        # Build output file path
        out_file = os.path.join(
            out_dir, f"{input_stem}__{idx:04d}__{safe_fn}{suffix}.dfg.json"
        )

        # Extract AST & DFG for this single function
        ast_ext = ASTExtractorV1_12(function)
        ast_result = ast_ext.run()

        dfg_ext = DFGExtractorV1_12(function, ast_result, sink_mode="k1")
        dfg_result = dfg_ext.run()

        payload = {
            "source_template": str(rel_path),
            "function_index": idx,
            "function_name": fn_name,
            "ast": ast_result,
            "dfg": dfg_result,
        }

        with open(out_file, "w", encoding="utf-8") as wf:
            json.dump(payload, wf, ensure_ascii=False, indent=2)


def dfg() -> None:
    args = arg_parser()
    template_files = recursvely_get_json_files(args.data)
    print(args.data)
    print(len(template_files))

    for template in template_files:
        process_dfg_file(template, args.data, args.save)
