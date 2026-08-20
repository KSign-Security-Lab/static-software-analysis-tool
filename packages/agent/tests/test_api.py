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

from agent.config import ENV_MODEL  # noqa: E402


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """A client over the suite's throwaway database, with no model configured."""
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


def test_only_files_the_analyser_can_read_are_stored(client: TestClient) -> None:
    """The stored tree *is* the analysed tree.

    A README, a Makefile and a `package.json` produce no chunks -- there is no
    grammar for them -- so storing them cost bytes toward the upload cap and gave
    nothing back. `seen` against `kept` is how the reader still learns their
    project is four hundred files of which sixty are source.
    """
    body = _upload(client, {**SAMPLE, "README.md": "# hi\n", "Makefile": "all:\n", "package.json": "{}"})

    assert set(body["files"]) == {"src/app.c", "src/util.h"}
    assert body["intake"] == {"kept": 2, "seen": 5, "skipped": []}
    # Not reported one by one: three hundred such lines would bury the skips that
    # a reader can actually act on.
    assert client.get(f"/agent/runs/{body['run_id']}/files").json()["files"] == ["src/app.c", "src/util.h"]


def test_files_endpoint_404s_for_an_unknown_run(client: TestClient) -> None:
    assert client.get("/agent/runs/nosuchrun/files").status_code == 404


def test_file_endpoint_returns_content_and_a_monaco_language(client: TestClient) -> None:
    run_id = _upload(client)["run_id"]
    response = client.get(f"/agent/runs/{run_id}/file", params={"path": "src/app.c"})
    assert response.status_code == 200
    body = response.json()
    assert "system(c)" in body["content"]
    assert body["language"] == "c"


def test_file_endpoint_does_not_serve_a_path_out_of_the_run(client: TestClient) -> None:
    """This takes a path straight from a query string, so it is a real target.

    A 404, not a 400: there is no root to escape and nothing to resolve
    against, so a traversal is one more name the run does not have."""
    run_id = _upload(client)["run_id"]
    response = client.get(f"/agent/runs/{run_id}/file", params={"path": "../../../../etc/passwd"})
    assert response.status_code == 404


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


