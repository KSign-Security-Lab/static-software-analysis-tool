import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Tuple, Union, Optional, Set
import csv
import sys

Json = Union[Dict[str, Any], List[Any], str, int, float, None]

IGNORED_KEYS = {
    # 식별자/표현과 같이 구조 비교에 불필요한(노이즈) 필드들
    "id",
    "name",
    "code",
    "value",
    "size",
    "type",
    "storage",
    "length",
    "returnType",
    "pointingType",
    "elementType",
    "targetType",
}

STRUCTURAL_KEYS = {
    # 구조적으로 의미 있는 키만 제한적으로 사용
    "nodeType",
    "operator",
}


def load_json(path: Path) -> Json:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _normalize_node(obj: Json) -> Any:
    """
    AST 노드를 구조 신원(signature)으로 정규화.
    - dict: nodeType, operator, 그리고 children의 정규화 결과(순서 유지).
    - list: 각 원소의 정규화 결과(순서 유지).
    - primitive: 구조에 영향없음 -> 자리표시자만.
    """
    if isinstance(obj, dict):
        node_type = obj.get("nodeType", None)
        operator = obj.get("operator", None)

        # children은 순서가 중요하니 그대로 순회
        children = obj.get("children", [])
        norm_children = tuple(_normalize_node(ch) for ch in children)

        # 구조를 대표하는 최소한의 정보만 유지
        return ("NODE", node_type, operator, norm_children)

    elif isinstance(obj, list):
        return ("LIST", tuple(_normalize_node(x) for x in obj))

    else:
        # 리터럴/기타 원시값은 구조적으로 구분하지 않음
        return ("LEAF", None)


def signature_from_ast(ast_json: Json) -> str:
    """
    정규화된 구조를 바탕으로 강건한 해시를 생성합니다.
    """
    norm = _normalize_node(ast_json)
    # repr은 결정적 직렬화에 충분 (딥 튜플로만 구성)
    s = repr(norm).encode("utf-8")
    return hashlib.sha256(s).hexdigest()


def has_bad_token(path: Path) -> bool:
    """
    파일명에 'bad' (대소문자 무시)가 포함되는지 확인
    """
    return "bad" in path.stem.lower()


def propose_new_name(path: Path, suffix: str = "_bad_shift") -> Path:
    """
    path.stem 에 suffix를 붙여 충돌 없는 새 파일명을 제안
    (ex: foo.json -> foo_bad_shift.json, 충돌 시 foo_bad_shift(1).json ...)
    """
    parent = path.parent
    stem = path.stem
    ext = path.suffix
    candidate = parent / f"{stem}{suffix}{ext}"
    idx = 1
    while candidate.exists():
        candidate = parent / f"{stem}{suffix}({idx}){ext}"
        idx += 1
    return candidate


def scan_directory(dir_path: Path) -> List[Path]:
    files = [p for p in dir_path.iterdir() if p.is_file()]
    # json 우선 탐색 (그 외 확장자도 허용)
    files.sort()
    return files


def group_by_structure(files: List[Path]) -> Dict[str, List[Path]]:
    groups: Dict[str, List[Path]] = {}
    for p in files:
        try:
            ast_json = load_json(p)
        except Exception as e:
            print(f("[WARN] JSON 로드 실패: {p.name} ({e})"), file=sys.stderr)
            continue
        try:
            sig = signature_from_ast(ast_json)
        except Exception as e:
            print(f("[WARN] 시그니처 생성 실패: {p.name} ({e})"), file=sys.stderr)
            continue
        groups.setdefault(sig, []).append(p)
    return groups


def plan_actions(groups: Dict[str, List[Path]]):
    """
    각 구조 그룹마다 rename 계획 산출.
    반환:
        actions: List[{
           'signature': str,
           'bad_refs': List[Path],
           'to_rename': List[Tuple[Path, Path]]
        }]
    """
    actions = []
    for sig, paths in groups.items():
        if len(paths) < 2:
            # 단독 파일 그룹은 건너뜀
            continue

        bads = [p for p in paths if has_bad_token(p)]
        goods = [p for p in paths if not has_bad_token(p)]

        if bads and goods:
            to_rename = [(g, propose_new_name(g, "_bad_shift")) for g in goods]
            actions.append(
                {"signature": sig, "bad_refs": sorted(bads), "to_rename": to_rename}
            )
    return actions


def compute_stats(all_files: List[Path], actions) -> Dict[str, int]:
    """
    요약 통계 6가지 계산:
      1) 총 파일 수
      2) 변경 전 bad 개수
      3) 변경 전 non-bad 개수
      4) 변경 후 bad 개수
      5) 변경 후 non-bad 개수
      6) 총 변환한 파일 개수
    """
    total = len(all_files)
    pre_bad = sum(1 for p in all_files if has_bad_token(p))
    pre_nonbad = total - pre_bad

    # 중복 방지: 변환 대상 파일 셋
    rename_set: Set[Path] = set(
        old for act in actions for (old, _new) in act["to_rename"]
    )
    converted = len(rename_set)

    post_bad = pre_bad + converted
    post_nonbad = total - post_bad

    return {
        "total": total,
        "pre_bad": pre_bad,
        "pre_nonbad": pre_nonbad,
        "post_bad": post_bad,
        "post_nonbad": post_nonbad,
        "converted": converted,
    }


