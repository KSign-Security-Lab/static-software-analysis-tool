from __future__ import annotations

from pathlib import Path

from agent.config import AgentConfig
from agent.context import build_context, declarations_for
from conftest import read_tree

from agent.runs import new_run
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
    chunk = _handle()
    declared = dict(declarations_for(chunk, chunk.end_line, chunk.end_line))
    assert any("void handle(" in line for line in declared.values())


def test_it_does_not_drag_in_lines_the_region_never_mentions() -> None:
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
    store = ChunkStore(new_run().run_id)
    build_index(read_tree(root), store)
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


def test_a_replacement_gets_back_the_indentation_the_model_dropped() -> None:
    from agent.remediate import reindent as _reindent

    before = ['    sprintf(cmd, "wget %s", url);']
    assert _reindent('snprintf(cmd, sizeof(cmd), "wget %s", url);', before) == (
        '    snprintf(cmd, sizeof(cmd), "wget %s", url);'
    )


def test_a_replacement_that_indents_itself_is_left_alone() -> None:
    from agent.remediate import reindent as _reindent

    before = ["    do_thing();"]
    proposed = "    if (ok) {\n        do_thing();\n    }"
    assert _reindent(proposed, before) == proposed


def test_blank_lines_in_a_replacement_stay_blank() -> None:
    from agent.remediate import reindent as _reindent

    assert _reindent("a();\n\nb();", ["  x();"]) == "  a();\n\n  b();"


from agent.context import MAX_SIGNATURE_CHARS, _signature  # noqa: E402

TWO_FILES = {
    "src/util.c": (
        "#include <string.h>\n"
        "\n"
        "void copy_into(char *dst, const char *src, int n) {\n"
        "    memcpy(dst, src, n);\n"
        "}\n"
    ),
    "src/app.c": (
        "#include <stdio.h>\n"
        "\n"
        "static int helper(int a) {\n"
        "    return a + 1;\n"
        "}\n"
        "\n"
        "void run(char *out, const char *in) {\n"
        "    helper(1);\n"
        "    copy_into(out, in, 64);\n"
        "}\n"
    ),
}

MULTILINE = (
    "static int wide(int first,   // the first\n"
    "                char *second, /* a buffer */\n"
    "                int third) /* in bytes */\n"
    "{\n"
    "    return third;\n"
    "}\n"
)


def _chunk(source: str, name: str, path: str = "m.c"):
    return next(c for c in chunk_source(path, source) if c.symbol == name)


def test_a_signature_split_over_lines_arrives_whole() -> None:
    assert _signature(_chunk(MULTILINE, "wide")) == "static int wide(int first, char *second, int third)"


def test_a_comment_inside_the_parameter_list_is_not_a_parameter() -> None:
    signature = _signature(_chunk(MULTILINE, "wide"))
    assert "//" not in signature and "/*" not in signature
    assert "the first" not in signature and "in bytes" not in signature


def test_a_one_line_signature_is_unchanged() -> None:
    source = "int plain(char *a, int b) {\n    return b;\n}\n"
    assert _signature(_chunk(source, "plain")) == "int plain(char *a, int b)"


def test_a_runaway_signature_is_cut_and_says_so() -> None:
    params = ", ".join(f"int parameter_number_{n}" for n in range(60))
    source = f"int huge({params}) {{\n    return 0;\n}}\n"
    signature = _signature(_chunk(source, "huge"))

    assert len(signature) <= MAX_SIGNATURE_CHARS + 5
    assert signature.endswith("...)")


def _indexed(tmp_path: Path, files: dict[str, str]):
    root = tmp_path / "tree"
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    store = ChunkStore(new_run().run_id)
    build_index(read_tree(root), store)
    return root, store


def _callee_section(pack) -> str:
    return next((s for s in pack.text.split("\n\n") if "부르는 것들" in s), "")


def test_a_callee_with_no_note_still_reaches_its_caller(tmp_path: Path) -> None:
    _, store = _indexed(tmp_path, TWO_FILES)
    run = next(c for c in store.chunks() if c.symbol == "run")
    section = _callee_section(build_context(store, run, AgentConfig(model="m")))

    assert "void copy_into(char *dst, const char *src, int n)" in section, "cross-file callee"
    assert "src/util.c:" in section, "and where to read the rest of it"
    store.close()


def test_a_note_travels_beside_the_declaration_not_instead_of_it(tmp_path: Path) -> None:
    _, store = _indexed(tmp_path, TWO_FILES)
    run = next(c for c in store.chunks() if c.symbol == "run")
    copy_into = next(c for c in store.chunks() if c.symbol == "copy_into")
    store.set_note(copy_into.chunk_id, "writes n bytes into dst without checking its size")

    section = _callee_section(build_context(store, run, AgentConfig(model="m")))

    assert "writes n bytes into dst" in section
    assert "void copy_into(char *dst, const char *src, int n)" in section
    store.close()


def test_a_callee_nobody_has_read_yet_says_so(tmp_path: Path) -> None:
    _, store = _indexed(tmp_path, TWO_FILES)
    run = next(c for c in store.chunks() if c.symbol == "run")
    section = _callee_section(build_context(store, run, AgentConfig(model="m")))

    assert "아직 분석하지 않았습니다" in section
    store.close()


def test_each_callee_appears_once(tmp_path: Path) -> None:
    _, store = _indexed(tmp_path, TWO_FILES)
    run = next(c for c in store.chunks() if c.symbol == "run")
    section = _callee_section(build_context(store, run, AgentConfig(model="m")))

    assert section.count("copy_into(") == 1
    assert section.count("helper(") == 1
    store.close()


def test_a_file_chunk_is_never_rendered_as_a_callee(tmp_path: Path) -> None:
    _, store = _indexed(tmp_path, TWO_FILES)
    run = next(c for c in store.chunks() if c.symbol == "run")
    section = _callee_section(build_context(store, run, AgentConfig(model="m")))

    assert "#include" not in section
    for line in section.splitlines()[1:]:
        assert not line.startswith("- src/app.c:1 "), "the file chunk itself"
    store.close()


def test_callees_are_dropped_one_at_a_time_and_the_pack_says_so(tmp_path: Path) -> None:
    _, store = _indexed(tmp_path, TWO_FILES)
    run = next(c for c in store.chunks() if c.symbol == "run")
    config = AgentConfig(model="m")
    config.context_window = 0
    config.context_char_budget = 320

    pack = build_context(store, run, config)

    assert "부르는 것들" in pack.text, "the whole section vanished instead of degrading"
    assert "callees" in pack.dropped, "a section went missing without saying so"
    store.close()


def test_the_pack_is_budgeted_against_the_window(tmp_path: Path) -> None:
    _, store = _indexed(tmp_path, TWO_FILES)
    run = next(c for c in store.chunks() if c.symbol == "run")
    config = AgentConfig(model="m")
    config.context_window = 16_384

    pack = build_context(store, run, config)

    assert len(pack.text) <= config.input_chars()
    store.close()
