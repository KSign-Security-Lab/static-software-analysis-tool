"""The HTTP surface, including the parts that must refuse.

The upload endpoint takes an arbitrary archive from a browser, so the traversal
and zip-bomb cases are not hypothetical. They get as much attention here as the
happy path.
"""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path
from typing import Any, Iterator

import pytest

pytest.importorskip("fastapi", reason="the API extras are not installed")
pytest.importorskip("httpx", reason="fastapi.testclient needs httpx")

from fastapi.testclient import TestClient  # noqa: E402

from agent.config import ENV_MODEL, ENV_RUNS_DIR  # noqa: E402


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """A client whose runs land in a temp directory, not the real artifacts dir."""
    monkeypatch.setenv(ENV_RUNS_DIR, str(tmp_path / "runs"))
    monkeypatch.delenv(ENV_MODEL, raising=False)

    from api.main import app

    with TestClient(app) as test_client:
        yield test_client


def _zip(entries: dict[str, str | bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        for name, content in entries.items():
            zf.writestr(name, content)
    return buffer.getvalue()


SAMPLE = {
    "src/util.h": "typedef struct { char *location; } Request;\n",
    "src/app.c": (
        '#include "util.h"\n'
        "#include <stdlib.h>\n"
        'static void run(const char *u) { char c[64]; sprintf(c, "wget %s", u); system(c); }\n'
        "void handle(Request *r) { run(r->location); }\n"
    ),
}


def _upload(client: TestClient, entries: dict[str, str | bytes] | None = None) -> dict:
    payload = _zip(entries if entries is not None else SAMPLE)
    response = client.post("/agent/runs", files={"files": ("upload.zip", payload, "application/zip")})
    assert response.status_code == 200, response.text
    return response.json()


# -- upload ------------------------------------------------------------------


def test_upload_indexes_and_returns_the_file_list(client: TestClient) -> None:
    body = _upload(client)
    assert body["uploaded"] == 2
    assert body["index"]["files_indexed"] == 2
    assert body["index"]["chunks"] > 0
    assert set(body["files"]) == {"src/app.c", "src/util.h"}


def test_upload_of_loose_files_works_too(client: TestClient) -> None:
    response = client.post(
        "/agent/runs",
        files=[
            ("files", ("a.c", b"void f(void) { }\n", "text/plain")),
            ("files", ("b.c", b"void g(void) { f(); }\n", "text/plain")),
        ],
    )
    assert response.status_code == 200, response.text
    assert response.json()["uploaded"] == 2


@pytest.mark.parametrize(
    "name",
    [
        "../escape.c",
        "../../etc/passwd",
        "/absolute.c",
        "sub/../../escape.c",
    ],
)
def test_zip_traversal_entries_are_rejected(client: TestClient, name: str, tmp_path: Path) -> None:
    """A path-traversal entry must fail the upload, not be quietly renamed."""
    response = client.post(
        "/agent/runs",
        files={"files": ("evil.zip", _zip({name: "int x;"}), "application/zip")},
    )
    assert response.status_code == 400
    assert "unsafe path" in response.json()["detail"]
    assert not (tmp_path / "escape.c").exists()


def test_a_corrupt_archive_is_rejected(client: TestClient) -> None:
    response = client.post("/agent/runs", files={"files": ("x.zip", b"not a zip at all", "application/zip")})
    assert response.status_code == 400


def test_an_empty_upload_is_rejected(client: TestClient) -> None:
    response = client.post("/agent/runs", files={"files": ("empty.zip", _zip({}), "application/zip")})
    assert response.status_code == 400


# -- reading the tree --------------------------------------------------------


def test_files_endpoint_lists_the_whole_tree(client: TestClient) -> None:
    """The run record carries at most two names, which is a label, not a tree.

    Without this the editor could not populate its explorer for a run it had
    not just uploaded -- opening a shared ``?run=`` link showed nothing.
    """
    run_id = _upload(client)["run_id"]
    response = client.get(f"/agent/runs/{run_id}/files")
    assert response.status_code == 200
    body = response.json()
    assert body["run_id"] == run_id
    assert "src/app.c" in body["files"]
    assert body["files"] == sorted(body["files"])


def test_files_endpoint_includes_files_the_indexer_skipped(client: TestClient) -> None:
    """The editor can open a README even though no chunk was ever made of it."""
    run_id = _upload(client)["run_id"]
    client.put(f"/agent/runs/{run_id}/file", json={"path": "notes.txt", "content": "hello\n"})
    assert "notes.txt" in client.get(f"/agent/runs/{run_id}/files").json()["files"]


def test_files_endpoint_404s_for_an_unknown_run(client: TestClient) -> None:
    assert client.get("/agent/runs/nosuchrun/files").status_code == 404


def test_file_endpoint_returns_content_and_a_monaco_language(client: TestClient) -> None:
    run_id = _upload(client)["run_id"]
    response = client.get(f"/agent/runs/{run_id}/file", params={"path": "src/app.c"})
    assert response.status_code == 200
    body = response.json()
    assert "system(c)" in body["content"]
    assert body["language"] == "c"


def test_file_endpoint_refuses_to_escape_the_run(client: TestClient) -> None:
    """This takes a path straight from a query string, so it is a real target."""
    run_id = _upload(client)["run_id"]
    response = client.get(f"/agent/runs/{run_id}/file", params={"path": "../../../../etc/passwd"})
    assert response.status_code == 400


def test_missing_file_is_a_404(client: TestClient) -> None:
    run_id = _upload(client)["run_id"]
    assert client.get(f"/agent/runs/{run_id}/file", params={"path": "src/nope.c"}).status_code == 404


def test_unknown_run_is_a_404(client: TestClient) -> None:
    assert client.get("/agent/runs/deadbeef/spans").status_code == 404
    assert client.get("/agent/runs/../../etc/spans").status_code in (307, 404)


def test_runs_can_be_listed(client: TestClient) -> None:
    run_id = _upload(client)["run_id"]
    listed = client.get("/agent/runs").json()["runs"]
    assert any(run["run_id"] == run_id for run in listed)


# -- inspection --------------------------------------------------------------


def test_health_reports_unconfigured_when_no_model_is_set(client: TestClient) -> None:
    """A missing model must be visible, not discovered at chunk 400 of 600."""
    body = client.get("/agent/health").json()
    assert body["configured"] is False
    assert body["model"] is None


def test_health_does_not_touch_the_network_unless_asked(client: TestClient) -> None:
    """It doubles as a liveness probe, so the default must stay local."""
    body = client.get("/agent/health").json()
    assert "served_models" not in body
    assert "reachable" not in body


def test_health_probe_reports_what_the_endpoint_serves(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """?probe=true answers the question people actually have: is AGENT_MODEL
    one of the ids this server knows about?"""
    import api.agent.meta as routes

    monkeypatch.setattr(routes, "list_models", lambda _url: ["agent", "other"])
    monkeypatch.setenv(ENV_MODEL, "agent")

    body = client.get("/agent/health", params={"probe": "true"}).json()
    assert body["reachable"] is True
    assert body["served_models"] == ["agent", "other"]
    assert body["model_is_served"] is True


def test_health_probe_flags_a_model_the_server_does_not_serve(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The usual first failure: the HF path was used instead of the served id."""
    import api.agent.meta as routes

    monkeypatch.setattr(routes, "list_models", lambda _url: ["agent"])
    monkeypatch.setenv(ENV_MODEL, "Qwen/Qwen2.5-Coder-32B-Instruct")

    body = client.get("/agent/health", params={"probe": "true"}).json()
    assert body["reachable"] is True
    assert body["model_is_served"] is False


def test_health_probe_survives_a_dead_endpoint(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    import api.agent.meta as routes

    monkeypatch.setattr(routes, "list_models", lambda _url: [])
    body = client.get("/agent/health", params={"probe": "true"}).json()
    assert body["reachable"] is False
    assert body["model_is_served"] is False


def test_inspection_without_a_model_fails_the_run_not_the_request(client: TestClient) -> None:
    """Starting is asynchronous, so a config error surfaces on the stream."""
    run_id = _upload(client)["run_id"]
    assert client.post(f"/agent/runs/{run_id}/inspect").status_code == 200

    with client.stream("GET", f"/agent/runs/{run_id}/events") as stream:
        events = _collect_events(stream, limit=6)

    assert "run_failed" in events, events
    assert client.get(f"/agent/runs/{run_id}").json()["status"] == "failed"


def _collect_events(stream, limit: int) -> list[str]:
    names: list[str] = []
    for line in stream.iter_lines():
        if line.startswith("event: "):
            names.append(line.removeprefix("event: ").strip())
            if names[-1] in {"run_failed", "run_finished", "stream_closed"} or len(names) >= limit:
                break
    return names


def test_findings_endpoint_returns_an_empty_report_before_inspection(client: TestClient) -> None:
    run_id = _upload(client)["run_id"]
    body = client.get(f"/agent/runs/{run_id}/findings").json()
    assert body["findings"] == []
    assert body["schema_version"] == "1"


def test_diff_requires_both_runs_to_have_reports(client: TestClient) -> None:
    first = _upload(client)["run_id"]
    second = _upload(client)["run_id"]
    response = client.post(f"/agent/runs/{first}/diff", json={"against": second})
    assert response.status_code == 409


def test_diff_against_an_unknown_run_is_a_404(client: TestClient) -> None:
    run_id = _upload(client)["run_id"]
    assert client.post(f"/agent/runs/{run_id}/diff", json={"against": "nosuchrun"}).status_code == 404


def test_diff_reports_new_fixed_and_unchanged(client: TestClient, tmp_path: Path) -> None:
    """The payoff for content-derived ids, exercised through the wire."""
    from agent.runs import get_run
    from agent.schema import Finding, Remediation, Report, Span

    def make(finding_id: str) -> Finding:
        return Finding(
            id=finding_id,
            chunk_id="c1",
            severity="high",
            confidence=0.9,
            title="t",
            cwe="CWE-78",
            primary=Span(file="src/app.c", start_line=1, start_column=1, end_line=1, end_column=2, excerpt="x"),
            explanation="e",
            remediation=Remediation(summary="s", detail="d"),
            verified=True,
        )

    before_id = _upload(client)["run_id"]
    after_id = _upload(client)["run_id"]

    before = get_run(before_id)
    after = get_run(after_id)
    assert before is not None and after is not None
    before.save_report(Report(run_id=before_id, findings=[make("stays"), make("gone")]))
    after.save_report(Report(run_id=after_id, findings=[make("stays"), make("fresh")]))

    body = client.post(f"/agent/runs/{after_id}/diff", json={"against": before_id}).json()
    assert [f["id"] for f in body["new"]] == ["fresh"]
    assert [f["id"] for f in body["fixed"]] == ["gone"]
    assert [f["id"] for f in body["unchanged"]] == ["stays"]


def test_existing_ssat_routes_still_work(client: TestClient) -> None:
    """Mounting the agent router must not disturb the CPG service."""
    body = client.get("/health").json()
    assert "backends" in body or "status" in body, body


def test_generated_ts_schema_is_shipped_to_the_web_app() -> None:
    """The browser half of the contract has to actually exist on disk."""
    from agent.schema_ts import output_path

    content = output_path().read_text(encoding="utf-8")
    assert "export interface Finding" in content
    assert "GENERATED FILE" in content


def test_openapi_documents_the_agent_routes(client: TestClient) -> None:
    paths = json.loads(client.get("/openapi.json").text)["paths"]
    for route in (
        "/agent/runs",
        "/agent/runs/{run_id}/file",
        "/agent/runs/{run_id}/inspect",
        "/agent/runs/{run_id}/events",
        "/agent/runs/{run_id}/findings",
        "/agent/runs/{run_id}/diff",
        "/agent/runs/{run_id}/state",
        "/agent/runs/{run_id}/resume",
    ):
        assert route in paths, f"{route} is missing from the OpenAPI document"


# -- editing a run in place (the agent section's light IDE) ------------------


def test_an_empty_run_can_be_created_and_pasted_into(client: TestClient) -> None:
    """Trying one snippet must not require saving a file and uploading it."""
    run_id = client.post("/agent/runs/new").json()["run_id"]
    assert any(run["run_id"] == run_id for run in client.get("/agent/runs").json()["runs"])

    body = client.put(
        f"/agent/runs/{run_id}/file",
        json={"path": "main.c", "content": "void f(void) { g(); }\n"},
    ).json()
    assert body["files"] == ["main.c"]
    assert body["index"]["chunks"] > 0


def test_editing_a_file_reindexes_it(client: TestClient) -> None:
    """The chunk store is what the inspection walks, so a stale index would
    have it analysing code that is no longer there."""
    run_id = client.post("/agent/runs/new").json()["run_id"]
    client.put(f"/agent/runs/{run_id}/file", json={"path": "a.c", "content": "void one(void) { }\n"})
    after = client.put(
        f"/agent/runs/{run_id}/file",
        json={"path": "a.c", "content": "void one(void) { }\nvoid two(void) { one(); }\n"},
    ).json()

    assert after["index"]["chunks"] == 3  # file chunk + two functions
    assert "two" in client.get(f"/agent/runs/{run_id}/file", params={"path": "a.c"}).json()["content"]


def test_adding_and_deleting_files_tracks_the_tree(client: TestClient) -> None:
    run_id = client.post("/agent/runs/new").json()["run_id"]
    client.put(f"/agent/runs/{run_id}/file", json={"path": "a.c", "content": "void a(void) { }\n"})
    added = client.put(f"/agent/runs/{run_id}/file", json={"path": "b.c", "content": "void b(void) { }\n"}).json()
    assert added["files"] == ["a.c", "b.c"]

    removed = client.request("DELETE", f"/agent/runs/{run_id}/file", params={"path": "b.c"}).json()
    assert removed["files"] == ["a.c"]
    assert client.get(f"/agent/runs/{run_id}/file", params={"path": "b.c"}).status_code == 404


@pytest.mark.parametrize("path", ["../escape.c", "../../etc/passwd", "/abs.c"])
def test_writing_outside_the_run_is_rejected(client: TestClient, path: str, tmp_path: Path) -> None:
    """The path comes from a browser, so this is a real boundary."""
    run_id = client.post("/agent/runs/new").json()["run_id"]
    response = client.put(f"/agent/runs/{run_id}/file", json={"path": path, "content": "x"})
    assert response.status_code == 400
    assert not (tmp_path / "escape.c").exists()


def test_deleting_a_file_drops_its_findings(client: TestClient) -> None:
    """A finding pointing at a file that no longer exists cannot be opened."""
    from agent.runs import get_run

    run_id = client.post("/agent/runs/new").json()["run_id"]
    client.put(f"/agent/runs/{run_id}/file", json={"path": "a.c", "content": "void a(void) { }\n"})

    paths = get_run(run_id)
    assert paths is not None
    store = paths.store()
    store.add_findings("chunk1", [{"id": "f1", "primary": {"file": "a.c"}}])
    assert len(store.findings()) == 1
    store.close()

    client.request("DELETE", f"/agent/runs/{run_id}/file", params={"path": "a.c"})
    store = paths.store()
    assert store.findings() == []
    store.close()


# -- local traces --------------------------------------------------------------


def test_spans_are_empty_before_an_inspection(client: TestClient) -> None:
    run_id = _upload(client)["run_id"]
    body = client.get(f"/agent/runs/{run_id}/spans").json()

    assert body["spans"] == []
    assert body["summary"]["spans"] == 0


def test_spans_endpoint_serves_the_recorded_tree(client: TestClient) -> None:
    """What the debug view reads: a tree, with counts already totalled."""
    from agent.runs import get_run

    run_id = _upload(client)["run_id"]
    paths = get_run(run_id)
    assert paths is not None

    spans = paths.spans()
    spans.start(span_id="root", parent_id=None, name="LangGraph", kind="chain", started_at=0.0)
    spans.start(span_id="llm", parent_id="root", name="analyse:run", kind="llm", started_at=0.0)
    spans.finish(span_id="llm", ended_at=1.5, outputs={"text": ["ok"]}, tokens=200)
    spans.start(span_id="tool", parent_id="llm", name="read_source", kind="tool", started_at=1.5)
    spans.finish(span_id="tool", ended_at=1.6, error="no such file")
    spans.close()

    body = client.get(f"/agent/runs/{run_id}/spans").json()

    assert [span["id"] for span in body["spans"]] == ["root", "llm", "tool"]
    assert body["spans"][1]["latency_ms"] == 1500
    assert body["summary"] == {
        "spans": 3,
        "llm_calls": 1,
        "tool_calls": 1,
        "errors": 1,
        "running": 1,
        "tokens": 200,
        "total_ms": 1600,
    }


def test_spans_of_an_unknown_run_is_a_404(client: TestClient) -> None:
    assert client.get("/agent/runs/deadbeef/spans").status_code == 404


def test_graph_endpoint_answers_before_any_run(client: TestClient) -> None:
    body = client.get("/agent/graph").json()
    assert "plan" in body["nodes"] and "verify" in body["nodes"]
    assert body["mermaid"].startswith("---")


def test_graph_endpoint_says_what_each_step_is_given_and_may_reach_for(client: TestClient) -> None:
    """The half of "what did the agent do" that no trace can answer: a tool that
    was offered and never called leaves no span behind."""
    steps = {entry["step"]: entry for entry in client.get("/agent/graph").json()["steps"]}

    assert steps["triage"]["schema"] == "Triage"
    assert steps["lens:memory"]["prompt"] == "lens:memory"
    assert steps["gather"]["node"] == "gather", "retrieval is a node, not a half of one"
    assert [tool["name"] for tool in steps["gather"]["tools"]][:1] == ["read_source"]
    assert all(not entry["tools"] for step, entry in steps.items() if step != "gather")


def test_thread_groups_model_calls_into_one_conversation_per_chunk(client: TestClient) -> None:
    """The span tree shows the machinery; this shows the exchange."""
    from agent.runs import get_run

    run_id = _upload(client)["run_id"]
    paths = get_run(run_id)
    assert paths is not None

    spans = paths.spans()
    # `langgraph_node` is set by LangGraph on everything running inside a node,
    # so a real span carries it alongside the metadata `call_config` adds.
    meta = {
        "chunk_id": "c1",
        "symbol": "run",
        "file": "src/app.c",
        "langgraph_node": "verify",
        "lens": "injection",
    }
    spans.start(span_id="node", parent_id=None, name="verify", kind="chain", started_at=0.0)
    spans.start(
        span_id="llm",
        parent_id="node",
        name="gather:CWE-78",
        kind="llm",
        started_at=0.0,
        inputs={"messages": [{"role": "system", "content": "be strict"}, {"role": "human", "content": "check"}]},
        meta={**meta, "step": "gather"},
    )
    spans.finish(span_id="llm", ended_at=1.0, outputs={"tool_calls": [{"name": "read_source"}]}, tokens=90)
    spans.start(span_id="tool", parent_id="llm", name="read_source", kind="tool", started_at=1.0, inputs={"p": "a.c"})
    spans.finish(span_id="tool", ended_at=1.4, outputs="int main(void)")
    spans.close()

    (thread,) = client.get(f"/agent/runs/{run_id}/thread").json()["threads"]

    assert thread["symbol"] == "run"
    assert thread["tokens"] == 90
    (turn,) = thread["turns"]
    assert turn["step"] == "gather"
    assert [m["role"] for m in turn["messages"]] == ["system", "human"]
    assert turn["node"] == "verify", "the node, so narrowing the record is not a guess at the name"
    assert turn["raised_by"] == "injection", "which specialist raised the claim this call is about"
    # The tool the model asked for, and what running it returned -- the pair is
    # what makes a verify step readable.
    assert turn["tool_calls"][0]["name"] == "read_source"
    assert turn["tools"][0]["outputs"] == "int main(void)"
    assert turn["tools"][0]["latency_ms"] == 400


def test_thread_and_checkpoints_are_empty_before_an_inspection(client: TestClient) -> None:
    run_id = _upload(client)["run_id"]
    assert client.get(f"/agent/runs/{run_id}/thread").json()["threads"] == []
    assert client.get(f"/agent/runs/{run_id}/checkpoints").json()["count"] == 0


def test_checkpoints_of_an_unknown_run_is_a_404(client: TestClient) -> None:
    assert client.get("/agent/runs/deadbeef/checkpoints").status_code == 404
    assert client.get("/agent/runs/deadbeef/thread").status_code == 404


# -- the studio: breakpoints, state and resume --------------------------------


def test_graph_endpoint_names_the_nodes_a_breakpoint_may_use(client: TestClient) -> None:
    """The studio offers these as checkboxes, so they have to be the real set."""
    body = client.get("/agent/graph").json()

    assert set(body["steppable"]) == {
        "plan",
        "context",
        "triage",
        "scout",
        "memory",
        "injection",
        "access",
        "crypto",
        "logic",
        "skip",
        "locate",
        "gather",
        "verify",
        "reduce",
    }
    # LangGraph's own markers are in `nodes` and are not somewhere to stop.
    assert "__start__" not in body["steppable"]


def test_a_misspelled_breakpoint_is_refused_before_the_run_starts(client: TestClient) -> None:
    """A breakpoint that silently never fires is worse than an error."""
    run_id = _upload(client)["run_id"]
    response = client.post(f"/agent/runs/{run_id}/inspect", json={"breakpoints": ["analyze"]})

    assert response.status_code == 400
    assert "analyze" in response.json()["detail"]


def test_state_before_any_run_is_a_404_not_an_empty_state(client: TestClient) -> None:
    """Nothing to show and nothing to edit are the same answer here."""
    run_id = _upload(client)["run_id"]
    assert client.get(f"/agent/runs/{run_id}/state").status_code == 404
    assert client.get("/agent/runs/deadbeef/state").status_code == 404


def test_writing_state_with_no_history_is_refused(client: TestClient) -> None:
    run_id = _upload(client)["run_id"]
    response = client.post(f"/agent/runs/{run_id}/state", json={"values": {"pending": []}})

    assert response.status_code == 409


def test_writing_state_as_an_unknown_node_is_refused(client: TestClient) -> None:
    run_id = _upload(client)["run_id"]
    response = client.post(
        f"/agent/runs/{run_id}/state",
        json={"values": {"pending": []}, "as_node": "analyze"},
    )

    assert response.status_code == 400


def test_resuming_a_run_that_is_not_stopped_is_refused(client: TestClient) -> None:
    """Nothing is in flight and there is no history, so there is nowhere to go."""
    run_id = _upload(client)["run_id"]
    response = client.post(f"/agent/runs/{run_id}/resume", json={})

    assert response.status_code == 409


def test_resume_rejects_an_action_it_does_not_know(client: TestClient) -> None:
    run_id = _upload(client)["run_id"]
    assert client.post(f"/agent/runs/{run_id}/resume", json={"action": "rewind"}).status_code == 400


def test_state_and_resume_of_an_unknown_run_are_404(client: TestClient) -> None:
    assert client.post("/agent/runs/deadbeef/resume", json={}).status_code == 404
    assert client.post("/agent/runs/deadbeef/state", json={"values": {}}).status_code == 404


def test_state_can_be_read_and_branched_over_a_real_history(client: TestClient) -> None:
    """The round trip the studio's editor makes: read a step, write it back."""
    from agent.config import AgentConfig
    from agent.graph.build import run_inspection
    from agent.runs import get_run

    run_id = client.post("/agent/runs/new").json()["run_id"]
    client.put(f"/agent/runs/{run_id}/file", json={"path": "a.c", "content": "void one(void) { }\n"})
    paths = get_run(run_id)
    assert paths is not None

    store = paths.store()
    try:
        run_inspection(
            run_id=run_id,
            root=paths.source,
            store=store,
            config=AgentConfig(model="fake", enable_tools=False),
            caller=_SilentCaller(),
            checkpoints=paths.checkpoint_db,
        )
    finally:
        store.close()

    state = client.get(f"/agent/runs/{run_id}/state").json()
    # Full values, not the summary the timeline gets: a count cannot be edited
    # back into a list.
    assert isinstance(state["values"]["pending"], list)

    history = client.get(f"/agent/runs/{run_id}/checkpoints").json()["checkpoints"]
    target = next(h for h in history if h["node"] == "plan")
    written = client.post(
        f"/agent/runs/{run_id}/state",
        json={"values": {"pending": ["made-up"]}, "checkpoint_id": target["checkpoint_id"]},
    ).json()

    branched = client.get(f"/agent/runs/{run_id}/state", params={"checkpoint_id": written["checkpoint_id"]}).json()
    assert branched["values"]["pending"] == ["made-up"]
    # The line it was branched off is still there, and still says what it said.
    assert branched["parent_checkpoint_id"] == target["checkpoint_id"]
    assert len(client.get(f"/agent/runs/{run_id}/checkpoints").json()["checkpoints"]) == len(history) + 1


class _SilentCaller:
    """A model that finds nothing, so a run finishes without one being served."""

    def call(self, schema: Any, system: str, user: str, trace: Any = None) -> Any:
        from agent.schema import ChunkAnalysis, Verdict

        if schema is ChunkAnalysis:
            return ChunkAnalysis()
        if schema is Verdict:
            return Verdict(refuted=False, reason="holds", confidence=0.9)
        return None

    def gather(self, system: str, user: str, session: Any, budget: int, trace: Any = None) -> str:
        return ""


def test_watching_a_run_does_not_make_it_look_started(client: TestClient) -> None:
    """The studio opens the stream when a run is picked, before anyone presses
    start. If that read as in flight, the run could never be started at all."""
    import api.agent.channels as routes

    run_id = _upload(client)["run_id"]
    # What GET /events does on connect.
    routes._channel(run_id)

    body = client.post(f"/agent/runs/{run_id}/inspect", json={}).json()
    assert body["already_running"] is False


def test_starting_a_run_keeps_an_existing_watcher_attached(client: TestClient) -> None:
    """The watcher holds the channel object, so a new worker reuses it rather
    than swapping in one nothing writes to."""
    import api.agent.channels as routes

    run_id = _upload(client)["run_id"]
    watched = routes._channel(run_id)

    client.post(f"/agent/runs/{run_id}/inspect", json={})

    assert routes._channel(run_id) is watched
    assert watched.claimed is True


def test_reclaiming_a_channel_drops_the_last_attempt(client: TestClient) -> None:
    """Replaying the previous attempt's events would describe work about to be
    redone, and its finished flag would end the new stream immediately."""
    from api.agent.channels import RunChannel

    channel = RunChannel()
    with channel.listen() as events:
        channel.publish({"event": "stale", "data": {}})
        channel.commands.put({"action": "resume"})
        channel.finished.set()
        channel.waiting.set()
        channel.error = "the last one blew up"

        channel.reclaim()

        assert events.empty() and channel.commands.empty()
    assert not channel.finished.is_set() and not channel.waiting.is_set()
    assert channel.error is None and channel.claimed is True


def test_every_listener_gets_every_event(client: TestClient) -> None:
    """Two readers must each see the whole run, not half of it each.

    The channel used to be one queue that each reader popped from, so a second
    browser tab watching the same run silently took frames away from the first.
    """
    from api.agent.channels import RunChannel

    channel = RunChannel()
    with channel.listen() as first, channel.listen() as second:
        channel.publish({"event": "node_started", "data": {"node": "plan"}})
        channel.publish({"event": "node_finished", "data": {"node": "plan"}})

        for events in (first, second):
            assert [events.get_nowait()["event"] for _ in range(2)] == ["node_started", "node_finished"]
            assert events.empty()


def test_a_listener_stops_receiving_once_it_detaches(client: TestClient) -> None:
    from api.agent.channels import RunChannel

    channel = RunChannel()
    with channel.listen() as first:
        with channel.listen():
            assert channel.listeners == 2
        assert channel.listeners == 1

        channel.publish({"event": "checkpoint", "data": {}})
        assert first.get_nowait()["event"] == "checkpoint"
    assert channel.listeners == 0


def test_publishing_with_nobody_attached_is_dropped(client: TestClient) -> None:
    """Not buffered: the stream is documented as unreplayable, clients read
    their state over REST, and an unbounded backlog for a listener that may
    never arrive is a leak."""
    from api.agent.channels import RunChannel

    channel = RunChannel()
    channel.publish({"event": "node_started", "data": {}})

    with channel.listen() as events:
        assert events.empty()


# -- tuning a prompt against a real trace -------------------------------------


def _recorded_llm_span(client: TestClient, step: str = "lens:memory") -> tuple[str, str]:
    """A run with one recorded model call, as a finished inspection leaves."""
    from agent.runs import get_run

    run_id = _upload(client)["run_id"]
    paths = get_run(run_id)
    assert paths is not None

    spans = paths.spans()
    spans.start(
        span_id="llm-1",
        parent_id=None,
        name=f"{step}:run",
        kind="llm",
        started_at=0.0,
        inputs={"messages": [{"role": "system", "content": "BE STRICT"}, {"role": "human", "content": "int x;"}]},
        meta={"step": step},
    )
    spans.finish(span_id="llm-1", ended_at=1.0, outputs={"text": ["nothing found"]}, tokens=10)
    spans.close()
    return run_id, "llm-1"


def test_prompts_start_as_the_shipped_defaults(client: TestClient, tmp_path: Path) -> None:
    from agent.promptstore import DEFAULTS

    rows = {row["name"]: row for row in client.get("/agent/prompts").json()["prompts"]}

    assert set(rows) == set(DEFAULTS)
    assert all(row["override"] is None for row in rows.values())
    assert rows["lens:memory"]["in_use"] == DEFAULTS["lens:memory"]


def test_a_tuned_prompt_is_saved_and_revertible(client: TestClient, monkeypatch, tmp_path: Path) -> None:
    from agent.config import ENV_PROMPTS_FILE

    monkeypatch.setenv(ENV_PROMPTS_FILE, str(tmp_path / "prompts.json"))

    saved = client.put("/agent/prompts/lens:memory", json={"text": "Only memory errors."}).json()
    rows = {row["name"]: row for row in saved["prompts"]}
    assert rows["lens:memory"]["override"] == "Only memory errors."
    assert rows["lens:memory"]["in_use"] == "Only memory errors."

    reverted = client.delete("/agent/prompts/lens:memory").json()
    assert {r["name"]: r for r in reverted["prompts"]}["lens:memory"]["override"] is None


def test_an_unknown_or_empty_prompt_is_refused(client: TestClient, monkeypatch, tmp_path: Path) -> None:
    from agent.config import ENV_PROMPTS_FILE

    monkeypatch.setenv(ENV_PROMPTS_FILE, str(tmp_path / "prompts.json"))

    assert client.put("/agent/prompts/analyze", json={"text": "x"}).status_code == 404
    assert client.delete("/agent/prompts/analyze").status_code == 404
    assert client.put("/agent/prompts/lens:memory", json={"text": "  "}).status_code == 400


def test_replaying_a_span_that_is_not_a_model_call_is_refused(client: TestClient) -> None:
    from agent.runs import get_run

    run_id = _upload(client)["run_id"]
    paths = get_run(run_id)
    assert paths is not None
    spans = paths.spans()
    spans.start(span_id="node", parent_id=None, name="analyse", kind="chain", started_at=0.0)
    spans.finish(span_id="node", ended_at=1.0)
    spans.close()

    response = client.post(f"/agent/runs/{run_id}/spans/node/replay", json={})
    assert response.status_code == 400
    assert "model call" in response.json()["detail"]


def test_replaying_an_unknown_span_is_a_404(client: TestClient) -> None:
    run_id, _ = _recorded_llm_span(client)

    assert client.post(f"/agent/runs/{run_id}/spans/nope/replay", json={}).status_code == 404
    assert client.post("/agent/runs/deadbeef/spans/x/replay", json={}).status_code == 404


def test_replaying_without_a_model_configured_says_so(client: TestClient) -> None:
    """A 409 rather than a crashed request: the fix is configuration."""
    run_id, span_id = _recorded_llm_span(client)

    response = client.post(f"/agent/runs/{run_id}/spans/{span_id}/replay", json={})
    assert response.status_code == 409
    assert "AGENT_MODEL" in response.json()["detail"]


def test_a_replay_leaves_the_recorded_run_alone(client: TestClient, monkeypatch) -> None:
    """The whole basis of the tuning loop: try a prompt ten times without
    turning the run you are studying into a scratchpad."""
    import api.agent.trace as routes
    from agent.runs import get_run

    run_id, span_id = _recorded_llm_span(client)
    monkeypatch.setenv(ENV_MODEL, "fake")

    class FakeCaller:
        def __init__(self, config) -> None:  # noqa: ANN001
            self.llm = self

        def call(self, schema, system, user, trace=None):  # noqa: ANN001
            return schema(findings=[], note=f"saw: {system[:12]}")

    monkeypatch.setattr(routes, "StructuredCaller", FakeCaller)

    body = client.post(
        f"/agent/runs/{run_id}/spans/{span_id}/replay",
        json={"system": "BE LENIENT"},
    ).json()

    assert body["edited"] is True
    assert body["step"] == "lens:memory"
    assert body["output"]["note"] == "saw: BE LENIENT"
    # What it is being compared against comes back with it.
    assert body["recorded"]["system"] == "BE STRICT"
    assert body["recorded"]["output"] == {"text": ["nothing found"]}

    # The trace is untouched: still one span, still saying what it said.
    paths = get_run(run_id)
    assert paths is not None
    spans = paths.spans()
    try:
        rows = spans.spans()
    finally:
        spans.close()
    assert len(rows) == 1
    assert rows[0].outputs == {"text": ["nothing found"]}


def test_an_unedited_replay_reuses_what_the_span_recorded(client: TestClient, monkeypatch) -> None:
    import api.agent.trace as routes

    run_id, span_id = _recorded_llm_span(client)
    monkeypatch.setenv(ENV_MODEL, "fake")

    seen: dict[str, str] = {}

    class FakeCaller:
        def __init__(self, config) -> None:  # noqa: ANN001
            self.llm = self

        def call(self, schema, system, user, trace=None):  # noqa: ANN001
            seen.update(system=system, user=user)
            return schema(findings=[], note="")

    monkeypatch.setattr(routes, "StructuredCaller", FakeCaller)

    body = client.post(f"/agent/runs/{run_id}/spans/{span_id}/replay", json={}).json()

    assert seen == {"system": "BE STRICT", "user": "int x;"}
    assert body["edited"] is False


# -- picking a run out of a list ----------------------------------------------


def test_a_run_is_labelled_by_its_files_not_its_id(client: TestClient) -> None:
    """A run id is random hex. What anyone recognises is the code in it."""
    run_id = _upload(client)["run_id"]

    run = next(r for r in client.get("/agent/runs").json()["runs"] if r["run_id"] == run_id)
    assert set(run["files"]) <= {"app.c", "util.h"}
    assert run["file_count"] == 2
    assert run["updated_at"] > 0


def test_runs_are_listed_most_recently_touched_first(client: TestClient) -> None:
    """Sorted by id, a list of random hex is shuffled into a meaningless order."""
    import os
    import time

    from agent.runs import get_run

    first = _upload(client)["run_id"]
    second = _upload(client)["run_id"]
    # Timestamps can land in the same tick on a fast filesystem.
    later = time.time() + 10
    paths = get_run(second)
    assert paths is not None
    os.utime(paths.meta_path, (later, later))

    listed = [r["run_id"] for r in client.get("/agent/runs").json()["runs"]]
    assert listed.index(second) < listed.index(first)


def test_a_run_that_never_ran_is_marked_as_such(client: TestClient) -> None:
    """It has no trace to read, so the list can fold it away rather than
    padding itself with workspaces someone abandoned."""
    run_id = _upload(client)["run_id"]

    run = next(r for r in client.get("/agent/runs").json()["runs"] if r["run_id"] == run_id)
    assert run["started"] is False


def test_a_run_can_be_deleted(client: TestClient) -> None:
    from agent.runs import get_run

    run_id = _upload(client)["run_id"]
    paths = get_run(run_id)
    assert paths is not None
    assert paths.base.is_dir()

    assert client.delete(f"/agent/runs/{run_id}").json()["deleted"] == run_id
    assert not paths.base.exists()
    assert all(r["run_id"] != run_id for r in client.get("/agent/runs").json()["runs"])


def test_deleting_an_unknown_run_is_a_404(client: TestClient) -> None:
    assert client.delete("/agent/runs/deadbeef").status_code == 404


def test_a_run_in_flight_is_not_deleted_from_under_its_worker(client: TestClient) -> None:
    import api.agent.channels as routes

    run_id = _upload(client)["run_id"]
    channel = routes._channel(run_id)
    channel.claimed = True

    response = client.delete(f"/agent/runs/{run_id}")
    assert response.status_code == 409
    assert "in flight" in response.json()["detail"]


def _run_with_status(status: str) -> str:
    """A run workspace recorded in one state, with nothing behind it."""
    from agent.runs import new_run

    paths = new_run()
    paths.write_meta(status=status, index={}, uploaded=0)
    return paths.run_id


def test_startup_fails_the_runs_no_process_is_left_to_finish(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A run recorded as in flight at startup belongs to a process that is gone.

    Its worker was a thread here and its progress channel was in-process, so
    nothing can resume it and nothing will ever finish it. Left alone it reads
    as running for ever -- which is the one thing a status is for.
    """
    monkeypatch.setenv(ENV_RUNS_DIR, str(tmp_path / "runs"))
    monkeypatch.delenv(ENV_MODEL, raising=False)

    from agent.runs import get_run

    inspecting = _run_with_status("inspecting")
    interrupted = _run_with_status("interrupted")
    finished = _run_with_status("done")

    from api.main import app

    with TestClient(app) as client:
        statuses = {run["run_id"]: run["status"] for run in client.get("/agent/runs").json()["runs"]}

    assert statuses[inspecting] == "failed"
    assert statuses[interrupted] == "failed"
    # Anything already settled is left exactly as it was.
    assert statuses[finished] == "done"

    paths = get_run(interrupted)
    assert paths is not None
    meta = paths.read_meta()
    assert "다시 시작" in meta["error"]
    # The breakpoint position goes with it: there is no worker parked there.
    assert meta["parked"] is None


def test_a_second_inspection_of_unchanged_code_is_declined(client: TestClient) -> None:
    """Pressing 검사 실행 again must not throw away the trace to do nothing.

    A chunk id is derived from its content, so an unchanged tree has nothing
    left to analyse -- and a fresh start resets the debug record first. The run
    therefore called no model, found nothing, and destroyed the call history of
    the run that did the work. Declining is the whole fix; `force` is how you
    ask for the work anyway.
    """
    from agent.runs import get_run

    run_id = _upload(client)["run_id"]
    paths = get_run(run_id)
    assert paths is not None

    # Stand in for a completed inspection: every chunk has a result, and a
    # trace exists. Both are what the route reads.
    store = paths.store()
    chunk_ids = store.order()
    assert chunk_ids, "the fixture upload should index at least one chunk"
    for chunk_id in chunk_ids:
        store.mark_inspected(chunk_id)
    assert store.uninspected() == []
    store.close()
    paths.spans().close()  # creates the trace database

    declined = client.post(f"/agent/runs/{run_id}/inspect").json()
    assert declined["nothing_to_do"] is True
    assert declined["already_running"] is False

    # `force` is not declined -- it is the request to do the work regardless.
    forced = client.post(f"/agent/runs/{run_id}/inspect", json={"force": True}).json()
    assert "nothing_to_do" not in forced


def test_an_uninspected_chunk_still_starts_a_run(client: TestClient) -> None:
    """The decline is about there being nothing to do, not about having run before."""
    run_id = _upload(client)["run_id"]
    accepted = client.post(f"/agent/runs/{run_id}/inspect").json()
    assert "nothing_to_do" not in accepted


# -- applying a proposed fix --------------------------------------------------
#
# This writes to the user's source, so the refusals matter more than the happy
# path: every one of them is a way of corrupting a file rather than failing.


def _report_with_fix(paths, *, replacement: str | None, excerpt: str, start: int, end: int) -> None:
    from agent.schema import Finding, Remediation, Report, Span

    report = Report(
        run_id=paths.run_id,
        findings=[
            Finding(
                id="f1",
                chunk_id="c1",
                severity="high",
                confidence=0.9,
                title="셸로 넘어가는 입력",
                cwe="CWE-78",
                primary=Span(
                    file="src/app.c",
                    start_line=start,
                    start_column=1,
                    end_line=end,
                    end_column=1,
                    excerpt=excerpt,
                ),
                explanation="설명",
                remediation=Remediation(summary="고치기", detail="자세히", replacement=replacement),
                verified=True,
            )
        ],
    )
    paths.save_report(report)


def _paths_for(run_id: str):
    from agent.runs import get_run

    paths = get_run(run_id)
    assert paths is not None
    return paths


def test_a_fix_replaces_exactly_the_lines_the_finding_is_anchored_to(client: TestClient) -> None:
    run_id = _upload(client)["run_id"]
    paths = _paths_for(run_id)
    source = (paths.source / "src/app.c").read_text(encoding="utf-8")
    target = next(i for i, line in enumerate(source.splitlines(), 1) if "sprintf" in line)
    original = source.splitlines()[target - 1]

    _report_with_fix(
        paths,
        replacement='static void run(const char *u) { char c[64]; snprintf(c, sizeof(c), "wget %s", u); system(c); }',
        excerpt=original,
        start=target,
        end=target,
    )

    response = client.post(f"/agent/runs/{run_id}/apply", json={"finding_id": "f1"})
    assert response.status_code == 200, response.text

    after = (paths.source / "src/app.c").read_text(encoding="utf-8").splitlines()
    assert "snprintf" in after[target - 1]
    assert len(after) == len(source.splitlines()), "a one-line fix must not change the line count"
    # Everything around it untouched: this splices, it does not rewrite.
    assert after[: target - 1] == source.splitlines()[: target - 1]
    assert after[target:] == source.splitlines()[target:]


def test_a_fix_is_refused_when_the_file_changed_since_the_run(client: TestClient) -> None:
    """The span points at lines that were analysed. If they are not there any
    more, applying writes over code nobody looked at."""
    run_id = _upload(client)["run_id"]
    paths = _paths_for(run_id)
    _report_with_fix(paths, replacement="int safe = 1;", excerpt="something that was never there", start=3, end=3)

    response = client.post(f"/agent/runs/{run_id}/apply", json={"finding_id": "f1"})
    assert response.status_code == 409, response.text
    assert "다시 검사" in response.json()["detail"]


def test_a_finding_with_no_replacement_is_refused_rather_than_guessed_at(client: TestClient) -> None:
    """An empty `replacement` is the model saying it cannot fix this in place."""
    run_id = _upload(client)["run_id"]
    paths = _paths_for(run_id)
    _report_with_fix(paths, replacement=None, excerpt="anything", start=1, end=1)

    response = client.post(f"/agent/runs/{run_id}/apply", json={"finding_id": "f1"})
    assert response.status_code == 409
    assert "no fix" in response.json()["detail"]


def test_applying_an_unknown_finding_is_a_404(client: TestClient) -> None:
    run_id = _upload(client)["run_id"]
    _report_with_fix(_paths_for(run_id), replacement="x", excerpt="y", start=1, end=1)
    assert client.post(f"/agent/runs/{run_id}/apply", json={"finding_id": "nope"}).status_code == 404
