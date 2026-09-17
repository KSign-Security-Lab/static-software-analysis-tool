from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent.index import build_index
from agent.runs import new_run
from agent.mcp.client import VERIFY_TOOLS, ToolSession, open_session, unwrap_tool_result


SOURCE = (
    "#include <stdlib.h>\n"
    'static void run(const char *u) { char c[64]; sprintf(c, "wget %s", u); system(c); }\n'
    "void handle(const char *loc) { run(loc); }\n"
)


@pytest.fixture
def session():
    run = new_run()
    run.put_file("app.c", SOURCE.encode("utf-8"))
    store = run.store()
    build_index(run.file_contents(), store)
    store.close()

    opened = open_session(run.run_id, allowed=VERIFY_TOOLS)
    if opened is None:
        pytest.skip("the MCP tool surface would not start")
    yield opened
    opened.close()


def test_the_agent_can_load_its_own_tool_surface(session: ToolSession) -> None:
    assert session.names(), "no tools were loaded"
    assert "read_source" in session.names()


def test_only_the_verify_subset_is_offered(session: ToolSession) -> None:
    offered = {tool.name for tool in session.tools}
    assert offered <= set(VERIFY_TOOLS)
    assert "list_directory" not in offered


def test_reading_source_round_trips_through_the_subprocess(session: ToolSession) -> None:
    out = session.call("read_source", {"path": "app.c"})
    assert "system(c)" in out


def test_graph_tools_answer_from_the_index(session: ToolSession) -> None:
    out = session.call("find_callers", {"symbol": "run"})
    assert "handle" in out, out
    assert json.loads(out), "expected a JSON payload from a graph tool"


def test_a_path_out_of_the_tree_is_refused_through_the_hop(session: ToolSession) -> None:
    out = session.call("read_source", {"path": "../../../../etc/passwd"})
    assert out.startswith("error:")
    assert "not a file" in out


def test_an_unknown_tool_is_reported_not_raised(session: ToolSession) -> None:
    assert session.call("no_such_tool", {}).startswith("error:")


def test_a_bad_argument_is_reported_not_raised(session: ToolSession) -> None:
    out = session.call("read_source", {"path": "does-not-exist.c"})
    assert out.startswith("error:")


def test_unwrap_flattens_langchain_content_blocks() -> None:
    assert unwrap_tool_result("plain") == "plain"
    assert unwrap_tool_result([{"type": "text", "text": "a"}, {"type": "text", "text": "b"}]) == "ab"
    assert unwrap_tool_result(5) == "5"


def test_a_session_that_cannot_start_degrades_instead_of_failing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("sys.executable", "/nonexistent/python")
    assert open_session(new_run().run_id) is None
