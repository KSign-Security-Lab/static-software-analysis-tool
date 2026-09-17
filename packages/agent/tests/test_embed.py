from __future__ import annotations

from pathlib import Path

import pytest

from conftest import read_tree

from agent.runs import new_run
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
    store = ChunkStore(new_run().run_id)
    build_index(read_tree(root), store)
    return store


def test_missing_extra_is_reported_rather_than_raised_as_an_import_error(
    indexed: ChunkStore, monkeypatch: pytest.MonkeyPatch
) -> None:

    def no_fastembed() -> None:
        raise embed.Unavailable("semantic search needs the optional 'rag' extra")

    monkeypatch.setattr(embed, "_embedder", no_fastembed)
    with pytest.raises(embed.Unavailable):
        embed.build(indexed)
    indexed.close()


def test_it_finds_the_check_nobody_could_have_grepped_for(indexed: ChunkStore) -> None:
    pytest.importorskip("fastembed", reason="needs the rag extra")

    assert embed.build(indexed) > 0
    hits = embed.search(indexed, "is there a permission check anywhere?", limit=3)

    assert hits, "nothing came back"
    assert hits[0][2] == "is_authorized", hits
    assert hits[0][0] > hits[1][0] + 0.05, hits
    indexed.close()


def test_re_indexing_only_pays_for_what_is_new(indexed: ChunkStore) -> None:
    pytest.importorskip("fastembed", reason="needs the rag extra")

    first = embed.build(indexed)
    assert first > 0
    assert embed.build(indexed) == 0, "the second pass re-embedded unchanged chunks"
    indexed.close()
