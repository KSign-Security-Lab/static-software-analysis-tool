"""The index is the piece everything else stands on, so it is pinned hard.

Chunking, symbol extraction, link resolution and ordering are all deterministic
and LLM-free, which means they can be tested as ordinary functions rather than
sampled. If these pass, a wrong finding is the model's fault; if they fail,
every finding downstream is pointing at the wrong place.
"""

from __future__ import annotations

from pathlib import Path

from agent.index import ChunkStore, build_index, relative_posix
from agent.index.chunk import FILE_CHUNK_KIND, chunk_id_for, chunk_source, line_windows, normalize_body
from agent.index.links import CALLS, FILE_DEPENDS, USES_TYPE, resolve_links
from agent.index.order import call_levels, inspection_order, wave
from agent.languages import spec_for_path


def _chunks(tree: Path) -> list:
    out = []
    for path in sorted(tree.glob("*.c")) + sorted(tree.glob("*.h")):
        out.extend(chunk_source(relative_posix(path, tree), path.read_text(encoding="utf-8")))
    return out


def test_functions_become_their_own_chunks(tree: Path) -> None:
    chunks = _chunks(tree)
    functions = {c.symbol for c in chunks if c.kind != FILE_CHUNK_KIND}
    assert {"inner", "outer", "entry", "ping", "pong", "log_msg"} <= functions


def test_every_file_gets_a_file_chunk(tree: Path) -> None:
    """Struct layouts and globals live here, not in the functions that use them."""
    chunks = _chunks(tree)
    file_chunks = {c.file for c in chunks if c.kind == FILE_CHUNK_KIND}
    assert file_chunks == {"app.c", "util.c", "util.h"}

    header = next(c for c in chunks if c.file == "util.h" and c.kind == FILE_CHUNK_KIND)
    assert "Request" in header.defines, "the typedef must be attributed to the header"


def test_chunk_spans_are_one_based_and_inclusive(tree: Path) -> None:
    """Editors and compilers count from 1; a chunk that counts from 0 puts every
    marker one line high."""
    source = (tree / "app.c").read_text(encoding="utf-8")
    lines = source.splitlines()
    for chunk in chunk_source("app.c", source):
        if chunk.kind == FILE_CHUNK_KIND:
            continue
        assert chunk.start_line >= 1
        assert chunk.symbol in lines[chunk.start_line - 1], (
            f"{chunk.symbol} claims line {chunk.start_line}, which reads {lines[chunk.start_line - 1]!r}"
        )


BIG = "void big(void) {\n" + "\n".join(f"    int v{i} = {i};" for i in range(60)) + "\n}\n"


def _big() -> object:
    return next(c for c in chunk_source("b.c", BIG) if c.symbol == "big")


def test_a_range_renders_the_same_lines_the_whole_body_would() -> None:
    """Absolute numbers, and the same padding however the unit is cut.

    A region is a line range and a Span is a line range, so they have to be the
    same numbers. And the width comes from the whole body: otherwise one line
    arrives as `42|` in one prompt and `042|` in another, and the `NNN| ` the
    prompts promise stops being one thing.
    """
    chunk = _big()
    assert chunk.numbered_body() == chunk.numbered_range(chunk.start_line, chunk.end_line)

    slice_ = chunk.numbered_range(3, 5).splitlines()
    assert len(slice_) == 3
    assert slice_[0].startswith("003| ")
    assert slice_ == chunk.numbered_body().splitlines()[2:5]


def test_a_unit_is_read_in_passes_rather_than_cut_short() -> None:
    """`truncate` is a character prefix cut, so on a large unit whatever reads
    the body never sees the tail. Deciding *where* is worth close reading while
    blind to the end of it is the failure this exists to avoid."""
    chunk = _big()
    body_lines = len(chunk.body.splitlines())

    assert line_windows(chunk, 10_000) == [(chunk.start_line, chunk.start_line + body_lines - 1)], (
        "a unit that fits is one pass"
    )

    windows = line_windows(chunk, 400)
    assert len(windows) > 1, windows
    # Contiguous, and the whole unit: a gap is a region nobody was ever shown.
    assert windows[0][0] == chunk.start_line
    assert windows[-1][1] == chunk.start_line + body_lines - 1
    for (_, before), (after, _) in zip(windows, windows[1:]):
        assert before + 1 == after, windows
    assert sum(last - first + 1 for first, last in windows) == body_lines


