from __future__ import annotations

import re
from dataclasses import dataclass

from .config import AgentConfig
from .index.chunk import FILE_CHUNK_KIND, Chunk
from .index.store import ChunkStore


@dataclass
class ContextPack:
    chunk: Chunk
    text: str
    truncated: bool = False
    region: tuple[int, int] | None = None
    dropped: tuple[str, ...] = ()


MAX_SIGNATURE_LINES = 6
MAX_SIGNATURE_CHARS = 240


def _signature(chunk: Chunk) -> str:
    parts: list[str] = []
    depth = 0
    for line in chunk.body.splitlines()[:MAX_SIGNATURE_LINES]:
        text = _COMMENT.sub(" ", line.split("//")[0]).strip()
        if not text and not parts:
            continue
        parts.append(text)
        depth += text.count("(") - text.count(")")
        if "(" in " ".join(parts) and depth <= 0:
            break

    signature = " ".join(" ".join(parts).split())
    opened = signature.find("(")
    if opened >= 0 and depth <= 0:
        level = 0
        for index, char in enumerate(signature[opened:], start=opened):
            level += (char == "(") - (char == ")")
            if level == 0:
                signature = signature[: index + 1]
                break
    signature = signature.split("{")[0].strip().rstrip(";").strip()
    if not signature:
        return chunk.symbol
    if depth > 0 or len(signature) > MAX_SIGNATURE_CHARS:
        return signature[:MAX_SIGNATURE_CHARS].rstrip(", ") + " ...)"
    return signature


def truncate(text: str, limit: int) -> tuple[str, bool]:
    if len(text) <= limit:
        return text, False
    return text[:limit] + f"\n... [{limit}자에서 잘림]", True


_NOT_NAMES = frozenset(
    """
    if else for while do switch case break continue return goto sizeof typedef
    struct union enum const static extern volatile register inline void char int
    long short float double signed unsigned auto new delete this null nullptr
    true false and or not in is def class import from as pass raise try except
    finally with lambda self func var let type interface package go defer chan
    map range nil error string bool byte rune public private protected final
    abstract implements extends throws catch throw instanceof
    """.split()
)

_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_COMMENT = re.compile(r"/\*.*?\*/", re.S)
MAX_DECLARATION_LINES = 24


def declarations_for(chunk: Chunk, first: int, last: int) -> list[tuple[int, str]]:
    lines = chunk.body.splitlines()
    if not lines:
        return []

    used: set[str] = set()
    for offset, line in enumerate(lines):
        if first <= chunk.start_line + offset <= last:
            used.update(name for name in _NAME.findall(line) if name not in _NOT_NAMES)

    wanted: dict[int, str] = {}
    for offset, line in enumerate(lines):
        number = chunk.start_line + offset
        if number >= first:
            break
        for name in _NAME.findall(line):
            if name in used:
                wanted.setdefault(number, line)
                used.discard(name)
                break

    if chunk.start_line < first:
        wanted.setdefault(chunk.start_line, lines[0])

    return sorted(wanted.items())[:MAX_DECLARATION_LINES]


