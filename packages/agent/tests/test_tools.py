from __future__ import annotations

import pytest

from agent.index import ChunkStore, build_index
from agent.runs import new_run
from agent.tools import (
    ToolError,
    callees_of,
    callers_of,
    definition_of,
    glob_files,
    grep,
    list_dir,
    read_file,
)

TREE = {
    "a.c": "one\ntwo\nthree\nfour\n",
    "sub/b.c": "int x;\nsystem(cmd);\n",
}


@pytest.mark.parametrize(
    "candidate",
    [
        "../outside.txt",
        "../../etc/passwd",
        "sub/../../outside.txt",
        "/etc/passwd",
        "/tmp/x",
    ],
)
def test_paths_leaving_the_tree_are_refused(candidate: str) -> None:
    with pytest.raises(ToolError):
        read_file(TREE, candidate)


def test_glob_only_ever_returns_stored_names() -> None:
    assert glob_files(TREE, "*.c") == ["a.c"]
    assert glob_files(TREE, "**/*.c") == ["a.c", "sub/b.c"]


def test_read_file_line_range_is_one_based_inclusive() -> None:
    assert read_file(TREE, "a.c", start_line=2, end_line=3) == "two\nthree"
    assert read_file(TREE, "a.c").startswith("one\n")


def test_list_dir_marks_directories() -> None:
    assert list_dir(TREE) == ["a.c", "sub/"]
    assert list_dir(TREE, "sub") == ["b.c"]


def test_list_dir_on_a_file_is_an_error() -> None:
    with pytest.raises(ToolError):
        list_dir(TREE, "a.c")


def test_grep_finds_matches_with_line_numbers() -> None:
    hits = grep(TREE, r"system\(")
    assert any(line.startswith("sub/b.c:2:") for line in hits), hits


def test_grep_can_be_narrowed_by_glob() -> None:
    assert grep(TREE, "int", glob="*.c") == []
    assert grep(TREE, "int", glob="**/*.c") == ["sub/b.c:1:int x;"]


def test_grep_with_no_matches_is_empty_not_an_error() -> None:
    assert grep(TREE, "nothing_matches_this") == []


@pytest.fixture
def indexed(tree_files: dict[str, str]) -> ChunkStore:
    run = new_run()
    store = run.store()
    build_index(tree_files, store)
    return store


def test_graph_tools_answer_from_the_link_graph(indexed: ChunkStore) -> None:
    assert [c["symbol"] for c in callers_of(indexed, "inner")] == ["outer"]
    assert [c["symbol"] for c in callees_of(indexed, "outer")] == ["inner"]

    definitions = definition_of(indexed, "log_msg")
    assert [d["file"] for d in definitions] == ["util.c"]
    assert "printf" in definitions[0]["body"]
    indexed.close()


def test_graph_tools_are_empty_for_unknown_symbols(indexed: ChunkStore) -> None:
    assert callers_of(indexed, "no_such_function") == []
    assert definition_of(indexed, "no_such_function") == []
    indexed.close()


def test_agent_mcp_does_not_shadow_the_mcp_library() -> None:
    from agent.mcp.server import mcp as server

    import mcp as library

    assert server.name == "agent-code-tools"
    assert hasattr(library, "types"), "the top-level `mcp` import resolved to agent.mcp"


def test_mcp_server_exposes_the_expected_tools() -> None:
    import asyncio

    from agent.mcp.server import mcp as server

    names = {tool.name for tool in asyncio.run(server.list_tools())}
    assert names == {
        "read_source",
        "list_directory",
        "find_files",
        "search_text",
        "plan_status",
        "search_corpus",
        "search_semantic",
        "find_callers",
        "find_callees",
        "find_definition",
        "graph_neighbours",
        "graph_path",
        "graph_subsystem",
    }


def test_mcp_tools_report_bad_paths_as_text_not_protocol_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    from agent.mcp import server as server_module

    run = new_run()
    run.put_file("a.c", b"int x;\n")
    monkeypatch.setenv(server_module.ENV_RUN_ID, run.run_id)

    assert server_module.read_source("../../etc/passwd").startswith("error:")
    assert server_module.read_source("a.c") == "int x;\n"
