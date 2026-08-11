"""Semantic search over the index.

Skipped without the `rag` extra, which is most installs: it drags in onnxruntime
and downloads a model, and a suite that fails for not having paid that would be
reporting the extra as a defect.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agent.index import ChunkStore, build_index, embed

TREE = {
    "auth.c": """\
typedef struct { int role; } user_t;

int is_authorized(user_t *u) {
    return u && u->role == 2;
}
""",
    "net.c": """\
#include <stdlib.h>
#include <stdio.h>

void download_firmware(const char *url) {
    char cmd[256];
    sprintf(cmd, "wget %s", url);
    system(cmd);
}
""",
}


def test_a_chunk_is_embedded_with_its_name_and_file() -> None:
    """The body alone embeds the same whether the function is called
    `is_authorized` or `f`, and the name is usually the strongest statement of
    intent in the whole unit."""
    document = embed.document_for("auth.c", "is_authorized", "return u->role == 2;")
    assert "is_authorized" in document
    assert "auth.c" in document
    assert "return u->role == 2;" in document


@pytest.fixture
def indexed(tmp_path: Path) -> ChunkStore:
    root = tmp_path / "src"
    root.mkdir()
    for name, body in TREE.items():
        (root / name).write_text(body, encoding="utf-8")
    store = ChunkStore(tmp_path / "index.db")
    build_index(root, store)
    return store


def test_missing_extra_is_reported_rather_than_raised_as_an_import_error(
    indexed: ChunkStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The tool has to be able to say why it cannot answer. An ImportError out
    of a subprocess-hosted MCP server is a traceback nobody sees."""

    def no_fastembed() -> None:
        raise embed.Unavailable("semantic search needs the optional 'rag' extra")

    monkeypatch.setattr(embed, "_embedder", no_fastembed)
    with pytest.raises(embed.Unavailable):
        embed.build(indexed)
    indexed.close()


def test_it_finds_the_check_nobody_could_have_grepped_for(indexed: ChunkStore) -> None:
    """The one question the other tools answer badly.

    `is_authorized` contains none of the words in the query, so `search_text`
    could only find it by being handed the identifier -- which is the thing the
    asker does not have. This is the case the extra exists for.
    """
    pytest.importorskip("fastembed", reason="needs the rag extra")

    assert embed.build(indexed) > 0
    hits = embed.search(indexed, "is there a permission check anywhere?", limit=3)

    assert hits, "nothing came back"
    assert hits[0][2] == "is_authorized", hits
    # Ranked, not merely present: a hit that is only just above the noise is
    # what this cannot promise, and the check query is the one where it can.
    assert hits[0][0] > hits[1][0] + 0.05, hits
    indexed.close()


def test_re_indexing_only_pays_for_what_is_new(indexed: ChunkStore) -> None:
    """A chunk id is content-derived, so an unedited function is already here."""
    pytest.importorskip("fastembed", reason="needs the rag extra")

    first = embed.build(indexed)
    assert first > 0
    assert embed.build(indexed) == 0, "the second pass re-embedded unchanged chunks"
    indexed.close()