def build_context(
    store: ChunkStore,
    chunk: Chunk,
    config: AgentConfig,
    region: tuple[int, int] | None = None,
) -> ContextPack:
    sections: list[str] = []
    dropped: list[str] = []
    budget = config.input_chars()

    first, last = region or (chunk.start_line, chunk.end_line)
    body, truncated = truncate(chunk.numbered_range(first, last), min(config.max_chunk_chars, budget))
    label = "파일 수준 선언" if chunk.kind == FILE_CHUNK_KIND else "분석 대상 단위"
    where = f"{first}-{last}번 줄" if region else f"{chunk.start_line}-{chunk.end_line}번 줄"
    header = f"=== {label}: {chunk.file} :: {chunk.symbol} ({where}) ==="
    primary = f"{header}\n{body}"
    sections.append(primary)
    budget -= len(primary)

    if region:
        declared = declarations_for(chunk, first, last)
        if declared:
            width = max(3, len(str(chunk.end_line)))
            block = "\n".join(
                [
                    "=== 이 구간이 쓰는 것들이 선언된 곳 (같은 단위의 앞부분) ===",
                    *(f"{number:0{width}d}| {line}" for number, line in declared),
                ]
            )
            if len(block) <= budget:
                sections.append(block)
                budget -= len(block)
            else:
                dropped.append("declarations")

    callees = _callees_for(store, chunk, region, config)
    if callees:
        header = "=== 이 단위가 부르는 것들 (선언, 그리고 이미 분석했다면 그 결과) ==="
        rendered = [header]
        spent = len(header)
        for entry in callees:
            if spent + 1 + len(entry) > budget:
                dropped.append("callees")
                break
            rendered.append(entry)
            spent += 1 + len(entry)
        if len(rendered) > 1:
            sections.append("\n".join(rendered))
            budget -= spent

    if chunk.kind != FILE_CHUNK_KIND:
        file_chunk = next((c for c in store.chunks_in_file(chunk.file) if c.kind == FILE_CHUNK_KIND), None)
        if file_chunk is not None and file_chunk.body.strip():
            block, _ = truncate(
                f"=== {chunk.file} 의 최상위 선언 ===\n{file_chunk.body}",
                max(0, min(budget // 2, config.max_chunk_chars)),
            )
            if block and len(block) <= budget:
                sections.append(block)
                budget -= len(block)
            else:
                dropped.append("file declarations")

    budget = max(0, budget)
    type_defs = _type_definitions(store, chunk, budget)
    if type_defs:
        sections.append(type_defs)
        budget -= len(type_defs)

    callers = store.callers_of(chunk.chunk_id)
    if callers:
        block = "\n".join(
            [
                "=== 여기서 호출됨 ===",
                *(f"- {c.file}:{c.start_line} {_signature(c)}" for c in callers[:10]),
            ]
        )
        if len(block) <= budget:
            sections.append(block)
        else:
            dropped.append("callers")

    return ContextPack(
        chunk=chunk,
        text="\n\n".join(sections),
        truncated=truncated,
        region=region,
        dropped=tuple(dropped),
    )


def _callees_for(
    store: ChunkStore,
    chunk: Chunk,
    region: tuple[int, int] | None,
    config: AgentConfig,
) -> list[str]:
    seen: set[str] = set()
    candidates: list[Chunk] = []
    for callee in store.callees_of(chunk.chunk_id):
        if callee.chunk_id in seen or callee.chunk_id == chunk.chunk_id:
            continue
        if callee.kind == FILE_CHUNK_KIND:
            continue
        seen.add(callee.chunk_id)
        candidates.append(callee)

    if not candidates:
        return []

    in_region: set[str] = set()
    if region:
        first, last = region
        for offset, line in enumerate(chunk.body.splitlines()):
            if first <= chunk.start_line + offset <= last:
                in_region.update(_NAME.findall(line))

    notes = {callee.chunk_id: store.note(callee.chunk_id) or "" for callee in candidates}

    def rank(callee: Chunk) -> tuple[int, int, int]:
        return (
            0 if callee.symbol in in_region else 1,
            0 if callee.file != chunk.file else 1,
            0 if notes[callee.chunk_id] else 1,
        )

    ordered = sorted(candidates, key=rank)[: config.max_callee_notes]
    lines: list[str] = []
    for callee in ordered:
        note = notes[callee.chunk_id]
        where = f"{callee.file}:{callee.start_line}"
        entry = f"- {where}  {_signature(callee)}"
        if note:
            entry += f"\n    {note}"
        elif not store.is_inspected(callee.chunk_id):
            entry += "\n    (아직 분석하지 않았습니다)"
        lines.append(entry)
    return lines


def _type_definitions(store: ChunkStore, chunk: Chunk, budget: int) -> str:
    blocks: list[str] = []
    remaining = budget
    seen: set[str] = set()

    for type_name in chunk.types_used:
        if type_name in seen:
            continue
        seen.add(type_name)
        for definition in store.definition_of(type_name):
            if definition.chunk_id == chunk.chunk_id:
                continue
            snippet = _extract_type(definition.body, type_name)
            if not snippet:
                continue
            entry = f"- {type_name} ({definition.file} 에서):\n{snippet}"
            if len(entry) > remaining:
                break
            blocks.append(entry)
            remaining -= len(entry)
            break

    return "=== 쓰이는 타입 ===\n" + "\n".join(blocks) if blocks else ""


def _extract_type(body: str, type_name: str) -> str:
    lines = body.splitlines()
    for index, line in enumerate(lines):
        if type_name in line and any(keyword in line for keyword in ("struct", "typedef", "class", "enum", "union")):
            start = index
            depth = 0
            for end in range(start, min(len(lines), start + 60)):
                depth += lines[end].count("{") - lines[end].count("}")
                if depth <= 0 and end > start:
                    return "\n".join(lines[start : end + 1])
                if depth == 0 and lines[end].rstrip().endswith(";"):
                    return "\n".join(lines[start : end + 1])
            return "\n".join(lines[start : start + 20])
    return ""