def test_a_line_longer_than_the_budget_still_gets_a_pass() -> None:
    """Dropping it would be the cut this is here to avoid."""
    chunk = _big()
    windows = line_windows(chunk, 1)
    assert len(windows) == len(chunk.body.splitlines())
    assert all(first == last for first, last in windows)


def test_verbatim_chunk_body_matches_its_byte_span(tree: Path) -> None:
    """Function chunk bodies are exact slices; file chunk bodies are not.

    A file chunk's body is a synthesized concatenation with function bodies
    elided, so an offset inside it does not map onto the file. It says so via
    ``body_is_verbatim`` -- and ``locate`` reads that flag rather than assuming
    it can index into any chunk body.
    """
    raw = (tree / "app.c").read_bytes()
    chunks = chunk_source("app.c", raw.decode())

    for chunk in chunks:
        if chunk.body_is_verbatim:
            assert chunk.body == raw[chunk.start_byte : chunk.end_byte].decode()

    file_chunk = next(c for c in chunks if c.kind == FILE_CHUNK_KIND)
    assert file_chunk.body_is_verbatim is False
    assert all(c.body_is_verbatim for c in chunks if c.kind != FILE_CHUNK_KIND)


def test_references_exclude_nested_definitions(tree: Path) -> None:
    """A chunk claims only the calls in its own body."""
    chunks = {c.symbol: c for c in _chunks(tree) if c.kind != FILE_CHUNK_KIND}
    assert set(chunks["inner"].references) == {"log_msg", "system"}
    assert set(chunks["outer"].references) == {"inner"}
    assert set(chunks["entry"].references) == {"outer"}


def test_calls_resolve_to_real_definitions(tree: Path) -> None:
    chunks = _chunks(tree)
    by_id = {c.chunk_id: c for c in chunks}
    edges = {(by_id[link.src].symbol, by_id[link.dst].symbol) for link in resolve_links(chunks) if link.kind == CALLS}
    assert ("entry", "outer") in edges
    assert ("outer", "inner") in edges
    assert ("inner", "log_msg") in edges, "cross-file call did not resolve"
    assert not any(dst == "system" for _, dst in edges), "libc is not in the tree; nothing to link to"


def test_type_and_include_links_resolve(tree: Path) -> None:
    chunks = _chunks(tree)
    by_id = {c.chunk_id: c for c in chunks}
    links = resolve_links(chunks)

    type_edges = {(by_id[x.src].symbol, x.symbol) for x in links if x.kind == USES_TYPE}
    assert ("inner", "Request") in type_edges

    include_edges = {(by_id[x.src].file, by_id[x.dst].file) for x in links if x.kind == FILE_DEPENDS}
    assert ("app.c", "util.h") in include_edges
    assert not any(dst.startswith("<") for _, dst in include_edges), "system headers must not resolve"


def test_callees_are_always_inspected_before_callers(tree: Path) -> None:
    """The ordering invariant the whole cross-chunk design depends on.

    Scoped to acyclic edges, because a cycle has no ordering that satisfies it:
    in ``ping <-> pong`` whichever is analysed first necessarily precedes a
    caller. Those edges are excluded here and covered by the mutual-recursion
    test instead. Every *other* edge must hold, and that is the real claim.
    """
    chunks = _chunks(tree)
    links = resolve_links(chunks)
    position = {chunk_id: i for i, chunk_id in enumerate(inspection_order(chunks, links))}
    by_id = {c.chunk_id: c for c in chunks}

    call_edges = {(link.src, link.dst) for link in links if link.kind == CALLS}
    acyclic = [(src, dst) for src, dst in call_edges if (dst, src) not in call_edges]
    assert len(acyclic) < len(call_edges), "fixture no longer contains the mutual-recursion case"

    violations = [(by_id[src].symbol, by_id[dst].symbol) for src, dst in acyclic if position[dst] > position[src]]
    assert violations == [], f"callee analysed after its caller: {violations}"


