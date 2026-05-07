"""Graph processing package for SSAT."""

import json
import argparse
from pathlib import Path
from typing import List, Dict, Any

from utils import (
    get_functions_from_template,
    recursively_get_json_files,
)
from .dfg import DFGExtractor
from .ast import ASTExtractor


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Extract AST and DFG from template files.")
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


def _sanitize_filename(name: str, fallback: str, max_len: int = 120) -> str:
    """Make a filesystem-safe component; fallback used if name is empty after sanitization."""
    import re
    safe_chars = re.compile(r"[^A-Za-z0-9._-]+")
    cleaned = safe_chars.sub("_", name or "")
    cleaned = cleaned.strip("._-")
    if not cleaned:
        cleaned = safe_chars.sub("_", fallback or "fn")
    return cleaned[:max_len]


def _to_markdown(code: str, ast_obj: Any, dfg_obj: Any) -> str:
    """Render a Notion-friendly markdown section with Code, AST (json), and DFG (json)."""
    code_str = code if isinstance(code, str) else ""
    ast_json = json.dumps(ast_obj, ensure_ascii=False, indent=2)
    dfg_json = json.dumps(dfg_obj, ensure_ascii=False, indent=2)

    return f"""### Code
```c
{code_str}
```

### AST
```json
{ast_json}
```

### DFG
```json
{dfg_json}
```
"""


def process_dfg_file(
    template_path: Path, data_root: Path, save_root: Path, emit_md: bool, keep_name: bool
) -> None:
    """
    Process a single template JSON and emit one result JSON per function.
    """
    with template_path.open("r", encoding="utf-8") as f:
        template_json = json.load(f)

    if isinstance(template_json, list):
        functions = get_functions_from_template(template_json)
    else:
        functions = get_functions_from_template([template_json])

    rel_path = template_path.relative_to(data_root)
    input_stem = template_path.stem

    out_dir = save_root / rel_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)

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
            out_base = out_dir / f"{input_stem}{suffix}"
        else:
            out_base = out_dir / f"{input_stem}__{safe_fn}{suffix}"

        # Extract AST & DFG for this single function
        ast_ext = ASTExtractor(function)
        ast_result = ast_ext.run()

        dfg_ext = DFGExtractor(function, ast_result, sink_mode="k1")
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
        out_json = out_base.with_suffix(".dfg.json")
        with out_json.open("w", encoding="utf-8") as wf:
            json.dump(payload, wf, ensure_ascii=False, indent=2)

        # Optionally write Notion-friendly Markdown
        if emit_md:
            md_text = _to_markdown(
                payload.get("code", ""), payload["ast"], payload["dfg"]
            )
            out_md = out_base.with_suffix(".md")
            with out_md.open("w", encoding="utf-8") as mf:
                mf.write(md_text)


def dfg() -> None:
    """Main entry point for DFG extraction CLI."""
    args = parse_args()
    data_root = Path(args.data)
    save_root = Path(args.save)
    template_files = recursively_get_json_files(data_root)

    print(f"Input root: {data_root}")
    print(f"Found {len(template_files)} template file(s)")
    print(f"Output root: {save_root}")
    print(f"Emit Markdown: {args.emit_md}")
    print(f"Keep original name: {args.keep_name}")

    for template in template_files:
        process_dfg_file(template, data_root, save_root, args.emit_md, args.keep_name)


if __name__ == "__main__":
    dfg()