def test_a_run_that_dies_mid_flight_still_surfaces_on_the_stream(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Starting is asynchronous, so a *runtime* failure has nowhere else to go.

    Configuration is answered by the route now -- see the 503 below -- and an
    unreachable endpoint is not enough to fail a run either: the graph is
    deliberately resilient, so it completes having found nothing. What is left is
    a genuine crash, which is what the worker's except branch is for.
    """
    monkeypatch.setenv(ENV_MODEL, "agent")

    def explode(**_kwargs: object) -> None:
        raise RuntimeError("the checkpointer is gone")

    monkeypatch.setattr("api.agent.inspection.InspectionSession", explode)
    run_id = _upload(client)["run_id"]
    assert client.post(f"/agent/runs/{run_id}/inspect").status_code == 200

    with client.stream("GET", f"/agent/runs/{run_id}/events") as stream:
        events = _collect_events(stream, limit=6)

    assert "run_failed" in events, events
    row = client.get(f"/agent/runs/{run_id}").json()
    assert row["status"] == "failed"
    # The reason is persisted, not only streamed: the stream cannot be replayed,
    # so a tab that attached late has only the row to read.
    assert "checkpointer" in row["error"]


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


def test_diff_against_an_unknown_run_is_a_404(client: TestClient) -> None:
    run_id = _upload(client)["run_id"]
    assert client.post(f"/agent/runs/{run_id}/diff", json={"against": "nosuchrun"}).status_code == 404


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
        "/agent/runs/{run_id}/resume",
        "/agent/runs/git",
        "/agent/runs/{run_id}/patch",
        "/agent/runs/{run_id}/archive",
        "/agent/runs/{run_id}/push",
    ):
        assert route in paths, f"{route} is missing from the OpenAPI document"

    # And the editing surface is gone rather than merely unused: a route that
    # still answers is a route something will start calling again.
    for route in (
        "/agent/runs/new",
        "/agent/runs/{run_id}/apply",
        "/agent/runs/{run_id}/diff",
        "/agent/runs/{run_id}/state",
        "/agent/runs/{run_id}/checkpoints",
        "/agent/runs/{run_id}/input",
        "/agent/runs/{run_id}/spans/{span_id}/replay",
        # Both verbs went, so FastAPI never registers the path.
        "/agent/prompts/{name}",
    ):
        assert route not in paths, f"{route} should have been removed"

    # The file route survives, read-only.
    assert set(paths["/agent/runs/{run_id}/file"]) == {"get"}


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
    # The specialists hold lookups now; only the steps that read nothing new --
    # screening, narrowing, and the ruling itself -- hold none.
    assert [t["name"] for t in steps["lens:memory"]["tools"]] == [
        "find_definition",
        "find_callers",
        "find_callees",
        "graph_neighbours",
    ]
    assert not steps["triage"]["tools"] and not steps["scout"]["tools"] and not steps["verify"]["tools"]


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


def test_the_thread_is_empty_before_an_inspection(client: TestClient) -> None:
    run_id = _upload(client)["run_id"]
    assert client.get(f"/agent/runs/{run_id}/thread").json()["threads"] == []
    assert client.get("/agent/runs/deadbeef/thread").status_code == 404


def test_graph_endpoint_names_the_nodes_a_breakpoint_may_use(client: TestClient) -> None:
    """The studio offers these as checkboxes, so they have to be the real set."""
    body = client.get("/agent/graph").json()

    assert set(body["steppable"]) == {
        "plan",
        "replan",
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


def test_watching_a_run_does_not_make_it_look_started(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Opening the stream before anyone presses start must not read as in flight,
    or the run could never be started at all."""
    import api.agent.channels as routes

    monkeypatch.setenv(ENV_MODEL, "agent")
    run_id = _upload(client)["run_id"]
    # What GET /events does on connect.
    routes._channel(run_id)

    body = client.post(f"/agent/runs/{run_id}/inspect", json={}).json()
    assert body["already_running"] is False


def test_starting_a_run_keeps_an_existing_watcher_attached(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """The watcher holds the channel object, so a new worker reuses it rather
    than swapping in one nothing writes to."""
    import api.agent.channels as routes

    monkeypatch.setenv(ENV_MODEL, "agent")
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


def test_replaying_an_unknown_span_is_a_404(client: TestClient) -> None:
    run_id, _ = _recorded_llm_span(client)

    assert client.post(f"/agent/runs/{run_id}/spans/nope/replay", json={}).status_code == 404
    assert client.post("/agent/runs/deadbeef/spans/x/replay", json={}).status_code == 404


def test_a_run_is_labelled_by_its_files_not_its_id(client: TestClient) -> None:
    """A run id is random hex. What anyone recognises is the code in it."""
    run_id = _upload(client)["run_id"]

    run = next(r for r in client.get("/agent/runs").json()["runs"] if r["run_id"] == run_id)
    assert set(run["files"]) <= {"app.c", "util.h"}
    assert run["file_count"] == 2
    assert run["updated_at"] > 0


def test_runs_are_listed_most_recently_touched_first(client: TestClient) -> None:
    """Sorted by id, a list of random hex is shuffled into a meaningless order."""
    from agent.runs import get_run

    first = _upload(client)["run_id"]
    second = _upload(client)["run_id"]
    # Two uploads can land in the same tick, so the newer one is touched
    # explicitly. `write_meta` is what bumps `updated_at`.
    run = get_run(second)
    assert run is not None
    run.write_meta(touched=True)

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
    run = get_run(run_id)
    assert run is not None
    assert run.files(), "the upload should have landed as rows"

    assert client.delete(f"/agent/runs/{run_id}").json()["deleted"] == run_id
    # Gone, and gone as a unit: the row is deleted and everything hanging off
    # it cascades, which is what the directory removal used to stand for.
    assert get_run(run_id) is None
    assert run.files() == []
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


def _report_with_fixes(paths, specs: list[dict[str, Any]]) -> None:
    """A report over `src/app.c`, one finding per spec.

    Specs carry `id`, `line`, `replacement` and optionally `end`; the excerpt is
    read from the run so the anchors match unless a test means them not to.
    """
    from agent.schema import Finding, Remediation, Report, Span

    source = paths.read_file("src/app.c").splitlines()
    findings = []
    for spec in specs:
        start = spec["line"]
        end = spec.get("end", start)
        excerpt = spec.get("excerpt", "\n".join(source[start - 1 : end]))
        findings.append(
            Finding(
                id=spec["id"],
                chunk_id="c1",
                severity=spec.get("severity", "high"),
                confidence=spec.get("confidence", 0.9),
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
                remediation=Remediation(summary="고치기", detail="자세히", replacement=spec.get("replacement")),
                verified=True,
            )
        )
    paths.save_report(Report(run_id=paths.run_id, findings=findings))


def _line_of(paths, needle: str) -> int:
    source = paths.read_file("src/app.c").splitlines()
    return next(i for i, line in enumerate(source, 1) if needle in line)


def test_patch_returns_a_diff_for_the_selected_findings(client: TestClient) -> None:
    run_id = _upload(client)["run_id"]
    paths = _paths_for(run_id)
    target = _line_of(paths, "sprintf")
    _report_with_fixes(
        paths,
        [{"id": "f1", "line": target, "replacement": "static void run(const char *u) { (void)u; }"}],
    )

    response = client.post(f"/agent/runs/{run_id}/patch", json={"finding_ids": ["f1"]})
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["applied"] == ["f1"]
    assert body["skipped"] == []
    assert body["files"] == ["src/app.c"]
    assert body["patch"].startswith("--- a/src/app.c")
    assert "+static void run(const char *u) { (void)u; }" in body["patch"]


def test_patch_never_touches_the_stored_tree(client: TestClient) -> None:
    """The whole reason a patch is reproducible: the analysed tree is immutable."""
    run_id = _upload(client)["run_id"]
    paths = _paths_for(run_id)
    before = paths.read_file("src/app.c")
    _report_with_fixes(paths, [{"id": "f1", "line": _line_of(paths, "sprintf"), "replacement": "void run(void) { }"}])

    assert client.post(f"/agent/runs/{run_id}/patch", json={"finding_ids": ["f1"]}).status_code == 200
    assert paths.read_file("src/app.c") == before


def test_patch_reports_what_it_could_not_apply(client: TestClient) -> None:
    """Advice without code is a reason, not a smaller patch than expected."""
    run_id = _upload(client)["run_id"]
    paths = _paths_for(run_id)
    _report_with_fixes(
        paths,
        [
            {"id": "coded", "line": _line_of(paths, "sprintf"), "replacement": "void run(void) { }"},
            {"id": "prose", "line": _line_of(paths, "void handle"), "replacement": None},
        ],
    )

    body = client.post(f"/agent/runs/{run_id}/patch", json={"finding_ids": ["coded", "prose"]}).json()

    assert body["applied"] == ["coded"]
    assert body["skipped"] == [{"finding_id": "prose", "reason": "no_replacement", "detail": ""}]


def test_patch_of_an_unfixable_selection_is_an_empty_patch_not_an_error(client: TestClient) -> None:
    """A question about the selection, answered. Not a failed request."""
    run_id = _upload(client)["run_id"]
    paths = _paths_for(run_id)
    _report_with_fixes(paths, [{"id": "prose", "line": 1, "replacement": None}])

    response = client.post(f"/agent/runs/{run_id}/patch", json={"finding_ids": ["prose"]})
    assert response.status_code == 200
    assert response.json()["patch"] == ""
    assert response.json()["applied"] == []


def test_patch_refuses_an_unknown_finding_rather_than_patching_a_subset(client: TestClient) -> None:
    run_id = _upload(client)["run_id"]
    paths = _paths_for(run_id)
    _report_with_fixes(paths, [{"id": "f1", "line": _line_of(paths, "sprintf"), "replacement": "void run(void) { }"}])

    response = client.post(f"/agent/runs/{run_id}/patch", json={"finding_ids": ["f1", "ghost"]})
    assert response.status_code == 404
    assert "ghost" in response.json()["detail"]


def test_patch_needs_a_completed_report(client: TestClient) -> None:
    run_id = _upload(client)["run_id"]
    response = client.post(f"/agent/runs/{run_id}/patch", json={"finding_ids": ["f1"]})
    assert response.status_code == 409


def test_patch_requires_at_least_one_finding(client: TestClient) -> None:
    run_id = _upload(client)["run_id"]
    assert client.post(f"/agent/runs/{run_id}/patch", json={"finding_ids": []}).status_code == 422


def test_archive_ships_the_whole_tree_with_the_fix_in_it(client: TestClient) -> None:
    """Every file, not only the patched ones: three files out of four hundred
    is not a source tree."""
    run_id = _upload(client)["run_id"]
    paths = _paths_for(run_id)
    _report_with_fixes(
        paths,
        [
            {
                "id": "f1",
                "line": _line_of(paths, "sprintf"),
                "replacement": "static void run(const char *u) { (void)u; }",
            }
        ],
    )

    response = client.post(f"/agent/runs/{run_id}/archive", json={"finding_ids": ["f1"]})
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/zip"
    assert f"ssat-{run_id}-fixed.zip" in response.headers["content-disposition"]
    assert response.headers["x-ssat-applied"] == "1"

    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert set(archive.namelist()) == {"src/app.c", "src/util.h"}
        patched = archive.read("src/app.c").decode("utf-8")
        assert "static void run(const char *u) { (void)u; }" in patched
        assert "sprintf" not in patched
        # The file nobody fixed comes through unchanged.
        assert archive.read("src/util.h").decode("utf-8") == paths.read_file("src/util.h")


def test_archive_refuses_when_nothing_could_be_applied(client: TestClient) -> None:
    """An archive identical to the upload, named as though it were fixed, is the
    one output here that could get unpatched code shipped."""
    run_id = _upload(client)["run_id"]
    paths = _paths_for(run_id)
    _report_with_fixes(paths, [{"id": "prose", "line": 1, "replacement": None}])

    response = client.post(f"/agent/runs/{run_id}/archive", json={"finding_ids": ["prose"]})
    assert response.status_code == 409
    assert "내려받을 소스가 없습니다" in response.json()["detail"]


def test_two_fixes_in_one_file_both_reach_the_archive(client: TestClient) -> None:
    """The ordering guarantee, end to end through HTTP."""
    run_id = _upload(client)["run_id"]
    paths = _paths_for(run_id)
    upper = _line_of(paths, "sprintf")
    lower = _line_of(paths, "void handle")
    assert upper < lower
    _report_with_fixes(
        paths,
        [
            # Grows by a line, which is what would shift the one below it.
            {"id": "upper", "line": upper, "replacement": "static void run(const char *u) {\n    (void)u;\n}"},
            {"id": "lower", "line": lower, "replacement": "void handle(Request *r) { (void)r; }"},
        ],
    )

    body = client.post(f"/agent/runs/{run_id}/patch", json={"finding_ids": ["upper", "lower"]}).json()
    assert sorted(body["applied"]) == ["lower", "upper"]
    assert body["skipped"] == []

    response = client.post(f"/agent/runs/{run_id}/archive", json={"finding_ids": ["upper", "lower"]})
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        patched = archive.read("src/app.c").decode("utf-8")
    assert "(void)u;" in patched
    assert "void handle(Request *r) { (void)r; }" in patched


# -- intake from a git remote --------------------------------------------------
#
# This route makes the *server* fetch a URL somebody typed. `test_vcs.py` covers
# the validation in detail; what matters here is that a refusal is a 400 and not
# a half-created run, and that the commit is recorded so a push can be honest.


@pytest.fixture
def git_remote(tmp_path: Path) -> Path:
    import subprocess

    work = tmp_path / "work"
    work.mkdir()
    (work / "app.c").write_text("void run(char *u) {\n    system(u);\n}\n", encoding="utf-8")
    for args in (
        ["git", "init", "-q", "-b", "main", "."],
        ["git", "config", "user.email", "t@t"],
        ["git", "config", "user.name", "t"],
        ["git", "add", "-A"],
        ["git", "commit", "-q", "-m", "first"],
    ):
        subprocess.run(args, cwd=work, check=True, capture_output=True)  # noqa: S603 - fixed argv, no shell

    bare = tmp_path / "remote.git"
    subprocess.run(  # noqa: S603, S607 - fixed argv, no shell
        ["git", "clone", "-q", "--bare", str(work), str(bare)], cwd=tmp_path, check=True, capture_output=True
    )
    return bare


def test_cloning_a_repository_indexes_it_and_records_the_commit(
    client: TestClient, git_remote: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import shutil

    if shutil.which("git") is None:
        pytest.skip("git is not installed")
    # A filesystem path cannot pass the real check; it is tested on its own.
    monkeypatch.setattr("agent.vcs.check_url", lambda url: url)

    response = client.post("/agent/runs/git", json={"url": str(git_remote), "ref": "main"})
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["files"] == ["app.c"]
    assert body["index"]["files_indexed"] == 1
    origin = body["origin"]
    assert origin["kind"] == "git"
    assert origin["ref"] == "main"
    assert len(origin["commit"]) == 40
    assert origin["label"].endswith("@main")

    # And it survives on the run, which is what a later push reads.
    listed = client.get(f"/agent/runs/{body['run_id']}").json()
    assert listed["origin"]["commit"] == origin["commit"]


def test_a_url_the_server_may_not_fetch_is_a_400(client: TestClient) -> None:
    response = client.post("/agent/runs/git", json={"url": "file:///etc/passwd"})
    assert response.status_code == 400
    assert "지원하지 않습니다" in response.json()["detail"]


def test_an_unreachable_remote_is_a_502_not_a_500(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """We reached out and something upstream said no. That is not our error."""
    import shutil

    if shutil.which("git") is None:
        pytest.skip("git is not installed")
    monkeypatch.setattr("agent.vcs.check_url", lambda url: url)

    response = client.post("/agent/runs/git", json={"url": "/nonexistent/repo.git"})
    assert response.status_code == 502


def test_an_upload_records_what_kind_of_intake_it_was(client: TestClient) -> None:
    """The patch surface reads this to decide whether pushing is even possible."""
    body = _upload(client)
    assert body["origin"] == {"kind": "zip", "label": "upload.zip", "url": None, "ref": None, "commit": None}


def test_pushing_a_run_that_was_uploaded_is_a_400(client: TestClient) -> None:
    """No remote, so no button. The API says so rather than trying."""
    run_id = _upload(client)["run_id"]
    paths = _paths_for(run_id)
    _report_with_fixes(paths, [{"id": "f1", "line": _line_of(paths, "sprintf"), "replacement": "void run(void) { }"}])

    response = client.post(
        f"/agent/runs/{run_id}/push",
        json={"finding_ids": ["f1"], "branch": "ssat/fix", "token": "t"},
    )
    assert response.status_code == 400
    assert "올릴 원격이 없습니다" in response.json()["detail"]


def test_pushing_with_nothing_applicable_is_refused_before_any_network(client: TestClient) -> None:
    run_id = _upload(client)["run_id"]
    _report_with_fixes(_paths_for(run_id), [{"id": "prose", "line": 1, "replacement": None}])

    response = client.post(
        f"/agent/runs/{run_id}/push",
        json={"finding_ids": ["prose"], "branch": "ssat/fix", "token": "t"},
    )
    # The origin check comes first, and this run has no git origin either.
    assert response.status_code in {400, 409}


def test_a_push_needs_a_token(client: TestClient) -> None:
    run_id = _upload(client)["run_id"]
    response = client.post(
        f"/agent/runs/{run_id}/push",
        json={"finding_ids": ["f1"], "branch": "ssat/fix", "token": ""},
    )
    assert response.status_code == 422


def test_a_cloned_run_can_have_its_fix_pushed_back(
    client: TestClient, git_remote: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The whole path, end to end: clone, report, select, push.

    Against a bare repository on disk rather than a network host. The URL check
    and the credential rewrite are stubbed -- both are tested on their own in
    `test_vcs.py` -- so what this exercises is the route: origin lookup, patch
    built server-side from ids, apply on a fresh clone, branch created.
    """
    import shutil
    import subprocess

    if shutil.which("git") is None:
        pytest.skip("git is not installed")
    monkeypatch.setattr("agent.vcs.check_url", lambda url: url)
    monkeypatch.setattr("agent.vcs._authenticated", lambda url, token: url)

    created = client.post("/agent/runs/git", json={"url": str(git_remote), "ref": "main"}).json()
    run_id = created["run_id"]
    paths = _paths_for(run_id)

    from agent.schema import Finding, Remediation, Report, Span

    paths.save_report(
        Report(
            run_id=run_id,
            findings=[
                Finding(
                    id="f1",
                    chunk_id="c1",
                    severity="critical",
                    confidence=0.95,
                    title="셸로 넘어가는 입력",
                    cwe="CWE-78",
                    primary=Span(
                        file="app.c",
                        start_line=2,
                        start_column=1,
                        end_line=2,
                        end_column=1,
                        excerpt="    system(u);",
                    ),
                    explanation="입력이 그대로 셸로 갑니다.",
                    remediation=Remediation(summary="쓰지 않습니다", detail="제거", replacement="    (void)u;"),
                    verified=True,
                )
            ],
        )
    )

    response = client.post(
        f"/agent/runs/{run_id}/push",
        json={"finding_ids": ["f1"], "branch": "ssat/fix-1", "token": "secret-token"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["branch"] == "ssat/fix-1"
    assert body["applied"] == ["f1"]

    shown = subprocess.run(  # noqa: S603, S607 - fixed argv, no shell
        ["git", "show", "ssat/fix-1:app.c"], cwd=git_remote, capture_output=True, text=True, check=True
    )
    assert "(void)u;" in shown.stdout
    assert "system(u);" not in shown.stdout

    # The token was a request argument and nothing more.
    assert "secret-token" not in json.dumps(paths.read_meta())


# -- what an upload may contain ------------------------------------------------
#
# Two caps defending two different things, and the difference is the point. The
# totals are a resource-exhaustion defence and stay refusals. The per-file cap is
# a judgement about what is worth keeping, so it skips -- because a real project
# carries generated artifacts and refusing the whole upload over one of them cost
# the reader every other file for nothing.


def test_an_oversized_file_is_skipped_and_the_rest_is_indexed(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The case this exists for: a 260 MB `pkix1.json` beside the C it came from.

    The indexer skips anything over 1.5 MB anyway, so such a file was never going
    to be inspected -- and the upload refusing outright meant the project could
    not be scanned at all.
    """
    # Comfortably above both SAMPLE files and far below the artifact.
    monkeypatch.setattr("agent.files.MAX_SINGLE_FILE_BYTES", 1024)

    # A *source* file this time: a generated `.json` no longer reaches the size
    # check at all, because it is not something the analyser reads.
    body = _upload(client, {**SAMPLE, "src/generated.c": "x" * 4096})

    assert set(body["files"]) == {"src/app.c", "src/util.h"}
    assert body["uploaded"] == 2
    assert body["index"]["files_indexed"] == 2
    assert body["intake"]["kept"] == 2
    assert body["intake"]["skipped"] == [{"path": "src/generated.c", "size": 4096, "reason": "too_large"}]


def test_what_was_skipped_survives_the_request_that_decided_it(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A patch archive a week later is missing that file. The run has to say why."""
    monkeypatch.setattr("agent.files.MAX_SINGLE_FILE_BYTES", 1024)
    run_id = _upload(client, {**SAMPLE, "big.c": "x" * 4096})["run_id"]

    listed = client.get(f"/agent/runs/{run_id}").json()
    assert listed["intake"]["skipped"][0]["path"] == "big.c"


def test_an_upload_of_nothing_but_oversized_files_says_so(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Different from an empty upload: this is a tree with no source in it."""
    monkeypatch.setattr("agent.files.MAX_SINGLE_FILE_BYTES", 64)

    payload = _zip({"big.c": "x" * 4096})
    response = client.post("/agent/runs", files={"files": ("upload.zip", payload, "application/zip")})

    assert response.status_code == 400
    assert "너무 크거나 텍스트가 아니었습니다" in response.json()["detail"]


def test_the_total_size_cap_is_still_a_refusal(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """A thousand merely-large files each pass the per-file cap and still add up,
    so skipping cannot be the answer here the way it is for one absurd file."""
    monkeypatch.setattr("agent.files.MAX_UPLOAD_BYTES", 128)

    payload = _zip({f"f{i}.c": "x" * 64 for i in range(8)})
    response = client.post("/agent/runs", files={"files": ("upload.zip", payload, "application/zip")})

    assert response.status_code == 400
    detail = response.json()["detail"]
    # Actionable, not just accurate: `expands past 524288000 bytes` said what
    # happened and nothing about what to do next.
    assert "MB를 넘습니다" in detail
    assert "하위 폴더만 골라" in detail


def test_the_file_count_cap_is_still_a_refusal(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("agent.files.MAX_UPLOAD_FILES", 3)

    payload = _zip({f"f{i}.c": "int x;" for i in range(8)})
    response = client.post("/agent/runs", files={"files": ("upload.zip", payload, "application/zip")})

    assert response.status_code == 400
    assert "3개를 넘습니다" in response.json()["detail"]


def test_loose_files_are_capped_the_same_way_an_archive_is(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """The folder picker had no caps at all -- only `read_zip` counted anything.

    So the same tree was refused as a zip and accepted as a folder, which is the
    wrong way round: the folder picker is the path most people use.
    """
    monkeypatch.setattr("agent.files.MAX_SINGLE_FILE_BYTES", 64)

    response = client.post(
        "/agent/runs",
        files=[
            ("files", ("small.c", b"int x;", "text/plain")),
            ("files", ("generated.c", b"x" * 4096, "text/plain")),
        ],
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["files"] == ["small.c"]
    assert body["intake"]["skipped"] == [{"path": "generated.c", "size": 4096, "reason": "too_large"}]


def test_the_dead_weight_of_a_real_project_is_not_stored(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """`.git`, `node_modules` and build output are excluded at intake.

    Only the git path did this, so a project *zipped up* stored its whole history
    as rows and the indexer then skipped every one of them -- which is how an
    upload could exceed the total cap on bytes nobody was ever going to read.

    Not reported as skips: unlike an oversized source file, nobody is surprised
    that `.git` was left out, and ten thousand of them would bury the ones that
    matter.
    """
    body = _upload(
        client,
        {
            **SAMPLE,
            ".git/objects/ab/cdef": "x" * 2048,
            "node_modules/dep/index.js": "module.exports = 1",
            "build/out.o": "x" * 2048,
            "vendor/lib/thing.c": "int vendored;",
        },
    )

    assert set(body["files"]) == {"src/app.c", "src/util.h"}
    assert body["intake"]["skipped"] == []


def test_the_total_cap_counts_only_what_is_kept(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """A project whose bulk is `.git` must not be refused for its bulk.

    The whole point of filtering at intake: 40 MB of history against a 128-byte
    budget is fine, because none of it is stored.
    """
    monkeypatch.setattr("agent.files.MAX_UPLOAD_BYTES", 128)

    body = _upload(client, {"src/app.c": "int x;", ".git/pack/big": "x" * 40_000})

    assert body["files"] == ["src/app.c"]


def test_a_mac_made_zip_does_not_take_the_upload_down(client: TestClient) -> None:
    """The crash this exists for: `psycopg.DataError` from inside the ORM flush.

    A Mac writes an AppleDouble fork beside every file it archives, and its header
    is literally `\\x00\\x05\\x16\\x07`. `files.content` is a Postgres text column,
    Postgres rejects NUL outright, and `errors="replace"` does not help because
    NUL is perfectly valid UTF-8 -- so one such entry failed the whole upload with
    a 500 and left the run empty.
    """
    body = _upload(
        client,
        {
            **SAMPLE,
            "__MACOSX/src/._app.c": b"\x00\x05\x16\x07\x00\x02\x00\x00Mac OS X\x00\x02\x00\x00\x00\t",
            "src/._app.c": b"\x00\x05\x16\x07\x00\x02\x00\x00Mac OS X",
            "src/.DS_Store": b"\x00\x00\x00\x01Bud1",
        },
    )

    assert set(body["files"]) == {"src/app.c", "src/util.h"}
    # Mac litter is noise, not a skip worth reporting: one entry per real file
    # would bury the skips that matter.
    assert body["intake"]["skipped"] == []


def test_a_binary_file_is_skipped_and_named(client: TestClient) -> None:
    """Not a size judgement. It cannot be stored, and storing it mangled was worse
    than useless: the archive route writes rows back out as text, so a PNG went in
    and came out corrupted."""
    # Named `.c`, so it passes the source filter and the bytes are what refuse it --
    # a corrupt file wearing a source extension is the only way a binary now
    # reaches this check at all.
    body = _upload(client, {**SAMPLE, "src/blob.c": b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"})

    assert set(body["files"]) == {"src/app.c", "src/util.h"}
    assert body["intake"]["skipped"] == [{"path": "src/blob.c", "size": 16, "reason": "binary"}]


def test_text_that_merely_looks_odd_is_still_stored(client: TestClient) -> None:
    """The heuristic is a NUL in the first block, not "is not ASCII".

    Korean comments, a UTF-8 BOM and invalid byte sequences all have to survive --
    `errors="replace"` is what they are for, and refusing them would refuse most
    of this repository's own corpus.
    """
    body = _upload(
        client,
        {
            "src/korean.c": "/* 셸로 넘어가는 입력 */\nint main(void) { return 0; }\n",
            "src/bom.c": b"\xef\xbb\xbfint x;\n",
            "src/latin1.c": b"/* caf\xe9 */\nint y;\n",
        },
    )

    assert set(body["files"]) == {"src/korean.c", "src/bom.c", "src/latin1.c"}
    assert body["intake"]["skipped"] == []


def test_a_stray_nul_deep_in_a_text_file_does_not_fail_the_upload(client: TestClient) -> None:
    """Past the sniff window, so `is_binary` misses it and the decode has to catch
    it. Defence in depth: one odd byte is not worth refusing an upload over."""
    padded = ("int x;\n" * 2000).encode() + b"\x00tail\n"
    body = _upload(client, {"src/odd.c": padded})

    assert body["files"] == ["src/odd.c"]
    stored = client.get(f"/agent/runs/{body['run_id']}/file", params={"path": "src/odd.c"}).json()
    assert "\x00" not in stored["content"]
    assert "�" in stored["content"]


def test_starting_without_a_model_is_refused_rather_than_started(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A 503 from the button, not a run that dies.

    `require_model` was checked inside the worker thread, so a deployment with no
    `AGENT_MODEL` accepted the request with a 200, marked the run `inspecting`,
    and then failed -- which reaches the reader as 실행 실패 on a scan they thought
    had started, rather than as a button telling them what to configure.
    """
    monkeypatch.delenv(ENV_MODEL, raising=False)
    run_id = _upload(client)["run_id"]

    response = client.post(f"/agent/runs/{run_id}/inspect", json={})

    assert response.status_code == 503
    detail = response.json()["detail"]
    assert "AGENT_MODEL" in detail
    # And the run is untouched: nothing was spawned, so it is still indexed.
    assert client.get(f"/agent/runs/{run_id}").json()["status"] != "inspecting"


def test_health_names_what_the_endpoint_actually_serves(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """The one fact that turns this dead end into a one-line fix.

    Knowing `AGENT_MODEL` is unset does not say what to set it *to*, and the
    endpoint already knows.
    """
    monkeypatch.delenv(ENV_MODEL, raising=False)
    monkeypatch.setattr("api.agent.meta.list_models", lambda _base: ["agent", "other"])

    body = client.get("/agent/health", params={"probe": "true"}).json()

    assert body["configured"] is False
    assert body["served_models"] == ["agent", "other"]
    assert body["model_is_served"] is False
