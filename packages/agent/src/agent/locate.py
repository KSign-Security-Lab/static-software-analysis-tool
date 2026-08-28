"""Resolve a model-supplied ``anchor_text`` to a real source span.

Line numbers from a model are not trusted; the model quotes the source and this
finds it. Models do not quote cleanly, so matching walks a ladder from exact to
whitespace-flexible, strictest first. If nothing matches the finding is dropped
-- a marker on the wrong line is worse than none.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .index.chunk import Chunk
from .schema import Span

# Models copy the ``001| `` prompt prefix in despite being told not to.
_LINE_PREFIX = re.compile(r"(?m)^\s*\d{1,6}\s*\|\s?")

_WHITESPACE = re.compile(r"\s+")

_QUOTE_PAIRS = (('"', '"'), ("'", "'"), ("`", "`"), ("```", "```"))

# ``\/`` is here because models over-escape forward slashes like some JSON
# encoders; a real run returned ``\/tmp\/fw.bin`` for ``/tmp/fw.bin``.
_ESCAPES = (
    ("\\\\", "\\"),
    ('\\"', '"'),
    ("\\'", "'"),
    ("\\/", "/"),
    ("\\n", "\n"),
    ("\\t", "\t"),
)

# Appended when a model "completes" a fragment into a statement: source
# ``sprintf(cmd, "wget %s", url);`` came back as ``"wget %s", url;``. Trimming
# and retrying an *exact* match recovers it without loosening matching.
_TRAILING_NOISE = ";,)}"

# Below this a trimmed anchor matches almost anywhere.
MIN_TRIMMED_CHARS = 8


@dataclass(frozen=True)
class Located:
    """A successful match: where it was found and how hard it was to find."""

    span: Span
    # Which rung matched; a rise in loose matches means prompt drift.
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
    """Progressively looser forms of the anchor, strictest first."""
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

    # Still an exact match, minus punctuation the model added. Bounded so it
    # cannot degrade into "match any prefix".
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
    """1-based line and column for a character offset."""
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
        # Inclusive of the final character, so the range covers the whole match.
        end_column=end_column + 1,
        excerpt=text[start:end],
    )


def _search_window(text: str, chunk: Chunk | None, lines_range: tuple[int, int] | None = None) -> tuple[int, int]:
    """Restricting to the chunk stops a common token like ``memcpy`` matching an
    unrelated function. File chunks span the whole file, which is their extent.

    ``lines_range`` narrows it further, to the region a specialist was actually
    shown. Without it a lens given lines 40-55 that quotes ``memcpy(dst, src, n)``
    resolves to an identical line 20 -- the first hit in the *chunk*, outside
    anything the lens ever read. And the unique-line rung below is worse than
    wrong: it requires exactly one hit in the window, so a line unique within the
    region but repeated in the chunk finds two and the finding is discarded.
    """
    if chunk is None and lines_range is None:
        return 0, len(text)

    first, last = (chunk.start_line, chunk.end_line) if chunk is not None else (1, len(text.splitlines()))
    if lines_range is not None:
        # Clamped rather than trusted: the range came from a model, and one that
        # reaches past the unit would widen the window this exists to narrow.
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
    """Last rung: accepts different line breaks, still requires every token in
    order."""
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
    """Find ``anchor`` in ``text``, or return None.

    ``text`` comes from disk, never from ``chunk.body``: a file chunk's body is
    synthesized and its offsets do not map onto the file.

    ``lines_range`` is the region the caller was shown, when it was shown one.
    Every rung below returns the *first* hit in the window, so the window has to
    be what the model actually read or the span points somewhere it never looked.
    """
    if not anchor.strip():
        return None

    window_start, window_end = _search_window(text, chunk, lines_range)
    window = text[window_start:window_end]

    for strategy, form in _candidates(anchor):
        index = window.find(form)
        if index != -1:
            start = window_start + index
            return Located(_span_from_offsets(file, text, start, start + len(form)), strategy)

    # Whitespace-flexible, on the loosest literal form we produced.
    _, loosest = _candidates(anchor)[-1]
    pattern = _flexible_pattern(loosest)
    if pattern is not None:
        match = pattern.search(window)
        if match:
            start = window_start + match.start()
            return Located(_span_from_offsets(file, text, start, window_start + match.end()), "whitespace-flexible")

    # A single-line anchor occurring on exactly one line in the window is that
    # line, even with a trailing comment or truncated tail.
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
    """(offset, line) for each line, offsets relative to ``text``."""
    out: list[tuple[int, str]] = []
    offset = 0
    for line in text.splitlines(keepends=True):
        out.append((offset, line.rstrip("\n")))
        offset += len(line)
    return out