def test_mutual_recursion_does_not_hang_or_duplicate(tree: Path) -> None:
    """ping/pong is a cycle. It has no valid topological order, so the only
    requirement is that both appear exactly once and the walk terminates."""
    chunks = _chunks(tree)
    order = inspection_order(chunks, resolve_links(chunks))
    assert len(order) == len(set(order)) == len(chunks)


def test_file_chunks_come_first(tree: Path) -> None:
    chunks = _chunks(tree)
    order = inspection_order(chunks, resolve_links(chunks))
    by_id = {c.chunk_id: c for c in chunks}
    kinds = [by_id[cid].kind for cid in order]
    assert kinds[: kinds.count(FILE_CHUNK_KIND)] == [FILE_CHUNK_KIND] * kinds.count(FILE_CHUNK_KIND)


def test_no_two_chunks_at_one_level_call_each_other(tree: Path) -> None:
    """The claim a wave rests on. If it ever fails, two chunks inspected
    concurrently could need each other's note, and the cross-chunk context the
    ordering exists to provide would be silently missing."""
    chunks = _chunks(tree)
    links = resolve_links(chunks)
    levels = call_levels(chunks, links)
    by_id = {c.chunk_id: c for c in chunks}

    clashes = [
        (by_id[link.src].symbol, by_id[link.dst].symbol)
        for link in links
        if link.kind == CALLS and link.src in levels and link.dst in levels and levels[link.src] == levels[link.dst]
    ]
    assert clashes == [], f"a caller and its callee share a level: {clashes}"


def test_every_chunk_gets_a_level_including_a_cycle(tree: Path) -> None:
    chunks = _chunks(tree)
    levels = call_levels(chunks, resolve_links(chunks))
    assert set(levels) == {c.chunk_id for c in chunks}
    assert all(level >= 0 for level in levels.values())


def test_file_chunks_and_leaves_are_level_zero(tree: Path) -> None:
    chunks = _chunks(tree)
    levels = call_levels(chunks, resolve_links(chunks))
    by_id = {c.chunk_id: c for c in chunks}
    assert all(levels[c.chunk_id] == 0 for c in chunks if c.kind == FILE_CHUNK_KIND)
    # `outer` calls `inner`, so it must sit above it.
    inner = next(cid for cid, c in by_id.items() if c.symbol == "inner")
    outer = next(cid for cid, c in by_id.items() if c.symbol == "outer")
    assert levels[outer] > levels[inner]


def test_a_wave_takes_only_chunks_that_share_a_level() -> None:
    levels = {"a": 0, "b": 1, "c": 0, "d": 0}
    assert wave(["a", "b", "c", "d"], levels, width=4) == ["a", "c", "d"]
    assert wave(["b", "a", "c"], levels, width=4) == ["b"]


def test_a_wave_is_bounded_and_degrades_to_one() -> None:
    levels = {name: 0 for name in "abcdef"}
    assert wave(list("abcdef"), levels, width=3) == ["a", "b", "c"]
    assert wave(list("abcdef"), levels, width=1) == ["a"]
    # An index written before levels existed: one at a time, as before.
    assert wave(["a", "b"], {}, width=4) == ["a"]
    assert wave([], levels, width=4) == []


def test_levels_survive_a_round_trip_through_the_store(tmp_path: Path, tree: Path) -> None:
    store = ChunkStore(tmp_path / "index.db")
    build_index(tree, store)
    stored = store.levels()
    store.close()

    chunks = _chunks(tree)
    assert stored == call_levels(chunks, resolve_links(chunks))


def test_chunk_ids_are_stable_across_reindexing(tree: Path) -> None:
    assert [c.chunk_id for c in _chunks(tree)] == [c.chunk_id for c in _chunks(tree)]


