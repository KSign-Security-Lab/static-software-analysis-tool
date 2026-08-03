"""Location integrity: the property the whole product rests on.

A finding is only worth showing if its squiggle is on the right characters. So
these tests cover both directions -- anchors that must resolve despite the model
mangling them, and anchors that must be rejected rather than guessed at.

The mangled forms here are not invented. They are what a served model actually
returned during the Phase 0 spike.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agent.index.chunk import FILE_CHUNK_KIND, chunk_source
from agent.locate import locate_anchor

SOURCE = """\
#include <stdio.h>
#include <stdlib.h>

typedef struct { char *location; } Request;

void handle_update_firmware(const Request *req) {
    char cmd[256];
    if (req->location == NULL) return;
    snprintf(cmd, sizeof(cmd), "wget -O /tmp/fw %s", req->location);
    system(cmd);
}

void other(void) {
    system("true");
}
"""


def _span(anchor: str, chunk=None):
    located = locate_anchor(anchor, "a.c", SOURCE, chunk)
    return located.span if located else None


def _text_at(span) -> str:
    """Re-read the span out of the source, the way the excerpt check does."""
    lines = SOURCE.splitlines()
    if span.start_line == span.end_line:
        return lines[span.start_line - 1][span.start_column - 1 : span.end_column - 1]
    first = lines[span.start_line - 1][span.start_column - 1 :]
    middle = lines[span.start_line : span.end_line - 1]
    last = lines[span.end_line - 1][: span.end_column - 1]
    return "\n".join([first, *middle, last])


def test_exact_anchor_resolves_to_the_right_characters() -> None:
    span = _span("system(cmd);")
    assert span is not None
    assert span.start_line == 10
    assert span.excerpt == "system(cmd);"
    assert _text_at(span) == "system(cmd);", "span coordinates do not select the excerpt"


def test_span_columns_are_one_based() -> None:
    span = _span("char cmd[256];")
    assert span is not None
    assert span.start_column == 5, "four spaces of indent means the token starts at column 5"


def test_the_anchor_a_real_model_returned_still_resolves() -> None:
    """Verbatim from the Phase 0 spike, which produced a correct finding.

    The model wrapped the whole statement in quotes and backslash-escaped the
    inner ones. A plain substring test rejects this, and rejecting it would have
    discarded a true positive -- which is why the ladder exists.
    """
    mangled = '"snprintf(cmd, sizeof(cmd), \\"wget -O /tmp/fw %s\\", req->location);"'
    span = _span(mangled)
    assert span is not None, "the ladder failed on the exact form a real model emits"
    assert span.start_line == 9
    assert span.excerpt.startswith("snprintf(cmd")
    assert span.excerpt.endswith("req->location);")


def test_model_appended_punctuation_is_trimmed_back_to_an_exact_match() -> None:
    """Also from a real run, against ``sprintf(cmd, "wget %s ...", url);``.

    The model returned ``"wget %s -O /tmp/fw.bin", url;`` -- it dropped the
    ``sprintf(cmd, `` prefix and *added* a semicolon to make the fragment look
    like a statement. Removing the added punctuation leaves something that is
    still an exact substring, so this is recovered without loosening matching.
    """
    source = '    sprintf(cmd, "wget %s -O /tmp/fw.bin", url);\n'
    located = locate_anchor('"wget %s -O /tmp/fw.bin", url;', "fw.c", source)
    assert located is not None
    assert located.strategy == "punctuation-trimmed"
    assert located.span.excerpt == '"wget %s -O /tmp/fw.bin", url'


def test_json_over_escaped_slashes_and_leading_tabs_still_resolve() -> None:
    """Third real form: ``\\/`` for ``/``, plus indentation the model invented.

    Some encoders escape forward slashes; the model copied that convention into
    ``anchor_text``. The finding was correct and would have been discarded.
    """
    source = '    sprintf(cmd, "wget %s -O /tmp/fw.bin", url);\n'
    located = locate_anchor('\t\tsprintf(cmd, "wget %s -O \\/tmp\\/fw.bin", url);', "fw.c", source)
    assert located is not None
    assert located.span.excerpt == 'sprintf(cmd, "wget %s -O /tmp/fw.bin", url);'


def test_degenerate_anchors_are_still_rejected() -> None:
    """The same run also produced ``/**/`` twice. Junk must stay dropped."""
    source = "void f(void) { /* note */ g(); }\n"
    assert locate_anchor("/**/", "a.c", source) is None


def test_punctuation_trimming_cannot_shrink_an_anchor_into_noise() -> None:
    """Trimming must not turn a bad anchor into a match on a stray bracket."""
    source = "int main(void) { return f(x); }\n"
    assert locate_anchor("zzz;", "a.c", source) is None
    assert locate_anchor("nonexistent call);", "a.c", source) is None


def test_copied_line_number_prefix_is_stripped() -> None:
    """The prompt says not to copy the NNN| prefix. Models copy it anyway."""
    span = _span("010|     system(cmd);")
    assert span is not None
    assert span.start_line == 10


def test_reflowed_whitespace_still_matches() -> None:
    """A model that re-wrapped a long call must not lose its finding."""
    span = _span('snprintf(cmd,\n    sizeof(cmd),\n    "wget -O /tmp/fw %s",\n    req->location);')
    assert span is not None
    assert span.start_line == 9


@pytest.mark.parametrize(
    "anchor",
    [
        "strcpy(dst, src);",
        "this text does not appear anywhere",
        "",
        "   ",
    ],
)
def test_absent_anchors_are_rejected_not_guessed(anchor: str) -> None:
    """Dropping a finding beats pointing at the wrong line."""
    assert locate_anchor(anchor, "a.c", SOURCE) is None


def test_chunk_window_disambiguates_a_repeated_token() -> None:
    """``system(`` occurs twice. The chunk decides which one is meant."""
    chunks = chunk_source("a.c", SOURCE)
    handler = next(c for c in chunks if c.symbol == "handle_update_firmware")
    other = next(c for c in chunks if c.symbol == "other")

    in_handler = _span("system(", handler)
    in_other = _span("system(", other)
    assert in_handler is not None and in_other is not None
    assert in_handler.start_line == 10
    assert in_other.start_line == 14


def test_anchor_outside_its_chunk_does_not_match() -> None:
    """A model hallucinating a sink into the wrong function gets nothing."""
    chunks = chunk_source("a.c", SOURCE)
    other = next(c for c in chunks if c.symbol == "other")
    assert locate_anchor("snprintf(cmd", "a.c", SOURCE, other) is None


def test_file_chunk_searches_the_whole_file_not_its_elided_body() -> None:
    """A file chunk's body is synthesized, so offsets in it do not map to disk.

    ``locate`` reads the file instead -- this is the case that would silently
    produce wrong coordinates if it indexed into ``chunk.body``.
    """
    file_chunk = next(c for c in chunk_source("a.c", SOURCE) if c.kind == FILE_CHUNK_KIND)
    assert file_chunk.body_is_verbatim is False
    assert "system(cmd)" not in file_chunk.body, "function bodies are elided from the file chunk"

    span = locate_anchor("char *location;", "a.c", SOURCE, file_chunk)
    assert span is not None
    assert span.span.start_line == 4


def test_strategy_is_reported_so_prompt_drift_is_visible() -> None:
    """A rise in loose matches means the prompt stopped working; record which
    rung matched so that is observable rather than invisible."""
    exact = locate_anchor("system(cmd);", "a.c", SOURCE)
    loose = locate_anchor('"system(cmd);"', "a.c", SOURCE)
    assert exact is not None and exact.strategy == "exact"
    assert loose is not None and loose.strategy == "dequoted"


def test_multiline_span_excerpt_matches_its_coordinates() -> None:
    span = _span("void handle_update_firmware(const Request *req) {\n    char cmd[256];")
    assert span is not None
    assert span.start_line == 6 and span.end_line == 7
    assert _text_at(span) == span.excerpt


def test_locates_against_a_real_fixture_on_disk(fixture_root: Path) -> None:
    """Same guarantee, on real source rather than an inline string."""
    path = fixture_root / "update_firmware.c"
    text = path.read_text(encoding="utf-8")
    chunk = next(c for c in chunk_source("update_firmware.c", text) if c.symbol == "download_firmware")

    located = locate_anchor("system(", "update_firmware.c", text, chunk)
    assert located is not None
    line = text.splitlines()[located.span.start_line - 1]
    assert "system(" in line
    assert line[located.span.start_column - 1 :].startswith("system(")
