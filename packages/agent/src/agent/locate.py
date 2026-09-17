from __future__ import annotations

import re
from dataclasses import dataclass

from .index.chunk import Chunk
from .schema import Span

_LINE_PREFIX = re.compile(r"(?m)^\s*\d{1,6}\s*\|\s?")
_WHITESPACE = re.compile(r"\s+")
_QUOTE_PAIRS = (('"', '"'), ("'", "'"), ("`", "`"), ("```", "```"))
_ESCAPES = (
    ("\\\\", "\\"),
    ('\\"', '"'),
    ("\\'", "'"),
    ("\\/", "/"),
    ("\\n", "\n"),
    ("\\t", "\t"),
)

_TRAILING_NOISE = ";,)}"

MIN_TRIMMED_CHARS = 8


@dataclass(frozen=True)
class Located:
    span: Span
    strategy: str


def _strip_quotes(text: str) -> str:
    stripped = text.strip()
    for open_q, close_q in _QUOTE_PAIRS:
        if len(stripped) > len(open_q) + len(close_q) and stripped.startswith(open_q) and stripped.endswith(close_q):
            return stripped[len(open_q) : -len(close_q)].strip()
    return stripped


def _unescape(text: str) -> str:
    out = text
    for escaped, plain in _ESCAPES:
        out = out.replace(escaped, plain)
    return out


def _candidates(anchor: str) -> list[tuple[str, str]]:
    forms: list[tuple[str, str]] = [("exact", anchor)]
    unprefixed = _LINE_PREFIX.sub("", anchor)
    if unprefixed != anchor:
        forms.append(("line-prefix-stripped", unprefixed))

    dequoted = _strip_quotes(unprefixed)
    if dequoted != unprefixed:
        forms.append(("dequoted", dequoted))

    unescaped = _unescape(dequoted)
    if unescaped != dequoted:
        forms.append(("unescaped", unescaped))

    trimmed = unescaped.strip()
    if trimmed and trimmed != unescaped:
        forms.append(("trimmed", trimmed))

    candidate = (forms[-1][1]).strip()
    for _ in range(3):
        if len(candidate) <= MIN_TRIMMED_CHARS or candidate[-1] not in _TRAILING_NOISE:
            break
        candidate = candidate[:-1].strip()
        forms.append(("punctuation-trimmed", candidate))

    seen: set[str] = set()
    unique: list[tuple[str, str]] = []
    for name, form in forms:
        if form and form not in seen:
            seen.add(form)
            unique.append((name, form))
    return unique


def _offset_to_line_col(text: str, offset: int) -> tuple[int, int]:
    line = text.count("\n", 0, offset) + 1
    line_start = text.rfind("\n", 0, offset) + 1
    return line, offset - line_start + 1


def _span_from_offsets(file: str, text: str, start: int, end: int) -> Span:
    start_line, start_column = _offset_to_line_col(text, start)
    end_line, end_column = _offset_to_line_col(text, max(start, end - 1))
    return Span(
        file=file,
        start_line=start_line,
        start_column=start_column,
        end_line=end_line,
        end_column=end_column + 1,
        excerpt=text[start:end],
    )


def _search_window(text: str, chunk: Chunk | None, lines_range: tuple[int, int] | None = None) -> tuple[int, int]:
    if chunk is None and lines_range is None:
        return 0, len(text)

    first, last = (chunk.start_line, chunk.end_line) if chunk is not None else (1, len(text.splitlines()))
    if lines_range is not None:
        first = max(first, lines_range[0])
        last = min(last, lines_range[1])
        if first > last:
            first, last = (chunk.start_line, chunk.end_line) if chunk is not None else (1, last)

    lines = text.splitlines(keepends=True)
    start_index = max(0, first - 1)
    end_index = min(len(lines), last)
    start = sum(len(line) for line in lines[:start_index])
    end = start + sum(len(line) for line in lines[start_index:end_index])
    return start, end


def _flexible_pattern(anchor: str) -> re.Pattern[str] | None:
    tokens = [re.escape(token) for token in _WHITESPACE.split(anchor.strip()) if token]
    if not tokens:
        return None
    return re.compile(r"\s+".join(tokens))


def locate_anchor(
    anchor: str,
    file: str,
    text: str,
    chunk: Chunk | None = None,
    lines_range: tuple[int, int] | None = None,
) -> Located | None:
    if not anchor.strip():
        return None

    window_start, window_end = _search_window(text, chunk, lines_range)
    window = text[window_start:window_end]

    for strategy, form in _candidates(anchor):
        index = window.find(form)
        if index != -1:
            start = window_start + index
            return Located(_span_from_offsets(file, text, start, start + len(form)), strategy)

    _, loosest = _candidates(anchor)[-1]
    pattern = _flexible_pattern(loosest)
    if pattern is not None:
        match = pattern.search(window)
        if match:
            start = window_start + match.start()
            return Located(_span_from_offsets(file, text, start, window_start + match.end()), "whitespace-flexible")

    if "\n" not in loosest:
        condensed = _WHITESPACE.sub(" ", loosest).strip()
        hits = [
            offset
            for offset, line in _iter_lines(window)
            if condensed and condensed in _WHITESPACE.sub(" ", line).strip()
        ]
        if len(hits) == 1:
            start = window_start + hits[0]
            line_end = window.find("\n", hits[0])
            end = window_start + (len(window) if line_end == -1 else line_end)
            return Located(_span_from_offsets(file, text, start, end), "unique-line")

    return None


def _iter_lines(text: str) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    offset = 0
    for line in text.splitlines(keepends=True):
        out.append((offset, line.rstrip("\n")))
        offset += len(line)
    return out