def format_summary(stats: Dict[str, int]) -> List[str]:
    return [
        "=== 요약 통계 ===",
        f"1) 분석 디렉토리 총 파일 개수: {stats['total']}",
        f"2) 변경 전 bad 네임된 파일 개수: {stats['pre_bad']}",
        f"3) 변경 전 non-bad 네임된 파일 개수: {stats['pre_nonbad']}",
        f"4) 변경 후 bad 네임된 파일 개수: {stats['post_bad']}",
        f"5) 변경 후 non-bad 네임된 파일 개수: {stats['post_nonbad']}",
        f"6) 총 변환한 파일 개수: {stats['converted']}",
        "",
    ]


def print_report(
    actions,
    *,
    csv_path: Optional[Path] = None,
    txt_path: Optional[Path] = None,
    stats: Optional[Dict[str, int]] = None,
):
    lines: List[str] = []

    if stats:
        lines.extend(format_summary(stats))

    lines.append("=== 구조 일치 그룹: 이름 정렬 계획 ===")
    if not actions:
        lines.append("동일 구조이면서 'bad' 유무가 섞인 그룹이 없습니다.")
        text = "\n".join(lines)
        print(text)
        if txt_path is not None:
            try:
                txt_path.write_text(text + "\n", encoding="utf-8")
                print(f"\n텍스트 리포트 저장됨: {txt_path}")
            except Exception as e:
                print(f"[WARN] 텍스트 리포트 저장 실패: {e}", file=sys.stderr)
        return

    for i, act in enumerate(actions, 1):
        lines.append(f"\n[{i}] signature: {act['signature'][:12]}...")
        lines.append("  - 기준(bad 포함) 파일들:")
        for p in act["bad_refs"]:
            lines.append(f"      • {p.name}")

        lines.append("  - 이름 변경 대상(현재 → 변경 후):")
        for old, new in act["to_rename"]:
            lines.append(f"      • {old.name}  →  {new.name}")

    text = "\n".join(lines)
    print(text)

    if csv_path is not None:
        try:
            with csv_path.open("w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["signature", "role", "old_path", "new_path"])
                for act in actions:
                    sig_short = act["signature"][:12]
                    for p in act["bad_refs"]:
                        w.writerow([sig_short, "reference_bad", str(p), ""])
                    for old, new in act["to_rename"]:
                        w.writerow([sig_short, "rename", str(old), str(new)])
            print(f"\nCSV 리포트 저장됨: {csv_path}")
        except Exception as e:
            print(f"[WARN] CSV 리포트 저장 실패: {e}", file=sys.stderr)

    if txt_path is not None:
        try:
            txt_path.write_text(text + "\n", encoding="utf-8")
            print(f"\n텍스트 리포트 저장됨: {txt_path}")
        except Exception as e:
            print(f"[WARN] 텍스트 리포트 저장 실패: {e}", file=sys.stderr)


def apply_actions(actions):
    for act in actions:
        for old, new in act["to_rename"]:
            try:
                os.rename(old, new)
                print(f"[RENAME] {old.name} -> {new.name}")
            except Exception as e:
                print(f"[ERROR] {old} -> {new} 실패: {e}", file=sys.stderr)


def main():
    ap = argparse.ArgumentParser(
        description="AST 구조 동일성 기반 'bad' 이름 정렬 도구"
    )
    ap.add_argument("dir", type=str, help="AST JSON 파일들이 있는 디렉토리")
    ap.add_argument(
        "--apply", action="store_true", help="실제 파일명 변경 수행(기본은 드라이런)"
    )
    ap.add_argument("--report", type=str, default=None, help="CSV 리포트 경로")
    ap.add_argument(
        "--result",
        type=str,
        default=None,
        help="드라이런 텍스트 리포트 파일 경로(기본: <dir>/result.txt)",
    )
    args = ap.parse_args()

    base = Path(args.dir).expanduser().resolve()
    if not base.exists() or not base.is_dir():
        print(f"[ERR] 디렉토리가 존재하지 않음: {base}", file=sys.stderr)
        sys.exit(1)

    files = scan_directory(base)
    if not files:
        print("[INFO] 처리할 파일이 없습니다.")
        return

    groups = group_by_structure(files)
    actions = plan_actions(groups)

    stats = compute_stats(files, actions)

    csv_path = Path(args.report).resolve() if args.report else None
    # 드라이런일 때만 텍스트 리포트 저장
    if not args.apply:
        txt_path = Path(args.result).resolve() if args.result else (base / "result.txt")
    else:
        txt_path = None

    print_report(actions, csv_path=csv_path, txt_path=txt_path, stats=stats)

    if args.apply:
        print("\n--apply 지정됨: 파일명 변경을 수행합니다.")
        apply_actions(actions)
    else:
        print("\n드라이런 모드: --apply 를 주면 실제로 이름을 변경합니다.")


if __name__ == "__main__":
    main()
