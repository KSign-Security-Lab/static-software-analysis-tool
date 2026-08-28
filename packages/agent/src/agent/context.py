"""Assemble one chunk's context from the index, deterministically.

The pack is the chunk, its file's top-level material, what the things it calls
are declared as, its callers' signatures, and the types it uses. No model decides
what to include: letting it explore costs a round trip per file and produces a
different context every run, which makes findings irreproducible.

What a callee does used to travel only as the prose note its analyst wrote, and
the prompt lets that be empty -- so it was, for 99% of units, and the section
reached 0 of 338 analyses in a measured run. Meanwhile 64% of resolved call edges
cross a file. A declaration is never blank, so it travels now; the note comes too
when there is one.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .config import AgentConfig
from .index.chunk import FILE_CHUNK_KIND, Chunk
from .index.store import ChunkStore


@dataclass
class ContextPack:
    """Everything the model is shown about one chunk."""

    chunk: Chunk
    text: str
    truncated: bool = False
    #: The stretch of the unit this pack is about, when it is not the whole one.
    region: tuple[int, int] | None = None
    #: Sections that did not fit, named. A pack that silently omits one is
    #: indistinguishable from a pack that had nothing to omit, which is how the
    #: callee section could be missing from an entire run before anyone noticed.
    #: `scout` reads this: supporting material that did not fit is a better
    #: reason to narrow a unit than the length of the string.
    dropped: tuple[str, ...] = ()


#: A signature is one line in this tree 88% of the time; these bound the rest.
MAX_SIGNATURE_LINES = 6
MAX_SIGNATURE_CHARS = 240


def _signature(chunk: Chunk) -> str:
    """How it is called: the whole declaration, not the first line of it.

    First line only was wrong in the way that reads as right -- 85 of 735
    function chunks here close their parameter list on a later line, so this
    returned `static DIGIT bn_Div(DIGIT *L_Dst, DIGIT *L_Rem,` for a six-argument
    function. Wrong arity is worse than silence to a memory lens: it invites both
    "two for two, fine" and a fabricated arity finding.

    Brackets counted, not parsed. The index holds no parameter list -- a real
    parse would mean a tree-sitter pass and a reindex -- and counting is exact
    for anything that is not a string or a macro, which a C header is not.
    A cut always looks like one.
    """
    parts: list[str] = []
    depth = 0
    for line in chunk.body.splitlines()[:MAX_SIGNATURE_LINES]:
        # These sources comment their parameters, in both styles and sometimes in
        # a legacy encoding. A comment is never part of how a function is called.
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
        # Cut at the parenthesis that closes the parameter list, so a trailing
        # comment or an attribute after it does not read as part of the call.
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


#: Words that are not names worth chasing a declaration for. Not a grammar --
#: deliberately small, and shared across the languages the index chunks, because
#: the cost of a miss here is one extra line of context.
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

#: Block comments inside a parameter list, which these sources use freely.
_COMMENT = re.compile(r"/\*.*?\*/", re.S)

#: A region is a few lines; its declarations should not dwarf it.
MAX_DECLARATION_LINES = 24


def declarations_for(chunk: Chunk, first: int, last: int) -> list[tuple[int, str]]:
    """Lines from earlier in the unit that introduce what the region uses.

    The hole `scout` opens, closed deterministically. A region of lines 807-808
    reading ``sprintf(cmd, "wget %s", url)`` says nothing about whether ``cmd``
    is a 256-byte array or a heap pointer, and the declaration that decides it
    is four hundred lines up and outside the region. A specialist shown only the
    region answered correctly by assuming -- which is a guess that happened to
    be right, and the next one will not be.

    First mention rather than a parse: the earliest line of a unit naming an
    identifier is, in every language this indexes, where it is introduced --
    parameter, declaration or first assignment. Cheap, language-agnostic, and
    wrong only in the direction of including one line too many.
    """
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

    # The signature always: it names the parameters, and a region that uses one
    # of them cannot be judged without knowing where it came from.
    if chunk.start_line < first:
        wanted.setdefault(chunk.start_line, lines[0])

    return sorted(wanted.items())[:MAX_DECLARATION_LINES]


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
    dropped: list[str] = []
    # The window, not a number invented against one. `config.py` says of the flat
    # budget that it is "roughly 40% more than [the window] holds", and `scout`
    # has always measured the finished pack against `input_chars()` -- so the
    # pack was built to one budget and judged against another.
    budget = config.input_chars()

    first, last = region or (chunk.start_line, chunk.end_line)
    # Clamped to the budget as well as to `max_chunk_chars`, because the two can
    # invert: `input_chars()` is derived from the window, so an 8k endpoint
    # allows ~4150 characters while the body cap stays at 12000. Truncating here
    # is also the right outcome rather than a lossy one -- `truncated` is what
    # `scout` reads to narrow a unit into regions, so an oversized body routes
    # into the designed path instead of overflowing the request.
    body, truncated = truncate(chunk.numbered_range(first, last), min(config.max_chunk_chars, budget))
    label = "파일 수준 선언" if chunk.kind == FILE_CHUNK_KIND else "분석 대상 단위"
    where = f"{first}-{last}번 줄" if region else f"{chunk.start_line}-{chunk.end_line}번 줄"
    header = f"=== {label}: {chunk.file} :: {chunk.symbol} ({where}) ==="
    primary = f"{header}\n{body}"
    sections.append(primary)
    budget -= len(primary)

    # Immediately after the code and before anything else, because it is the
    # only section that can decide a finding rather than colour it: a region
    # holding `sprintf(cmd, ...)` and not `char cmd[256];` leaves a specialist
    # guessing at the one fact the answer turns on.
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
        # Entry by entry, not as one block. Every other supporting section is
        # all-or-nothing, which for this one would mean twelve callees or zero at
        # a one-character boundary -- and the units where it would flip to zero
        # are the crowded ones that most need it. Ranked above, so what survives
        # a tight budget is what was worth keeping.
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
            # Half of what is left, not all of it. This is the only section that
            # resizes instead of dropping, so it always won ties it had not
            # earned -- and everything below it (types, callers) got whatever it
            # chose to leave, which was often nothing.
            block, _ = truncate(
                f"=== {chunk.file} 의 최상위 선언 ===\n{file_chunk.body}",
                max(0, min(budget // 2, config.max_chunk_chars)),
            )
            if block and len(block) <= budget:
                sections.append(block)
                budget -= len(block)
            else:
                dropped.append("file declarations")

    # Never negative: `_type_definitions` walks its own budget down and would
    # otherwise rely on `len(entry) > remaining` being incidentally true.
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
    """What this unit calls, as rendered lines, best first.

    Where it is, how it is declared, and what analysing it found if anything did.
    The declaration is the part that is always there -- a caller used to get
    nothing at all unless the callee's analyst had volunteered prose.

    Ranked before the cap, though the cap is rarely the constraint (16 of 542
    calling units exceed it). The order really decides which entries survive the
    budget running out, on exactly the crowded units where this matters.
    """
    seen: set[str] = set()
    candidates: list[Chunk] = []
    for callee in store.callees_of(chunk.chunk_id):
        # `callees_of` joins without DISTINCT, and one call name can resolve to
        # several definitions, so the raw list repeats.
        if callee.chunk_id in seen or callee.chunk_id == chunk.chunk_id:
            continue
        # A file chunk can be a call target -- its `defines` are the file's type
        # definitions -- but its `symbol` is a path and its body is a synthesized
        # concatenation, so a "signature" for it is the first line of an elided
        # blob. Its typedefs already reach the pack through `_type_definitions`.
        if callee.kind == FILE_CHUNK_KIND:
            continue
        seen.add(callee.chunk_id)
        candidates.append(callee)

    if not candidates:
        return []

    # Names the specialist is actually reading, when it is reading a stretch
    # rather than the whole unit. Same technique as `declarations_for`.
    in_region: set[str] = set()
    if region:
        first, last = region
        for offset, line in enumerate(chunk.body.splitlines()):
            if first <= chunk.start_line + offset <= last:
                in_region.update(_NAME.findall(line))

    # Read once, for both the ranking and the rendering. One round trip per
    # candidate either way -- a note is a ranking key, so it cannot be deferred
    # until after the cap -- but not two, which is what asking again below would
    # have cost on a unit with thirty-eight callees.
    notes = {callee.chunk_id: store.note(callee.chunk_id) or "" for callee in candidates}

    def rank(callee: Chunk) -> tuple[int, int, int]:
        return (
            0 if callee.symbol in in_region else 1,
            # A same-file callee's declaration is usually in the file's top-level
            # section already; a cross-file one is in *its* file's, which is
            # never included. Cross-file entries carry what nothing else carries.
            0 if callee.file != chunk.file else 1,
            0 if notes[callee.chunk_id] else 1,
        )

    # Sorted stably, so `callees_of`'s (file, start_line) order is the tiebreak
    # and two runs over one tree still agree.
    ordered = sorted(candidates, key=rank)[: config.max_callee_notes]

    lines: list[str] = []
    for callee in ordered:
        note = notes[callee.chunk_id]
        where = f"{callee.file}:{callee.start_line}"
        entry = f"- {where}  {_signature(callee)}"
        if note:
            entry += f"\n    {note}"
        elif not store.is_inspected(callee.chunk_id):
            # Said, so silence is not read as a clean bill of health.
            entry += "\n    (아직 분석하지 않았습니다)"
        lines.append(entry)
    return lines


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
