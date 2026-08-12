"""What a specialist is shown, and the one section that can decide a finding.

`scout` narrows a large unit to the stretch worth reading, and in doing so takes
away the lines that make that stretch judgeable. A region holding
``sprintf(cmd, "wget %s", url)`` and not ``char cmd[256];`` leaves the question
the finding turns on unanswerable -- and a model shown it answered anyway, which
is a guess that happened to be right.
"""

from __future__ import annotations

from pathlib import Path

from agent.config import AgentConfig
from agent.context import build_context, declarations_for
from agent.index import ChunkStore, build_index
from agent.index.chunk import chunk_source

BIG = (
    "#include <stdio.h>\n"
    "\n"
    "void handle(const char *url, int n) {\n"
    "    char cmd[256];\n"
    "    int unrelated = 0;\n"
    + "".join(f"    int step{i} = n + {i};\n" for i in range(40))
    + '    sprintf(cmd, "wget %s", url);\n'
    "    system(cmd);\n"
    "}\n"
)


def _handle():
    return next(c for c in chunk_source("big.c", BIG) if c.symbol == "handle")


def test_a_region_carries_what_its_names_were_declared_as() -> None:
    chunk = _handle()
    sink = next(n for n, line in _numbered(chunk) if "sprintf(cmd" in line)

    declared = dict(declarations_for(chunk, sink, sink + 1))
    joined = "\n".join(declared.values())

    assert "char cmd[256];" in joined, "the size the overflow question turns on"
    assert "void handle(const char *url, int n)" in joined, "where url came from"


def test_it_brings_the_signature_even_for_a_region_that_names_no_local() -> None:
    """A region using only a parameter still has to say where it came from."""
    chunk = _handle()
    declared = dict(declarations_for(chunk, chunk.end_line, chunk.end_line))
    assert any("void handle(" in line for line in declared.values())


def test_it_does_not_drag_in_lines_the_region_never_mentions() -> None:
    """First mention, not every mention: the point is a few decisive lines, not
    the unit back again."""
    chunk = _handle()
    sink = next(n for n, line in _numbered(chunk) if "sprintf(cmd" in line)

    declared = dict(declarations_for(chunk, sink, sink + 1))
    assert not any("unrelated" in line for line in declared.values())
    assert not any("step7" in line for line in declared.values())
    assert len(declared) <= 4, declared


def test_a_whole_unit_read_needs_none_of_this() -> None:
    chunk = _handle()
    assert declarations_for(chunk, chunk.start_line, chunk.end_line) == []


def test_the_section_only_appears_when_the_pack_is_a_region(tmp_path: Path) -> None:
    root = tmp_path / "src"
    root.mkdir()
    (root / "big.c").write_text(BIG, encoding="utf-8")
    store = ChunkStore(tmp_path / "index.db")
    build_index(root, store)
    chunk = next(c for c in (store.chunk(i) for i in store.order()) if c.symbol == "handle")
    config = AgentConfig(model="m")

    sink = next(n for n, line in _numbered(chunk) if "sprintf(cmd" in line)
    region = build_context(store, chunk, config, region=(sink, sink + 1))
    assert "char cmd[256];" in region.text
    assert "선언된 곳" in region.text

    whole = build_context(store, chunk, config)
    assert "선언된 곳" not in whole.text, "the unit already contains them"
    store.close()


def _numbered(chunk) -> list[tuple[int, str]]:
    return [(chunk.start_line + i, line) for i, line in enumerate(chunk.body.splitlines())]