def test_chunk_id_ignores_reformatting_but_not_edits() -> None:
    """Reindenting must not invalidate cached findings; editing a token must."""
    original = "void f(void) {\n    g();\n}"
    reindented = "void f(void) {\n        g();\n}"
    edited = "void f(void) {\n    h();\n}"

    assert chunk_id_for("a.c", "f", original) == chunk_id_for("a.c", "f", reindented)
    assert chunk_id_for("a.c", "f", original) != chunk_id_for("a.c", "f", edited)
    assert normalize_body("a  \n\t b") == "a b"


def test_numbered_body_starts_at_the_real_line(tree: Path) -> None:
    """The model is given absolute line numbers, not chunk-relative ones."""
    chunk = next(c for c in _chunks(tree) if c.symbol == "entry")
    first = chunk.numbered_body().splitlines()[0]
    assert first.startswith(f"{chunk.start_line:03d}| ")


def test_unsupported_files_are_not_indexed() -> None:
    assert spec_for_path("notes.txt") is None
    assert spec_for_path("Makefile") is None
    assert chunk_source("notes.txt", "hello") == []
    assert spec_for_path("a.hpp") is not None and spec_for_path("a.hpp").name == "cpp"
    assert spec_for_path("a.h") is not None and spec_for_path("a.h").name == "c"


def test_build_index_round_trips_through_the_store(tree: Path, tmp_path: Path) -> None:
    store = ChunkStore(tmp_path / "out" / "index.db")
    result = build_index(tree, store)

    assert result.files_indexed == 3
    assert result.chunks > 0 and result.links > 0
    assert len(store.order()) == result.chunks
    assert set(store.files()) == {"app.c", "util.c", "util.h"}

    entry = next(c for c in store.chunks() if c.symbol == "entry")
    assert [c.symbol for c in store.callees_of(entry.chunk_id)] == ["outer"]
    outer = next(c for c in store.chunks() if c.symbol == "outer")
    assert [c.symbol for c in store.callers_of(outer.chunk_id)] == ["entry"]
    assert [c.file for c in store.definition_of("Request")] == ["util.h"]
    store.close()


def test_notes_and_inspection_state_persist(tree: Path, tmp_path: Path) -> None:
    """A resumed run must be able to tell 'no findings' from 'not yet analysed'."""
    path = tmp_path / "index.db"
    store = ChunkStore(path)
    build_index(tree, store)
    chunk_id = store.order()[0]
    assert store.is_inspected(chunk_id) is False
    store.set_note(chunk_id, "returns attacker-controlled data")
    store.mark_inspected(chunk_id)
    store.close()

    reopened = ChunkStore(path)
    assert reopened.note(chunk_id) == "returns attacker-controlled data"
    assert reopened.is_inspected(chunk_id) is True
    reopened.close()


def test_sample_tree_indexes_without_ordering_violations(fixture_root: Path, tmp_path: Path) -> None:
    """The same invariants on the shipped sample tree rather than a built one."""
    store = ChunkStore(tmp_path / "index.db")
    result = build_index(fixture_root, store)
    assert result.files_indexed == 5
    assert result.files_skipped == 0

    position = {chunk_id: i for i, chunk_id in enumerate(store.order())}
    violations = [link for link in store.links() if link.kind == CALLS and position[link.dst] > position[link.src]]
    assert violations == []
    store.close()


def test_sample_tree_resolves_its_cross_file_chain(fixture_root: Path, tmp_path: Path) -> None:
    """The chain an inspection has to follow, checked structurally first.

    ``handle_download`` reaches ``system`` only via ``read_param`` in another
    file and ``fetch_firmware`` in this one. If these edges are missing, the
    model is asked to judge a sink with no idea where its argument came from.
    """
    store = ChunkStore(tmp_path / "index.db")
    build_index(fixture_root, store)

    handler = next(c for c in store.chunks() if c.symbol == "handle_download")
    callees = {c.symbol for c in store.callees_of(handler.chunk_id)}
    assert {"read_param", "fetch_firmware", "log_line"} <= callees

    read_param = next(c for c in store.chunks() if c.symbol == "read_param")
    assert read_param.file == "util.c", "cross-file call did not resolve"

    position = {chunk_id: i for i, chunk_id in enumerate(store.order())}
    fetch = next(c for c in store.chunks() if c.symbol == "fetch_firmware")
    assert position[fetch.chunk_id] < position[handler.chunk_id]
    assert position[read_param.chunk_id] < position[handler.chunk_id]
    store.close()


