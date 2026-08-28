#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
convertor.py

A script to extract function subtrees with nodeType == "FunctionDefinition" from a JSON-formatted AST 
and save them as individual JSON files.

Additional Features:
- Skips saving if the number of "internal nodes" (nodes with non-empty children) in the function subtree is below a threshold (default 5).
  * The root node (FunctionDefinition) is excluded from the internal node count.
  * Leaves (nodes without children) are also excluded.

Filename Rules (same as the original convertor.py):
- If the function name (name) exists and length <= 15: <original_file_base>_<function_name>.json
  * If the original filename is *_templateTree.json, '_templateTree' is removed from the base.
- Otherwise (no name or length > 15): <function_name or anonymous_function>.json
- Appends _1, _2... if name conflicts occur.

Logging:
- All logs printed to the terminal are simultaneously recorded in the result.txt file in the --output folder.
"""

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple, Iterable


# ----- Logger -----
def setup_logger(out_dir: Path) -> logging.Logger:
    """
    Setup logger to record INFO level logs simultaneously to console and file (result.txt).
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    log_path = out_dir / "result.txt"

    logger = logging.getLogger("convertor")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()  # prevent duplicates

    # console output
    sh = logging.StreamHandler(sys.stdout)
    sh.setLevel(logging.INFO)
    sh.setFormatter(logging.Formatter("%(message)s"))

    # file output (overwrite)
    fh = logging.FileHandler(log_path, mode="w", encoding="utf-8")
    fh.setLevel(logging.INFO)
    fh.setFormatter(logging.Formatter("%(message)s"))

    logger.addHandler(sh)
    logger.addHandler(fh)
    return logger


# ----- Core -----
def iter_function_defs(root: Dict[str, Any]) -> Iterable[Dict[str, Any]]:
    """DFS traversal to yield nodes with nodeType == 'FunctionDefinition'."""
    stack = [root]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            if node.get("nodeType") == "FunctionDefinition":
                yield node
            children = node.get("children") or []
            if isinstance(children, list):
                stack.extend(children)
        elif isinstance(node, list):
            stack.extend(node)


def is_leaf(node: Dict[str, Any]) -> bool:
    """Consider node as leaf if it has no children."""
    children = node.get("children")
    return not children or (isinstance(children, list) and len(children) == 0)


def count_internal_nodes(
    subtree_root: Dict[str, Any], exclude_root: bool = True
) -> int:
    """
    Count of nodes with children (= internal nodes) within the subtree.
    By default, the root (FunctionDefinition) is excluded (exclude_root=True).
    """
    count = 0
    stack = [subtree_root]
    first = True
    while stack:
        node = stack.pop()
        if not isinstance(node, dict):
            continue
        if first and exclude_root:
            first = False
        else:
            if not is_leaf(node):
                count += 1
        children = node.get("children") or []
        if isinstance(children, list):
            stack.extend(children)
    return count


def derive_output_name_original_rule(src_path: Path, func_name: str) -> str:
    """
    Implementation of original convertor.py filename rules:
      - If func_name exists and len(func_name) <= 15: <src_base>_<func_name>.json
        (src_base is src_path.stem with '_templateTree' suffix removed)
      - Otherwise: <func_name>.json (defaults to 'anonymous_function' if no func_name)
    """
    name = (func_name or "").strip() or "anonymous_function"
    stem = src_path.stem
    base = stem[: -len("_templateTree")] if stem.endswith("_templateTree") else stem

    if func_name and len(name) <= 15:
        return f"{base}_{name}.json"
    else:
        return f"{name}.json"


def ensure_unique_path(out_dir: Path, filename: str) -> Path:
    """Avoid collisions by appending _1, _2... if the filename already exists."""
    candidate = out_dir / filename
    if not candidate.exists():
        return candidate
    stem = candidate.stem
    suffix = candidate.suffix
    i = 1
    while True:
        cand = out_dir / f"{stem}_{i}{suffix}"
        if not cand.exists():
            return cand
        i += 1


def save_json(obj: Dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def process_one_file(
    src_path: Path, out_dir: Path, threshold: int, logger: logging.Logger
) -> Tuple[int, int, int]:
    """
    Process a single JSON file.
    Returns: (found, saved, skipped)
    """
    try:
        with src_path.open("r", encoding="utf-8") as f:
            root = json.load(f)
    except Exception as e:
        logger.info(f"[ERROR] Failed to load JSON: {src_path} - {e}")
        return (0, 0, 0)

    found = saved = skipped = 0
    for func in iter_function_defs(root):
        found += 1
        func_name = func.get("name") or "anonymous_function"
        internal_cnt = count_internal_nodes(func, exclude_root=True)

        if internal_cnt <= threshold:
            skipped += 1
            logger.info(
                f"[PASS] {src_path.name} :: {func_name} (internal_nodes={internal_cnt} ≤ {threshold})"
            )
            continue

        filename = derive_output_name_original_rule(src_path, func_name)
        # Remove leading "~" if any
        if filename.startswith("~"):
            filename = filename.lstrip("~")
        dst = ensure_unique_path(out_dir, filename)
        save_json(func, dst)
        saved += 1
        logger.info(f"[SAVE] {dst} (internal_nodes={internal_cnt})")

    return (found, saved, skipped)


def collect_json_files(input_path: Path) -> List[Path]:
    """Collect .json files recursively if input is a directory, otherwise return the file path itself."""
    if input_path.is_file():
        return [input_path]
    files: List[Path] = []
    for p in input_path.rglob("*.json"):
        if p.is_file():
            files.append(p)
    return sorted(files)


def main():
    parser = argparse.ArgumentParser(
        description="Extract FunctionDefinition nodes into separate JSON files, skipping small subtrees (<= threshold internal nodes)."
    )
    parser.add_argument(
        "--input", "-i", required=True, type=str, help="Input JSON file or directory"
    )
    parser.add_argument(
        "--output",
        "-o",
        default="./Convert",
        type=str,
        help="Output directory (default: ./Convert)",
    )
    parser.add_argument(
        "--threshold",
        "-t",
        default=5,
        type=int,
        help="Skip saving if function subtree INTERNAL node count (excluding root) is <= threshold (default: 5)",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    out_dir = Path(args.output)
    threshold = int(args.threshold)

    # Setup logger (creates out_dir + confirms result.txt path)
    logger = setup_logger(out_dir)

    files = collect_json_files(input_path)
    if not files:
        logger.info(f"[WARN] No JSON files found under: {input_path}")
        return

    total_found = total_saved = total_skipped = 0
    for fp in files:
        found, saved, skipped = process_one_file(fp, out_dir, threshold, logger)
        total_found += found
        total_saved += saved
        total_skipped += skipped

    logger.info("=" * 60)
    logger.info(f"Files processed : {len(files)}")
    logger.info(f"Functions found : {total_found}")
    logger.info(f"Saved           : {total_saved}")
    logger.info(f"Skipped (≤{threshold}) : {total_skipped}")
    logger.info("=" * 60)
    logger.info(f"Results saved to: {out_dir / 'result.txt'}")


if __name__ == "__main__":
    main()
