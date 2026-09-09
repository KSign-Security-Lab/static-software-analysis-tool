from __future__ import annotations

import re
from collections import defaultdict, deque
from fnmatch import fnmatch
from typing import Iterable, Literal, Mapping, Sequence

from ..languages import spec_for_path
from .chunk import FILE_CHUNK_KIND, Chunk
from .links import CALLS, Link

State = Literal["live", "unreferenced", "unreachable", "excluded", "unknown"]
DEFAULT_ENTRY_SYMBOLS: tuple[str, ...] = ("main", "wmain", "WinMain", "_start")
EXCLUDED_PARTS: frozenset[str] = frozenset(
    {"test", "tests", "testing", "spec", "specs", "fixture", "fixtures", "mock", "mocks", "example", "examples",
     "sample", "samples", "bench", "benchmarks", "generated", "gen", "__tests__"}
)

EXCLUDED_STEMS: tuple[str, ...] = ("test_", "_test", "_spec", ".test", ".spec", "_pb2", ".pb", "_generated")


def _is_excluded(path: str) -> bool:
    lowered = path.lower()
    parts = lowered.split("/")
    if any(part in EXCLUDED_PARTS for part in parts[:-1]):
        return True
    name = parts[-1]
    return any(marker in name for marker in EXCLUDED_STEMS)


def _declaration(chunk: Chunk) -> str:
    for line in chunk.body.splitlines():
        if line.strip():
            return line
    return ""


def _file_local(chunk: Chunk) -> bool:
    spec = spec_for_path(chunk.file)
    if spec is None:
        return False
    return spec.is_file_local(chunk.symbol, _declaration(chunk))


_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.S)
_SLASH_COMMENT = re.compile(r"//[^\n]*")
_HASH_COMMENT = re.compile(r"#[^\n]*")
_HASH_COMMENT_LANGUAGES = frozenset({"python"})


def _code_only(chunk: Chunk) -> str:
    text = _BLOCK_COMMENT.sub(" ", chunk.body)
    text = _SLASH_COMMENT.sub(" ", text)
    if chunk.language in _HASH_COMMENT_LANGUAGES:
        text = _HASH_COMMENT.sub(" ", text)
    return text


def _mentioned_as_a_value(symbol: str, chunks: Sequence[Chunk], defining: str) -> bool:
    pattern = re.compile(rf"\b{re.escape(symbol)}\b\s*(\()?")
    for chunk in chunks:
        if chunk.chunk_id == defining:
            continue
        for match in pattern.finditer(_code_only(chunk)):
            if match.group(1) is None:
                return True
    return False


def _entry(chunk: Chunk, patterns: Sequence[str]) -> bool:
    if chunk.symbol in DEFAULT_ENTRY_SYMBOLS:
        return True
    return any(fnmatch(chunk.symbol, pattern) for pattern in patterns)


def compute(
    chunks: Sequence[Chunk],
    links: Sequence[Link],
    entry_points: Sequence[str] = (),
) -> dict[str, dict[str, object]]:
    functions = [c for c in chunks if c.kind != FILE_CHUNK_KIND]
    known = {c.chunk_id for c in functions}
    callees: dict[str, list[str]] = defaultdict(list)
    callers: dict[str, list[str]] = defaultdict(list)
    for link in links:
        if link.kind == CALLS and link.src in known and link.dst in known and link.src != link.dst:
            callees[link.src].append(link.dst)
            callers[link.dst].append(link.src)

    local = {c.chunk_id: _file_local(c) for c in functions}
    excluded = {c.chunk_id: _is_excluded(c.file) for c in functions}
    entries = {c.chunk_id for c in functions if _entry(c, entry_points)}
    candidates = {
        c.chunk_id
        for c in functions
        if not callers[c.chunk_id] and not local[c.chunk_id] and not excluded[c.chunk_id]
    }

    hops: dict[str, int] = {}
    queue: deque[str] = deque()
    for root in [*entries, *candidates]:
        if root not in hops:
            hops[root] = 0
            queue.append(root)
    while queue:
        node = queue.popleft()
        for callee in callees[node]:
            if callee not in hops:
                hops[callee] = hops[node] + 1
                queue.append(callee)

    out: dict[str, dict[str, object]] = {}
    for chunk in functions:
        chunk_id = chunk.chunk_id
        count = len(set(callers[chunk_id]))
        why: list[str] = []
        state: State

        if excluded[chunk_id]:
            state = "excluded"
            why.append("시험·예제·생성 코드 경로")
        elif chunk_id in entries:
            state = "live"
            why.append("진입점")
        elif hops.get(chunk_id):
            state = "live"
        elif chunk_id in candidates:
            state = "unreferenced"
            why.append("트리 안에 호출자 없음")
            why.append("파일 밖에서는 부를 수 있음")
        elif count:
            state = "unreachable"
            why.append("호출자가 모두 도달 불가")
        elif local[chunk_id]:
            if _mentioned_as_a_value(chunk.symbol, chunks, chunk_id):
                state = "unknown"
                why.append("이름이 값으로 쓰인 곳이 있음 (콜백 테이블일 수 있음)")
            else:
                state = "unreachable"
                why.append("파일 밖에서 부를 수 없는 선언")
                why.append("트리 안에 호출자 없음")
        else:
            state = "unreferenced"
            why.append("트리 안에 호출자 없음")
            why.append("파일 밖에서는 부를 수 있음")

        out[chunk_id] = {
            "state": state,
            "callers": count,
            "hops": hops.get(chunk_id) if state == "live" else None,
            "why": why,
        }

    return out


def stamp(findings: Iterable[dict[str, object]], reach: Mapping[str, dict[str, object]]) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    for finding in findings:
        found = reach.get(str(finding.get("chunk_id", "")))
        out.append({**finding, "reach": found} if found else dict(finding))
    return out
