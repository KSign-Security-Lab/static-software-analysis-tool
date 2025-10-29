#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
convertor.py

JSON 형태의 AST에서 nodeType == "FunctionDefinition"인 함수 서브트리만 분리해
개별 JSON 파일로 저장하는 스크립트.

추가 기능:
- 함수 서브트리 내 "내부 노드"(children이 비어있지 않은 노드) 개수가 threshold 이하(기본 5)이면 저장 PASS.
  * 내부 노드 수는 함수 루트(FunctionDefinition)는 제외.
  * leaves(자식이 없는 노드)는 제외.

파일명 규칙(기존 convertor.py와 동일):
- 함수명(name)이 존재하고 길이 ≤ 15면: <원본파일base>_<함수명>.json
  * 원본파일명이 *_templateTree.json 이면 base에서 '_templateTree' 제거
- 그 외(이름이 없거나 길이 > 15): <함수명 or anonymous_function>.json
- 이름 충돌 시 _1, _2... 를 덧붙여 저장

로그 저장:
- 터미널에 출력되는 모든 로그를 동시에 --output 폴더의 result.txt 파일에도 기록합니다.
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
    콘솔 + 파일(result.txt)에 동시에 INFO 레벨 로그를 남기는 로거 설정.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    log_path = out_dir / "result.txt"

    logger = logging.getLogger("convertor")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()  # 중복 방지

    # 콘솔 출력
    sh = logging.StreamHandler(sys.stdout)
    sh.setLevel(logging.INFO)
    sh.setFormatter(logging.Formatter("%(message)s"))

    # 파일 출력 (덮어쓰기)
    fh = logging.FileHandler(log_path, mode="w", encoding="utf-8")
    fh.setLevel(logging.INFO)
    fh.setFormatter(logging.Formatter("%(message)s"))

    logger.addHandler(sh)
    logger.addHandler(fh)
    return logger


# ----- Core -----
def iter_function_defs(root: Dict[str, Any]) -> Iterable[Dict[str, Any]]:
    """DFS로 순회하며 nodeType == 'FunctionDefinition' 인 노드들을 yield."""
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
    """자식이 없는 노드면 leaf로 간주."""
    children = node.get("children")
    return not children or (isinstance(children, list) and len(children) == 0)


def count_internal_nodes(
    subtree_root: Dict[str, Any], exclude_root: bool = True
) -> int:
    """
    서브트리 내부에서 children이 있는 노드(= 내부 노드) 개수.
    기본적으로 루트(FunctionDefinition)는 제외(exclude_root=True).
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
    기존 convertor.py 파일명 규칙 구현:
      - func_name이 있고 len(func_name) <= 15 이면: <src_base>_<func_name>.json
        (src_base는 src_path.stem에서 '_templateTree' 접미사를 제거한 값)
      - 그 외: <func_name>.json (func_name이 없으면 'anonymous_function')
    """
    name = (func_name or "").strip() or "anonymous_function"
    stem = src_path.stem
    base = stem[: -len("_templateTree")] if stem.endswith("_templateTree") else stem

    if func_name and len(name) <= 15:
        return f"{base}_{name}.json"
    else:
        return f"{name}.json"


def ensure_unique_path(out_dir: Path, filename: str) -> Path:
    """동일 파일명이 존재하면 _1, _2... 접미사를 붙여 충돌 회피."""
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
    하나의 JSON 파일 처리.
    반환: (found, saved, skipped)
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
    """입력이 파일이면 그대로, 디렉터리면 하위의 .json 파일들을 재귀 수집."""
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

    # 로거 준비 (여기서 out_dir 생성 + result.txt 경로 확정)
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
