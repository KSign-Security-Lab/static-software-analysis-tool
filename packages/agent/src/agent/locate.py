"""Turn a model-supplied ``anchor_text`` into a real source span.

Models get line numbers wrong, so no line number the model produces is trusted.
Instead the model quotes the offending source text and this module finds it,
deriving the true line and column from the match.

They also do not quote cleanly. Observed from a real run against a served
model, on a function whose finding was entirely correct::

    anchor_text = '"snprintf(cmd, sizeof(cmd), \\"wget -O /tmp/fw %s\\", req->location);"'

-- wrapped in quotes, with the inner quotes backslash-escaped. A plain
``anchor in source`` test rejects that, and rejecting it would have thrown away
a true positive. Hence a ladder of progressively looser attempts rather than one
exact match.

The ladder is ordered strictest-first and stops at the first hit, so a finding
that *can* be located exactly is located exactly. When every rung fails the
finding is **dropped**: a marker on the wrong line is worse than no marker,
because line-level precision is the entire point of the product.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .index.chunk import Chunk
from .schema import Span

#: Line-number prefixes we add when prompting (``001| ``). Models sometimes copy
#: them into the anchor despite being told not to.
_LINE_PREFIX = re.compile(r"(?m)^\s*\d{1,6}\s*\|\s?")

_WHITESPACE = re.compile(r"\s+")

#: Wrapping quotes a model adds when it thinks it is quoting rather than copying.
_QUOTE_PAIRS = (('"', '"'), ("'", "'"), ("`", "`"), ("```", "```"))

#: ``\/`` is in here because models over-escape forward slashes the way some
#: JSON encoders do -- a real run returned
#: ``sprintf(cmd, "wget %s -O \/tmp\/fw.bin", url);`` for a line whose source
#: says ``/tmp/fw.bin``. Unescaping it is lossless; leaving it out discarded a
#: correct finding.
_ESCAPES = (
    ("\\\\", "\\"),
    ('\\"', '"'),
    ("\\'", "'"),
    ("\\/", "/"),
    ("\\n", "\n"),
    ("\\t", "\t"),
)

#: Punctuation a model appends when it "completes" a fragment into what looks
#: like a statement. Observed: source ``sprintf(cmd, "wget %s", url);`` came
#: back as ``"wget %s", url;`` -- the model dropped the call prefix and added a
#: semicolon. Trimming these and retrying an *exact* match recovers it without
#: loosening the match itself.
_TRAILING_NOISE = ";,)}"

#: A trimmed anchor shorter than this is too generic to identify a location.
#: ``);`` trimmed down to ``)`` would match almost anywhere.
MIN_TRIMMED_CHARS = 8


@dataclass(frozen=True)
class Located:
    """A successful match: where it was found and how hard it was to find."""

    span: Span
    #: Which rung of the ladder matched. Recorded so a run can report how much
    #: of its output needed loosening -- a sudden rise means prompt drift.
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

    # Still an exact substring match, just with punctuation the model added
    # removed. Bounded so this cannot degrade into "match any prefix".
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


def _search_window(text: str, chunk: Chunk | None) -> tuple[int, int]:
    """Character range of the file the anchor is allowed to match in.

    Restricting to the chunk keeps a common token (``memcpy``) from matching in
    an unrelated function fifty lines away. File chunks get the whole file,
    which is correct -- that is their extent.
    """
    if chunk is None:
        return 0, len(text)
    lines = text.splitlines(keepends=True)
    start_index = max(0, chunk.start_line - 1)
    end_index = min(len(lines), chunk.end_line)
    start = sum(len(line) for line in lines[:start_index])
    end = start + sum(len(line) for line in lines[start_index:end_index])
    return start, end


def _flexible_pattern(anchor: str) -> re.Pattern[str] | None:
    """Match the anchor's tokens with any whitespace between them.

    This is the last rung: it accepts a model that re-wrapped a long call across
    different line breaks, while still requiring every token in order.
    """
    tokens = [re.escape(token) for token in _WHITESPACE.split(anchor.strip()) if token]
    if not tokens:
        return None
    return re.compile(r"\s+".join(tokens))


def locate_anchor(anchor: str, file: str, text: str, chunk: Chunk | None = None) -> Located | None:
    """Find ``anchor`` in ``text``. Returns None if it is not really there.

    ``text`` is always read from disk. Chunk bodies are not searched directly:
    a file chunk's body is a synthesized concatenation whose offsets do not map
    onto the file (see ``Chunk.body_is_verbatim``).
    """
    if not anchor.strip():
        return None

    window_start, window_end = _search_window(text, chunk)
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

    # Single-line anchors sometimes come back with a trailing comment or a
    # truncated tail. If the first substantial token sequence occurs on exactly
    # one line in the window, that line is the anchor.
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
