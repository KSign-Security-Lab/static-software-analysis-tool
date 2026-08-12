"""Assemble one chunk's context from the index, deterministically.

The pack is the chunk, its file's top-level material, notes written when its
callees were analysed, its callers' signatures, and the types it uses. No model
decides what to include: letting it explore costs a round trip per file and
produces a different context every run, which makes findings irreproducible.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .config import AgentConfig
from .index.chunk import FILE_CHUNK_KIND, Chunk
from .index.store import ChunkStore


@dataclass
class ContextPack:
    """Everything the model is shown about one chunk."""

    chunk: Chunk
    text: str
    callee_notes: list[tuple[str, str]] = field(default_factory=list)
    truncated: bool = False
    #: The stretch of the unit this pack is about, when it is not the whole one.
    region: tuple[int, int] | None = None

    @property
    def has_callee_context(self) -> bool:
        return bool(self.callee_notes)


def _signature(chunk: Chunk) -> str:
    """First line: enough to see how it is called."""
    for line in chunk.body.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped.rstrip("{").strip()
    return chunk.symbol


def truncate(text: str, limit: int) -> tuple[str, bool]:
    if len(text) <= limit:
        return text, False
    return text[:limit] + f"\n... [{limit}자에서 잘림]", True


def build_context(
    store: ChunkStore,
    chunk: Chunk,
    config: AgentConfig,
    region: tuple[int, int] | None = None,
) -> ContextPack:
    """Sections are added in priority order, so on a large chunk the supporting
    material is dropped, never the code under analysis.

    ``region`` narrows the code under analysis to one stretch of the unit, which
    is what buys the room: a unit too large to send whole is sent as the part
    worth reading, with the supporting material it can now afford.
    """
    sections: list[str] = []
    budget = config.context_char_budget

    first, last = region or (chunk.start_line, chunk.end_line)
    body, truncated = truncate(chunk.numbered_range(first, last), config.max_chunk_chars)
    label = "파일 수준 선언" if chunk.kind == FILE_CHUNK_KIND else "분석 대상 단위"
    where = f"{first}-{last}번 줄" if region else f"{chunk.start_line}-{chunk.end_line}번 줄"
    header = f"=== {label}: {chunk.file} :: {chunk.symbol} ({where}) ==="
    primary = f"{header}\n{body}"
    sections.append(primary)
    budget -= len(primary)

    callee_notes: list[tuple[str, str]] = []
    for callee in store.callees_of(chunk.chunk_id):
        note = store.note(callee.chunk_id)
        if note:
            callee_notes.append((callee.symbol, note))
        if len(callee_notes) >= config.max_callee_notes:
            break

    if callee_notes:
        lines = [
            "=== 이 단위가 부르는 것들이 하는 일 (먼저 분석한 결과) ===",
            *(f"- {symbol}: {note}" for symbol, note in callee_notes),
        ]
        block = "\n".join(lines)
        if len(block) <= budget:
            sections.append(block)
            budget -= len(block)

    if chunk.kind != FILE_CHUNK_KIND:
        file_chunk = next((c for c in store.chunks_in_file(chunk.file) if c.kind == FILE_CHUNK_KIND), None)
        if file_chunk is not None and file_chunk.body.strip():
            block, _ = truncate(
                f"=== {chunk.file} 의 최상위 선언 ===\n{file_chunk.body}",
                max(0, min(budget, config.max_chunk_chars)),
            )
            if block and len(block) <= budget:
                sections.append(block)
                budget -= len(block)

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

    return ContextPack(
        chunk=chunk,
        text="\n\n".join(sections),
        callee_notes=callee_notes,
        truncated=truncated,
        region=region,
    )


def _type_definitions(store: ChunkStore, chunk: Chunk, budget: int) -> str:
    """``char buf[8]`` versus ``char *buf`` changes what an overflow means."""
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
    """One type out of a file chunk's body; pasting all of them would crowd out
    the code under analysis."""
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
