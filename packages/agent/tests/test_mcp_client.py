"""The agent as a client of its own MCP server.

Serving the tools over MCP and then importing them directly would defeat the
point, so this exercises the real path: a stdio subprocess, the adapter, and a
blocking call from the sync graph. It is the slowest test here and the only one
that spawns a process, which is the cost of checking the thing that actually
ships rather than a stand-in for it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent.index import ChunkStore, build_index
from agent.mcp.client import VERIFY_TOOLS, ToolSession, open_session, unwrap_tool_result


@pytest.fixture(scope="module")
def indexed_tree(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    """A tiny tree plus its index, built once for the whole module."""
    root = tmp_path_factory.mktemp("mcp-tree")
    (root / "app.c").write_text(
        "#include <stdlib.h>\n"
        'static void run(const char *u) { char c[64]; sprintf(c, "wget %s", u); system(c); }\n'
        "void handle(const char *loc) { run(loc); }\n",
        encoding="utf-8",
    )
    db = root.parent / "index.db"
    store = ChunkStore(db)
    build_index(root, store)
    store.close()
    return root, db


@pytest.fixture(scope="module")
def session(indexed_tree: tuple[Path, Path]):
    root, db = indexed_tree
    opened = open_session(run_root=root, index_db=db, allowed=VERIFY_TOOLS)
    if opened is None:
        pytest.skip("the MCP tool surface would not start")
    yield opened
    opened.close()


def test_the_agent_can_load_its_own_tool_surface(session: ToolSession) -> None:
    """The requirement this design was built around: the agent is a client of
    the same server any other MCP client would connect to."""
    assert session.names(), "no tools were loaded"
    assert "read_source" in session.names()


def test_only_the_verify_subset_is_offered(session: ToolSession) -> None:
    """Verification is about testing one claim; the whole surface invites the
    model to wander."""
    offered = {tool.name for tool in session.tools}
    assert offered <= set(VERIFY_TOOLS)
    assert "list_directory" not in offered


def test_reading_source_round_trips_through_the_subprocess(session: ToolSession) -> None:
    out = session.call("read_source", {"path": "app.c"})
    assert "system(c)" in out


def test_graph_tools_answer_from_the_index(session: ToolSession) -> None:
    """These need AGENT_INDEX_DB to have reached the subprocess."""
    out = session.call("find_callers", {"symbol": "run"})
    assert "handle" in out, out
    assert json.loads(out), "expected a JSON payload from a graph tool"


def test_path_confinement_survives_the_hop(session: ToolSession) -> None:
    """The boundary has to hold through MCP, not only in-process."""
    out = session.call("read_source", {"path": "../../../../etc/passwd"})
    assert out.startswith("error:")
    assert "escapes the run root" in out


def test_an_unknown_tool_is_reported_not_raised(session: ToolSession) -> None:
    assert session.call("no_such_tool", {}).startswith("error:")


def test_a_bad_argument_is_reported_not_raised(session: ToolSession) -> None:
    """A tool failure must not abort an inspection that is minutes in."""
    out = session.call("read_source", {"path": "does-not-exist.c"})
    assert out.startswith("error:")


def test_unwrap_flattens_langchain_content_blocks() -> None:
    """Adapter tools return blocks, not strings; every caller would otherwise
    have to know that."""
    assert unwrap_tool_result("plain") == "plain"
    assert unwrap_tool_result([{"type": "text", "text": "a"}, {"type": "text", "text": "b"}]) == "ab"
    assert unwrap_tool_result(5) == "5"


def test_a_session_that_cannot_start_degrades_instead_of_failing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Tools improve verification; they are not a precondition for it."""
    monkeypatch.setattr("sys.executable", "/nonexistent/python")
    assert open_session(run_root=tmp_path) is None