def test_sample_tree_labels_both_halves_of_each_pair(fixture_root: Path) -> None:
    """The fixtures are an eval set, so the ground truth has to be present.

    A run is scored on both rates: flagging the vulnerable half is easy, and
    staying quiet on the guarded half is what actually distinguishes a useful
    analyser.
    """
    text = "\n".join(p.read_text(encoding="utf-8") for p in sorted(fixture_root.glob("*.c")))
    for symbol in ("fetch_firmware", "handle_download", "store_payload"):
        assert f"{symbol} " in text or f"{symbol}(" in text
    assert "VULNERABLE" in text and "SAFE" in text
    assert "f2a" not in text.lower(), "the sample tree must not reference another package's fixtures"


def test_the_store_survives_reads_while_a_run_is_writing(tree: Path, tmp_path: Path) -> None:
    """GET /findings reads a run's store while the inspection thread writes it.

    Each thread opens its own connection -- sqlite3 forbids sharing one -- and
    WAL is what stops them blocking each other.
    """
    import sqlite3
    import threading

    db = tmp_path / "index.db"
    boot = ChunkStore(db)
    build_index(tree, boot)
    boot.close()

    assert sqlite3.connect(db).execute("pragma journal_mode").fetchone()[0] == "wal"

    errors: list[str] = []

    def write() -> None:
        try:
            store = ChunkStore(db)
            for i in range(300):
                store.set_note(f"chunk{i}", "x" * 400)
            store.close()
        except Exception as err:  # noqa: BLE001
            errors.append(f"writer: {err}")

    def read() -> None:
        try:
            for _ in range(300):
                store = ChunkStore(db)
                store.findings()
                list(store.chunks())
                store.close()
        except Exception as err:  # noqa: BLE001
            errors.append(f"reader: {err}")

    threads = [threading.Thread(target=write), *(threading.Thread(target=read) for _ in range(2))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)

    assert errors == []


def test_one_store_serves_many_threads(tmp_path: Path, tree: Path) -> None:
    """A wave of chunks is analysed on LangGraph's pool, and every one of them
    reads and writes the same store. A connection bound to its creator would
    raise `ProgrammingError` the moment a node ran off the main thread."""
    import threading

    store = ChunkStore(tmp_path / "index.db")
    build_index(tree, store)
    ids = store.order()
    errors: list[str] = []

    def work(n: int) -> None:
        try:
            for chunk_id in ids:
                store.set_note(chunk_id, f"note from {n}")
                store.mark_inspected(chunk_id)
                store.chunk(chunk_id)
                store.callees_of(chunk_id)
                store.is_inspected(chunk_id)
        except Exception as err:  # noqa: BLE001
            errors.append(f"{n}: {err}")

    threads = [threading.Thread(target=work, args=(n,)) for n in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)

    assert errors == []
    assert all(store.is_inspected(chunk_id) for chunk_id in ids)
    store.close()


def test_a_wave_prefers_the_head_s_own_subsystem() -> None:
    """Four related functions read better than four strangers, and they share
    callees, so the pack the specialists get is already assembled."""
    levels = {name: 0 for name in "abcd"}
    subsystems = {"a": 1, "b": 2, "c": 1, "d": 2}
    assert wave(list("abcd"), levels, width=3, affinity=subsystems) == ["a", "c", "b"]
    # A preference, not a partition: the rest of the wave still gets filled.
    assert wave(list("abd"), levels, width=3, affinity={"a": 1, "b": 2, "d": 2}) == ["a", "b", "d"]


def test_wave_order_is_still_the_index_s_order_within_a_subsystem() -> None:
    levels = {name: 0 for name in "abcd"}
    same = {name: 7 for name in "abcd"}
    assert wave(list("abcd"), levels, width=4, affinity=same) == ["a", "b", "c", "d"]
