"""Tool behaviour, especially where it refuses.

The input is an arbitrary uploaded archive, so confinement is a real boundary
rather than a formality. Most of these tests are about what the tools decline to
do.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from agent.index import ChunkStore, build_index
from agent.paths import PathEscape, is_within, resolve_within
from agent.tools import (
    ToolError,
    bwrap_available,
    callees_of,
    callers_of,
    definition_of,
    glob_files,
    grep,
    list_dir,
    read_file,
    run_sandboxed,
)


# -- confinement -------------------------------------------------------------


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
def test_paths_escaping_the_root_are_rejected(tmp_path: Path, candidate: str) -> None:
    with pytest.raises(PathEscape):
        resolve_within(tmp_path, candidate)


def test_symlink_out_of_the_tree_is_rejected(tmp_path: Path) -> None:
    """A lexical check would pass this; resolution is what catches it."""
    outside = tmp_path.parent / "secret.txt"
    outside.write_text("secret", encoding="utf-8")
    root = tmp_path / "root"
    root.mkdir()
    (root / "link.txt").symlink_to(outside)

    with pytest.raises(PathEscape):
        resolve_within(root, "link.txt")
    assert is_within(root, root / "link.txt") is False


def test_ordinary_paths_resolve(tmp_path: Path) -> None:
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "a.c").write_text("int main(void){return 0;}", encoding="utf-8")
    assert resolve_within(tmp_path, "sub/a.c").is_file()
    assert resolve_within(tmp_path, "./sub/a.c").is_file()


def test_read_file_refuses_to_escape(tmp_path: Path) -> None:
    with pytest.raises(ToolError):
        read_file(tmp_path, "../../etc/passwd")


def test_glob_does_not_return_symlinks_out_of_the_tree(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside.c"
    outside.write_text("int x;", encoding="utf-8")
    root = tmp_path / "root"
    root.mkdir()
    (root / "real.c").write_text("int y;", encoding="utf-8")
    (root / "link.c").symlink_to(outside)

    assert glob_files(root, "*.c") == ["real.c"]


# -- reading -----------------------------------------------------------------


def test_read_file_line_range_is_one_based_inclusive(tmp_path: Path) -> None:
    (tmp_path / "a.c").write_text("one\ntwo\nthree\nfour\n", encoding="utf-8")
    assert read_file(tmp_path, "a.c", start_line=2, end_line=3) == "two\nthree"
    assert read_file(tmp_path, "a.c").startswith("one\n")


def test_list_dir_marks_directories(tmp_path: Path) -> None:
    (tmp_path / "sub").mkdir()
    (tmp_path / "a.c").write_text("x", encoding="utf-8")
    assert list_dir(tmp_path) == ["a.c", "sub/"]


def test_list_dir_on_a_file_is_an_error(tmp_path: Path) -> None:
    (tmp_path / "a.c").write_text("x", encoding="utf-8")
    with pytest.raises(ToolError):
        list_dir(tmp_path, "a.c")


def test_grep_finds_matches_with_line_numbers(tmp_path: Path) -> None:
    (tmp_path / "a.c").write_text("int x;\nsystem(cmd);\n", encoding="utf-8")
    hits = grep(tmp_path, r"system\(")
    assert any(line.startswith("a.c:2:") for line in hits), hits


def test_grep_with_no_matches_is_empty_not_an_error(tmp_path: Path) -> None:
    (tmp_path / "a.c").write_text("int x;\n", encoding="utf-8")
    assert grep(tmp_path, "nothing_matches_this") == []


# -- graph tools -------------------------------------------------------------


def test_graph_tools_answer_from_the_link_graph(tree: Path, tmp_path: Path) -> None:
    """Exact, unlike grep: a textual mention is not a call."""
    store = ChunkStore(tmp_path / "index.db")
    build_index(tree, store)

    assert [c["symbol"] for c in callers_of(store, "inner")] == ["outer"]
    assert [c["symbol"] for c in callees_of(store, "outer")] == ["inner"]

    definitions = definition_of(store, "log_msg")
    assert [d["file"] for d in definitions] == ["util.c"]
    assert "printf" in definitions[0]["body"]
    store.close()


def test_graph_tools_are_empty_for_unknown_symbols(tree: Path, tmp_path: Path) -> None:
    store = ChunkStore(tmp_path / "index.db")
    build_index(tree, store)
    assert callers_of(store, "no_such_function") == []
    assert definition_of(store, "no_such_function") == []
    store.close()


# -- sandbox -----------------------------------------------------------------


needs_bwrap = pytest.mark.skipif(not bwrap_available(), reason="bubblewrap is not installed")


@needs_bwrap
def test_sandbox_runs_a_command_and_sees_the_tree(tmp_path: Path) -> None:
    (tmp_path / "hello.c").write_text("int main(void){return 0;}", encoding="utf-8")
    result = run_sandboxed(tmp_path, ["cat", "hello.c"], backend="bwrap")
    assert result.exit_code == 0, result.stderr
    assert "int main" in result.stdout


@needs_bwrap
def test_sandbox_denies_network(tmp_path: Path) -> None:
    """A verification step that can phone out is not verification."""
    result = run_sandboxed(
        tmp_path,
        ["python3", "-c", "import socket; socket.create_connection(('1.1.1.1', 53), timeout=3)"],
        backend="bwrap",
        timeout=15,
    )
    assert result.exit_code != 0, "network reached the outside from inside the sandbox"


@needs_bwrap
def test_sandbox_mounts_the_tree_read_only(tmp_path: Path) -> None:
    """A compile step must not be able to rewrite the source it is judging."""
    (tmp_path / "a.c").write_text("int x;", encoding="utf-8")
    result = run_sandboxed(tmp_path, ["sh", "-c", "echo tampered > a.c"], backend="bwrap")
    assert result.exit_code != 0
    assert (tmp_path / "a.c").read_text(encoding="utf-8") == "int x;"


@needs_bwrap
def test_sandbox_enforces_a_timeout(tmp_path: Path) -> None:
    result = run_sandboxed(tmp_path, ["sleep", "30"], backend="bwrap", timeout=2)
    assert result.exit_code == 124
    assert "timed out" in result.stderr


def test_sandbox_can_be_disabled(tmp_path: Path) -> None:
    with pytest.raises(ToolError, match="disabled"):
        run_sandboxed(tmp_path, ["echo", "hi"], backend="none")


def test_unknown_sandbox_backend_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(ToolError, match="unknown sandbox backend"):
        run_sandboxed(tmp_path, ["echo", "hi"], backend="chroot")


def test_empty_command_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(ToolError):
        run_sandboxed(tmp_path, [], backend="bwrap")


# -- the agent.mcp package must not shadow the mcp library -------------------


def test_agent_mcp_does_not_shadow_the_mcp_library() -> None:
    """``agent/mcp/`` and the ``mcp`` distribution share a name.

    Python 3's absolute imports make this safe, but "should be fine" is not
    evidence -- if it ever breaks, it breaks at server startup in a subprocess
    where the traceback is easy to miss.
    """
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
        "search_semantic",
        "find_callers",
        "find_callees",
        "find_definition",
        "graph_neighbours",
        "graph_path",
        "graph_subsystem",
        "run_in_sandbox",
    }


def test_mcp_tools_report_escapes_as_text_not_protocol_errors(tmp_path: Path) -> None:
    """A raised exception looks like a dead tool; a message the model can read
    lets it correct itself."""
    from agent.mcp import server as server_module

    os.environ[server_module.ENV_RUN_ROOT] = str(tmp_path)
    try:
        assert server_module.read_source("../../etc/passwd").startswith("error:")
    finally:
        del os.environ[server_module.ENV_RUN_ROOT]
