from __future__ import annotations

import io
import json
import queue
import threading
import time
import zipfile
from pathlib import Path
from typing import Any, Iterator

import pytest


pytest.importorskip("fastapi", reason="the API extras are not installed")
pytest.importorskip("httpx", reason="fastapi.testclient needs httpx")

from fastapi.testclient import TestClient  # noqa: E402

from agent.config import ENV_BASE_URL, ENV_ENV_FILE, ENV_MODEL  # noqa: E402


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.delenv(ENV_MODEL, raising=False)
    monkeypatch.setenv(ENV_ENV_FILE, str(tmp_path / "absent.env"))
    # Port 9 is discard, so nothing here can reach a model server that happens
    # to be running on this machine. Tests that want one patch `list_models`.
    monkeypatch.setenv(ENV_BASE_URL, "http://127.0.0.1:9/v1")

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


def test_files_endpoint_lists_the_whole_tree(client: TestClient) -> None:
    run_id = _upload(client)["run_id"]
    response = client.get(f"/agent/runs/{run_id}/files")
    assert response.status_code == 200
    body = response.json()
    assert body["run_id"] == run_id
    assert "src/app.c" in body["files"]
    assert body["files"] == sorted(body["files"])


def test_only_files_the_analyser_can_read_are_stored(client: TestClient) -> None:
    body = _upload(client, {**SAMPLE, "README.md": "# hi\n", "Makefile": "all:\n", "package.json": "{}"})

    assert set(body["files"]) == {"src/app.c", "src/util.h"}
    assert body["intake"] == {"kept": 2, "seen": 5, "skipped": []}
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


def test_health_reports_unconfigured_when_no_model_is_set(client: TestClient) -> None:
    body = client.get("/agent/health").json()
    assert body["configured"] is False
    assert body["model"] is None


def test_health_does_not_touch_the_network_unless_asked(client: TestClient) -> None:
    body = client.get("/agent/health").json()
    assert "served_models" not in body
    assert "reachable" not in body


def test_health_probe_reports_what_the_endpoint_serves(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
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
    import api.agent.meta as routes

    monkeypatch.setattr(routes, "list_models", lambda _url: ["agent"])
    monkeypatch.setenv(ENV_MODEL, "Qwen/Qwen2.5-Coder-32B-Instruct")

    body = client.get("/agent/health", params={"probe": "true"}).json()
    assert body["reachable"] is True
    assert body["model_is_served"] is False


def test_health_probe_counts_a_single_served_model_as_configured(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """What a run would do, so the UI does not refuse a setup that works.

    `require_model` takes the only model an endpoint serves when AGENT_MODEL is
    unset. Health used to read the variable directly and call that unconfigured.
    """
    import api.agent.meta as routes

    monkeypatch.setattr(routes, "list_models", lambda _url: ["agent"])

    body = client.get("/agent/health", params={"probe": "true"}).json()
    assert body["configured"] is True
    assert body["model"] == "agent"
    assert body["model_is_served"] is True


def test_health_probe_still_needs_a_choice_between_several_models(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import api.agent.meta as routes

    monkeypatch.setattr(routes, "list_models", lambda _url: ["agent", "other"])

    body = client.get("/agent/health", params={"probe": "true"}).json()
    assert body["configured"] is False
    assert body["model"] is None


def test_the_api_reads_the_model_from_an_env_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("AGENT_MODEL=from-the-file\n", encoding="utf-8")
    monkeypatch.delenv(ENV_MODEL, raising=False)
    monkeypatch.setenv(ENV_ENV_FILE, str(env_file))

    from api.main import app

    with TestClient(app) as reader:
        assert reader.get("/agent/health").json()["model"] == "from-the-file"


def test_an_exported_model_beats_the_env_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("AGENT_MODEL=from-the-file\n", encoding="utf-8")
    monkeypatch.setenv(ENV_MODEL, "exported")
    monkeypatch.setenv(ENV_ENV_FILE, str(env_file))

    from api.main import app

    with TestClient(app) as reader:
        assert reader.get("/agent/health").json()["model"] == "exported"


def test_health_probe_survives_a_dead_endpoint(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    import api.agent.meta as routes

    monkeypatch.setattr(routes, "list_models", lambda _url: [])
    body = client.get("/agent/health", params={"probe": "true"}).json()
    assert body["reachable"] is False
    assert body["model_is_served"] is False


def test_a_run_that_dies_mid_flight_still_surfaces_on_the_stream(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
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
    body = client.get("/health").json()
    assert "backends" in body or "status" in body, body


def test_generated_ts_schema_is_shipped_to_the_web_app() -> None:
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

    for route in (
        "/agent/runs/new",
        "/agent/runs/{run_id}/apply",
        "/agent/runs/{run_id}/diff",
        "/agent/runs/{run_id}/state",
        "/agent/runs/{run_id}/checkpoints",
        "/agent/runs/{run_id}/input",
        "/agent/runs/{run_id}/spans/{span_id}/replay",
        "/agent/prompts/{name}",
    ):
        assert route not in paths, f"{route} should have been removed"

    assert set(paths["/agent/runs/{run_id}/file"]) == {"get"}


def test_spans_are_empty_before_an_inspection(client: TestClient) -> None:
    run_id = _upload(client)["run_id"]
    body = client.get(f"/agent/runs/{run_id}/spans").json()

    assert body["spans"] == []
    assert body["summary"]["spans"] == 0


def test_spans_endpoint_serves_the_recorded_tree(client: TestClient) -> None:
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
    steps = {entry["step"]: entry for entry in client.get("/agent/graph").json()["steps"]}

    assert steps["triage"]["schema"] == "Triage"
    assert steps["lens:memory"]["prompt"] == "lens:memory"
    assert steps["gather"]["node"] == "gather", "retrieval is a node, not a half of one"
    assert [tool["name"] for tool in steps["gather"]["tools"]][:1] == ["read_source"]
    assert [t["name"] for t in steps["lens:memory"]["tools"]] == [
        "find_definition",
        "find_callers",
        "find_callees",
        "graph_neighbours",
    ]
    assert not steps["triage"]["tools"] and not steps["scout"]["tools"] and not steps["verify"]["tools"]


def test_thread_groups_model_calls_into_one_conversation_per_chunk(client: TestClient) -> None:
    from agent.runs import get_run

    run_id = _upload(client)["run_id"]
    paths = get_run(run_id)
    assert paths is not None

    spans = paths.spans()
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
    assert turn["tool_calls"][0]["name"] == "read_source"
    assert turn["tools"][0]["outputs"] == "int main(void)"
    assert turn["tools"][0]["latency_ms"] == 400


def test_the_thread_is_empty_before_an_inspection(client: TestClient) -> None:
    run_id = _upload(client)["run_id"]
    assert client.get(f"/agent/runs/{run_id}/thread").json()["threads"] == []
    assert client.get("/agent/runs/deadbeef/thread").status_code == 404


def test_graph_endpoint_names_the_nodes_a_breakpoint_may_use(client: TestClient) -> None:
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
    assert "__start__" not in body["steppable"]


def test_a_misspelled_breakpoint_is_refused_before_the_run_starts(client: TestClient) -> None:
    run_id = _upload(client)["run_id"]
    response = client.post(f"/agent/runs/{run_id}/inspect", json={"breakpoints": ["analyze"]})

    assert response.status_code == 400
    assert "analyze" in response.json()["detail"]


def test_state_before_any_run_is_a_404_not_an_empty_state(client: TestClient) -> None:
    run_id = _upload(client)["run_id"]
    assert client.get(f"/agent/runs/{run_id}/state").status_code == 404
    assert client.get("/agent/runs/deadbeef/state").status_code == 404


def test_resuming_a_run_that_is_not_stopped_is_refused(client: TestClient) -> None:
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
    import api.agent.channels as routes

    monkeypatch.setenv(ENV_MODEL, "agent")
    run_id = _upload(client)["run_id"]
    routes._channel(run_id)

    body = client.post(f"/agent/runs/{run_id}/inspect", json={}).json()
    assert body["already_running"] is False


def test_starting_a_run_keeps_an_existing_watcher_attached(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    import api.agent.channels as routes

    monkeypatch.setenv(ENV_MODEL, "agent")
    run_id = _upload(client)["run_id"]
    watched = routes._channel(run_id)

    client.post(f"/agent/runs/{run_id}/inspect", json={})

    assert routes._channel(run_id) is watched
    assert watched.claimed is True


def test_the_last_frame_of_the_previous_run_survives_a_restart(client: TestClient) -> None:
    from api.agent.channels import RunChannel

    channel = RunChannel()
    with channel.listen() as events:
        channel.publish({"event": "run_finished", "data": {}})
        channel.commands.put({"action": "resume"})
        channel.finished.set()
        channel.waiting.set()
        channel.error = "the last one blew up"

        channel.reclaim()

        assert events.get_nowait()["event"] == "run_finished"
        assert events.empty() and channel.commands.empty()
    assert not channel.finished.is_set() and not channel.waiting.is_set()
    assert channel.error is None and channel.claimed is True


def test_two_starts_landing_together_put_one_worker_on_the_run(client: TestClient) -> None:
    import threading

    from api.agent.channels import RunChannel

    channel = RunChannel()
    taken: list[bool] = []
    ready = threading.Barrier(8)

    def race() -> None:
        ready.wait()
        taken.append(channel.claim())

    threads = [threading.Thread(target=race) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert taken.count(True) == 1, "more than one worker claimed the run"
    assert channel.live is True


def test_a_start_on_a_run_already_in_flight_says_so(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    import api.agent.channels as channels

    monkeypatch.setenv(ENV_MODEL, "agent")
    run_id = _upload(client)["run_id"]
    channels._channel(run_id).claimed = True

    body = client.post(f"/agent/runs/{run_id}/inspect", json={"force": True}).json()
    assert body["already_running"] is True


class _Ordinary:
    stopped = False
    interrupted = False

    def __init__(self, **_kwargs: object) -> None:
        return None

    def start(self, **_kwargs: object) -> None:
        return None

    def resume(self, **_kwargs: object) -> None:
        return None

    def report(self):  # noqa: ANN202 - a stand-in for the real session
        from agent.schema import Report

        return Report(run_id="r")

    def close(self) -> None:
        return None


def test_a_stream_opened_before_the_start_survives_the_last_runs_finish(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import threading

    import api.agent.channels as channels

    monkeypatch.setenv(ENV_MODEL, "agent")
    monkeypatch.setattr("api.agent.inspection.STREAM_START_GRACE_SECONDS", 10.0)
    monkeypatch.setattr("api.agent.inspection.InspectionSession", _Ordinary)
    run_id = _upload(client)["run_id"]
    channel = channels._channel(run_id)
    channel.claimed = True
    channel.finished.set()

    def start_late() -> None:
        client.post(f"/agent/runs/{run_id}/inspect", json={"force": True})

    timer = threading.Timer(1.5, start_late)
    timer.start()
    try:
        with client.stream("GET", f"/agent/runs/{run_id}/events") as stream:
            events = _collect_events(stream, limit=8)
    finally:
        timer.cancel()

    assert events[0] != "stream_closed", "the stream closed on the last run's flag"
    assert "run_started" in events, events


def test_a_stream_on_a_run_nobody_starts_does_not_hang_for_ever(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("api.agent.inspection.STREAM_START_GRACE_SECONDS", 1.0)
    run_id = _upload(client)["run_id"]

    with client.stream("GET", f"/agent/runs/{run_id}/events") as stream:
        events = _collect_events(stream, limit=4)

    assert events == ["stream_closed"], events


def test_a_worker_that_dies_before_it_starts_still_ends_the_run(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import api.agent.channels as channels

    monkeypatch.setenv(ENV_MODEL, "agent")

    run_id = _upload(client)["run_id"]
    channel = channels._channel(run_id)

    def boom(self: object) -> None:
        raise RuntimeError("the database went away")

    monkeypatch.setattr("agent.runs.Run.store", boom)

    assert client.post(f"/agent/runs/{run_id}/inspect", json={"force": True}).status_code == 200
    assert channel.finished.wait(2.0), "a worker that died left the run claimed"
    assert client.get(f"/agent/runs/{run_id}").json()["status"] == "failed"
    assert channel.live is False


def test_a_store_that_fails_to_close_still_ends_the_run(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    import api.agent.channels as channels

    monkeypatch.setenv(ENV_MODEL, "agent")
    closed: list[str] = []

    class BadStore:
        def clear_results(self) -> None:
            return None

        def close(self) -> None:
            closed.append("store")
            raise RuntimeError("the connection is gone")

    class Spans:
        def clear(self) -> None:
            return None

        def close(self) -> None:
            closed.append("spans")

    run_id = _upload(client)["run_id"]
    channel = channels._channel(run_id)

    monkeypatch.setattr("agent.runs.Run.store", lambda self: BadStore())
    monkeypatch.setattr("agent.runs.Run.spans", lambda self: Spans())
    monkeypatch.setattr("api.agent.inspection.InspectionSession", _Ordinary)

    assert client.post(f"/agent/runs/{run_id}/inspect", json={"force": True}).status_code == 200
    assert channel.finished.wait(2.0), "a failing close stranded the run"
    assert closed[-2:] == ["store", "spans"], closed


def test_an_ordinary_stop_is_reported_as_aborted(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    import api.agent.channels as channels

    monkeypatch.setenv(ENV_MODEL, "agent")

    class CancelledMidRun(_Ordinary):
        stopped = True

        def __init__(self, **kwargs: object) -> None:
            self._run_id = str(kwargs.get("run_id"))

        def start(self, **_kwargs: object) -> None:
            channels._channel(self._run_id).cancelled.set()

    monkeypatch.setattr("api.agent.inspection.InspectionSession", CancelledMidRun)
    run_id = _upload(client)["run_id"]
    channel = channels._channel(run_id)

    with channel.listen() as events:
        assert client.post(f"/agent/runs/{run_id}/inspect", json={"force": True}).status_code == 200
        assert channel.finished.wait(2.0)
        frames = []
        while True:
            try:
                frames.append(events.get_nowait())
            except queue.Empty:
                break

    finished = [frame for frame in frames if frame["event"] == "run_finished"]
    assert finished and finished[0]["data"]["aborted"] is True, frames


def test_shutdown_stops_workers_rather_than_orphaning_them(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import api.agent.channels as channels
    from api.main import app

    monkeypatch.setenv(ENV_MODEL, "agent")
    closed: list[str] = []
    running = threading.Event()

    class Blocking(_Ordinary):
        def __init__(self, **kwargs: object) -> None:
            self._cancelled = kwargs.get("cancelled")

        def start(self, **_kwargs: object) -> None:
            running.set()
            while not self._cancelled():  # type: ignore[operator]
                time.sleep(0.01)

        def close(self) -> None:
            closed.append("session")

    monkeypatch.setattr("api.agent.inspection.InspectionSession", Blocking)

    with TestClient(app) as client:
        run_id = _upload(client)["run_id"]
        assert client.post(f"/agent/runs/{run_id}/inspect", json={"force": True}).status_code == 200
        assert running.wait(2.0), "the worker never started"
        channel = channels._channel(run_id)
        assert channel.live is True

    assert channel.cancelled.is_set(), "shutdown killed the worker instead of stopping it"
    assert channel.finished.wait(2.0)
    assert closed == ["session"], "the session was never closed, so its subprocess is orphaned"


def test_a_channel_nobody_is_on_is_forgotten(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    import api.agent.channels as channels

    monkeypatch.setattr(channels, "CHANNEL_IDLE_SECONDS", -1.0)
    channels._channel("watched-and-left")
    working = channels._channel("still-working")
    working.claimed = True

    channels._channel("someone-else")

    assert "watched-and-left" not in channels._channels
    assert "still-working" in channels._channels


def test_every_listener_gets_every_event(client: TestClient) -> None:
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
    from api.agent.channels import RunChannel

    channel = RunChannel()
    channel.publish({"event": "node_started", "data": {}})

    with channel.listen() as events:
        assert events.empty()


def _recorded_llm_span(client: TestClient, step: str = "lens:memory") -> tuple[str, str]:
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
    run_id = _upload(client)["run_id"]
    run = next(r for r in client.get("/agent/runs").json()["runs"] if r["run_id"] == run_id)
    assert set(run["files"]) <= {"app.c", "util.h"}
    assert run["file_count"] == 2
    assert run["updated_at"] > 0


def test_runs_are_listed_most_recently_touched_first(client: TestClient) -> None:
    from agent.runs import get_run

    first = _upload(client)["run_id"]
    second = _upload(client)["run_id"]
    run = get_run(second)
    assert run is not None
    run.write_meta(touched=True)

    listed = [r["run_id"] for r in client.get("/agent/runs").json()["runs"]]
    assert listed.index(second) < listed.index(first)


def test_a_run_that_never_ran_is_marked_as_such(client: TestClient) -> None:
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
    from agent.runs import new_run

    paths = new_run()
    paths.write_meta(status=status, index={}, uploaded=0)
    return paths.run_id


def test_startup_fails_the_runs_no_process_is_left_to_finish(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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
    assert statuses[finished] == "done"

    paths = get_run(interrupted)
    assert paths is not None
    meta = paths.read_meta()
    assert "다시 시작" in meta["error"]
    assert meta["parked"] is None


def test_a_second_inspection_of_unchanged_code_is_declined(client: TestClient) -> None:
    from agent.runs import get_run

    run_id = _upload(client)["run_id"]
    paths = get_run(run_id)
    assert paths is not None

    store = paths.store()
    chunk_ids = store.order()
    assert chunk_ids, "the fixture upload should index at least one chunk"
    for chunk_id in chunk_ids:
        store.mark_inspected(chunk_id)
    assert store.uninspected() == []
    store.close()
    paths.spans().close()

    declined = client.post(f"/agent/runs/{run_id}/inspect").json()
    assert declined["nothing_to_do"] is True
    assert declined["already_running"] is False

    forced = client.post(f"/agent/runs/{run_id}/inspect", json={"force": True}).json()
    assert "nothing_to_do" not in forced


def test_an_uninspected_chunk_still_starts_a_run(client: TestClient) -> None:
    run_id = _upload(client)["run_id"]
    accepted = client.post(f"/agent/runs/{run_id}/inspect").json()
    assert "nothing_to_do" not in accepted


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
    run_id = _upload(client)["run_id"]
    paths = _paths_for(run_id)
    before = paths.read_file("src/app.c")
    _report_with_fixes(paths, [{"id": "f1", "line": _line_of(paths, "sprintf"), "replacement": "void run(void) { }"}])

    assert client.post(f"/agent/runs/{run_id}/patch", json={"finding_ids": ["f1"]}).status_code == 200
    assert paths.read_file("src/app.c") == before


def test_patch_reports_what_it_could_not_apply(client: TestClient) -> None:
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
        assert archive.read("src/util.h").decode("utf-8") == paths.read_file("src/util.h")


def test_archive_refuses_when_nothing_could_be_applied(client: TestClient) -> None:
    run_id = _upload(client)["run_id"]
    paths = _paths_for(run_id)
    _report_with_fixes(paths, [{"id": "prose", "line": 1, "replacement": None}])

    response = client.post(f"/agent/runs/{run_id}/archive", json={"finding_ids": ["prose"]})
    assert response.status_code == 409
    assert "내려받을 소스가 없습니다" in response.json()["detail"]


def test_two_fixes_in_one_file_both_reach_the_archive(client: TestClient) -> None:
    run_id = _upload(client)["run_id"]
    paths = _paths_for(run_id)
    upper = _line_of(paths, "sprintf")
    lower = _line_of(paths, "void handle")
    assert upper < lower
    _report_with_fixes(
        paths,
        [
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

    listed = client.get(f"/agent/runs/{body['run_id']}").json()
    assert listed["origin"]["commit"] == origin["commit"]


def test_a_url_the_server_may_not_fetch_is_a_400(client: TestClient) -> None:
    response = client.post("/agent/runs/git", json={"url": "file:///etc/passwd"})
    assert response.status_code == 400
    assert "지원하지 않습니다" in response.json()["detail"]


def test_an_unreachable_remote_is_a_502_not_a_500(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    import shutil

    if shutil.which("git") is None:
        pytest.skip("git is not installed")
    monkeypatch.setattr("agent.vcs.check_url", lambda url: url)

    response = client.post("/agent/runs/git", json={"url": "/nonexistent/repo.git"})
    assert response.status_code == 502


def test_an_upload_records_what_kind_of_intake_it_was(client: TestClient) -> None:
    body = _upload(client)
    assert body["origin"] == {"kind": "zip", "label": "upload.zip", "url": None, "ref": None, "commit": None}


def test_pushing_a_run_that_was_uploaded_is_a_400(client: TestClient) -> None:
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

    assert "secret-token" not in json.dumps(paths.read_meta())


def test_an_oversized_file_is_skipped_and_the_rest_is_indexed(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("agent.files.MAX_SINGLE_FILE_BYTES", 1024)

    body = _upload(client, {**SAMPLE, "src/generated.c": "x" * 4096})

    assert set(body["files"]) == {"src/app.c", "src/util.h"}
    assert body["uploaded"] == 2
    assert body["index"]["files_indexed"] == 2
    assert body["intake"]["kept"] == 2
    assert body["intake"]["skipped"] == [{"path": "src/generated.c", "size": 4096, "reason": "too_large"}]


def test_what_was_skipped_survives_the_request_that_decided_it(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("agent.files.MAX_SINGLE_FILE_BYTES", 1024)
    run_id = _upload(client, {**SAMPLE, "big.c": "x" * 4096})["run_id"]
    listed = client.get(f"/agent/runs/{run_id}").json()
    assert listed["intake"]["skipped"][0]["path"] == "big.c"


def test_an_upload_of_nothing_but_oversized_files_says_so(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("agent.files.MAX_SINGLE_FILE_BYTES", 64)

    payload = _zip({"big.c": "x" * 4096})
    response = client.post("/agent/runs", files={"files": ("upload.zip", payload, "application/zip")})

    assert response.status_code == 400
    assert "너무 크거나 텍스트가 아니었습니다" in response.json()["detail"]


def test_the_total_size_cap_is_still_a_refusal(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("agent.files.MAX_UPLOAD_BYTES", 128)

    payload = _zip({f"f{i}.c": "x" * 64 for i in range(8)})
    response = client.post("/agent/runs", files={"files": ("upload.zip", payload, "application/zip")})

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "MB를 넘습니다" in detail
    assert "하위 폴더만 골라" in detail


def test_the_file_count_cap_is_still_a_refusal(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("agent.files.MAX_UPLOAD_FILES", 3)

    payload = _zip({f"f{i}.c": "int x;" for i in range(8)})
    response = client.post("/agent/runs", files={"files": ("upload.zip", payload, "application/zip")})

    assert response.status_code == 400
    assert "3개를 넘습니다" in response.json()["detail"]


def test_loose_files_are_capped_the_same_way_an_archive_is(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
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
    monkeypatch.setattr("agent.files.MAX_UPLOAD_BYTES", 128)

    body = _upload(client, {"src/app.c": "int x;", ".git/pack/big": "x" * 40_000})

    assert body["files"] == ["src/app.c"]


def test_a_mac_made_zip_does_not_take_the_upload_down(client: TestClient) -> None:
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
    assert body["intake"]["skipped"] == []


def test_a_binary_file_is_skipped_and_named(client: TestClient) -> None:
    body = _upload(client, {**SAMPLE, "src/blob.c": b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"})

    assert set(body["files"]) == {"src/app.c", "src/util.h"}
    assert body["intake"]["skipped"] == [{"path": "src/blob.c", "size": 16, "reason": "binary"}]


def test_text_that_merely_looks_odd_is_still_stored(client: TestClient) -> None:
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
    padded = ("int x;\n" * 2000).encode() + b"\x00tail\n"
    body = _upload(client, {"src/odd.c": padded})

    assert body["files"] == ["src/odd.c"]
    stored = client.get(f"/agent/runs/{body['run_id']}/file", params={"path": "src/odd.c"}).json()
    assert "\x00" not in stored["content"]
    assert "�" in stored["content"]


def test_starting_without_a_model_is_refused_rather_than_started(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(ENV_MODEL, raising=False)
    run_id = _upload(client)["run_id"]
    response = client.post(f"/agent/runs/{run_id}/inspect", json={})

    assert response.status_code == 503
    detail = response.json()["detail"]
    assert "AGENT_MODEL" in detail
    assert client.get(f"/agent/runs/{run_id}").json()["status"] != "inspecting"


def test_health_names_what_the_endpoint_actually_serves(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(ENV_MODEL, raising=False)
    monkeypatch.setattr("api.agent.meta.list_models", lambda _base: ["agent", "other"])

    body = client.get("/agent/health", params={"probe": "true"}).json()

    assert body["configured"] is False
    assert body["served_models"] == ["agent", "other"]
    assert body["model_is_served"] is False


def test_a_re_upload_names_the_run_that_already_has_it(client: TestClient) -> None:
    first = _upload(client)
    assert first["matches"] == [], "the first upload of a tree has nothing to match"

    second = _upload(client)

    assert [m["run_id"] for m in second["matches"]] == [first["run_id"]]
    match = second["matches"][0]
    assert match["file_count"] == 2
    assert match["status"] in {"indexed", "done"}


def test_one_changed_byte_is_a_different_tree(client: TestClient) -> None:
    _upload(client)
    edited = {**SAMPLE, "src/app.c": SAMPLE["src/app.c"] + "// touched\n"}

    assert _upload(client, edited)["matches"] == []


def test_a_missing_file_is_a_different_tree(client: TestClient) -> None:
    _upload(client)

    assert _upload(client, {"src/app.c": SAMPLE["src/app.c"]})["matches"] == []


def test_an_added_file_is_a_different_tree(client: TestClient) -> None:
    _upload(client)

    assert _upload(client, {**SAMPLE, "src/extra.c": "int extra;\n"})["matches"] == []


def test_a_stranger_s_run_is_never_offered(client: TestClient) -> None:
    payload = _zip(SAMPLE)
    theirs = client.post(
        "/agent/runs",
        files={"files": ("upload.zip", payload, "application/zip")},
        headers={"x-ssat-owner": "somebody-else"},
    )
    assert theirs.status_code == 200

    mine = client.post(
        "/agent/runs",
        files={"files": ("upload.zip", _zip(SAMPLE), "application/zip")},
        headers={"x-ssat-owner": "me"},
    )
    assert mine.json()["matches"] == []


def test_matches_are_newest_first(client: TestClient) -> None:
    older = _upload(client)["run_id"]
    newer = _upload(client)["run_id"]
    third = _upload(client)

    assert [m["run_id"] for m in third["matches"]] == [newer, older]


def test_a_cloned_tree_matches_an_uploaded_one(
    client: TestClient, git_remote: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import shutil

    if shutil.which("git") is None:
        pytest.skip("git is not installed")
    monkeypatch.setattr("agent.vcs.check_url", lambda url: url)

    first = client.post("/agent/runs/git", json={"url": str(git_remote), "ref": "main"}).json()
    second = client.post("/agent/runs/git", json={"url": str(git_remote), "ref": "main"}).json()

    assert [m["run_id"] for m in second["matches"]] == [first["run_id"]]


def test_cancelling_when_nothing_is_running_is_refused(client: TestClient) -> None:
    run_id = _upload(client)["run_id"]
    response = client.post(f"/agent/runs/{run_id}/cancel")

    assert response.status_code == 409
    assert "진행 중인 검사가 없습니다" in response.json()["detail"]


def test_watching_a_run_is_not_something_to_cancel(client: TestClient) -> None:
    import api.agent.channels as channels

    run_id = _upload(client)["run_id"]
    channels._channel(run_id)

    assert client.post(f"/agent/runs/{run_id}/cancel").status_code == 409


def test_cancelling_a_live_run_sets_the_flag_the_graph_reads(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import api.agent.channels as channels

    run_id = _upload(client)["run_id"]
    channel = channels._channel(run_id)
    channel.claimed = True

    response = client.post(f"/agent/runs/{run_id}/cancel")

    assert response.status_code == 200
    assert response.json()["cancelled"] is True
    assert channel.cancelled.is_set()


def test_cancelling_a_parked_run_also_wakes_it(client: TestClient) -> None:
    import api.agent.channels as channels

    run_id = _upload(client)["run_id"]
    channel = channels._channel(run_id)
    channel.claimed = True
    channel.waiting.set()

    client.post(f"/agent/runs/{run_id}/cancel")

    assert channel.cancelled.is_set()
    assert channel.commands.get_nowait() == {"action": "abort"}


def test_a_cancelled_run_is_not_reported_as_done(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ENV_MODEL, "agent")

    class Stopped:
        stopped = True

        def __init__(self, **kwargs: object) -> None:
            self._cancelled = kwargs.get("cancelled")

        def start(self, **_kwargs: object) -> None:
            return None

        interrupted = False

        def report(self):  # noqa: ANN202 - a stand-in for the real session
            from agent.schema import Report

            return Report(run_id="r")

        def close(self) -> None:
            return None

    monkeypatch.setattr("api.agent.inspection.InspectionSession", Stopped)
    run_id = _upload(client)["run_id"]

    assert client.post(f"/agent/runs/{run_id}/inspect").status_code == 200
    with client.stream("GET", f"/agent/runs/{run_id}/events") as stream:
        _collect_events(stream, limit=6)

    assert client.get(f"/agent/runs/{run_id}").json()["status"] == "cancelled"


def test_a_cancelled_run_finishes_instead_of_parking_at_a_breakpoint(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import api.agent.channels as channels

    monkeypatch.setenv(ENV_MODEL, "agent")
    monkeypatch.setattr("api.agent.inspection.INTERRUPT_TIMEOUT_SECONDS", 5.0)

    class CancelledMidWave:
        stopped = True
        interrupted = True
        next_nodes = ["plan"]
        checkpoint_id = "cp"

        def __init__(self, **kwargs: object) -> None:
            self._run_id = str(kwargs.get("run_id"))

        def start(self, **_kwargs: object) -> None:
            channels._channel(self._run_id).cancelled.set()

        def resume(self, **_kwargs: object) -> None:
            return None

        def report(self):  # noqa: ANN202 - a stand-in for the real session
            from agent.schema import Report

            return Report(run_id="r")

        def close(self) -> None:
            return None

    monkeypatch.setattr("api.agent.inspection.InspectionSession", CancelledMidWave)
    run_id = _upload(client)["run_id"]
    channel = channels._channel(run_id)

    with channel.listen() as events:
        assert client.post(f"/agent/runs/{run_id}/inspect").status_code == 200
        assert channel.finished.wait(2.0), "a cancelled run parked instead of finishing"
        seen = []
        while True:
            try:
                seen.append(events.get_nowait()["event"])
            except queue.Empty:
                break

    assert "run_interrupted" not in seen, "a cancelled run was reported as parked at a breakpoint"
    assert "run_finished" in seen
    assert client.get(f"/agent/runs/{run_id}").json()["status"] == "cancelled"


def test_stopping_a_run_does_not_stop_every_later_run_on_it(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import api.agent.channels as channels

    monkeypatch.setenv(ENV_MODEL, "agent")
    started: list[str] = []

    class Ordinary:
        stopped = False
        interrupted = False

        def __init__(self, **kwargs: object) -> None:
            self._cancelled = kwargs.get("cancelled")

        def start(self, **_kwargs: object) -> None:
            started.append("cancelled" if self._cancelled() else "running")  # type: ignore[operator]

        def report(self):  # noqa: ANN202 - a stand-in for the real session
            from agent.schema import Report

            return Report(run_id="r")

        def close(self) -> None:
            return None

    monkeypatch.setattr("api.agent.inspection.InspectionSession", Ordinary)
    run_id = _upload(client)["run_id"]
    channel = channels._channel(run_id)
    channel.claimed = True
    assert client.post(f"/agent/runs/{run_id}/cancel").status_code == 200
    assert channel.cancelled.is_set()
    channel.finished.set()

    assert client.post(f"/agent/runs/{run_id}/inspect", json={"force": True}).status_code == 200
    assert channel.finished.wait(2.0)

    assert started == ["running"], "a later run inherited the last stop"


def test_propose_says_there_is_no_model_in_the_reader_s_language(client: TestClient) -> None:
    run_id = _upload(client)["run_id"]
    paths = _paths_for(run_id)
    _report_with_fix(paths, replacement=None, excerpt="", start=1, end=1)

    response = client.post(f"/agent/runs/{run_id}/propose", json={"finding_id": "f1"})
    assert response.status_code == 503, response.text


def test_propose_sends_a_window_not_the_whole_file(client: TestClient, monkeypatch) -> None:
    from agent.config import AgentConfig, ENV_MODEL
    from agent.llm import Outcome
    from agent.schema import CandidateRemediation

    padding = "\n".join(f"// filler {n:05d} ------------------------------" for n in range(4_000))
    source = "#include <stdlib.h>\nvoid run(char *cmd) {\n  system(cmd);\n}\n" + padding + "\n"
    run_id = _upload(client, {"src/app.c": source})["run_id"]
    paths = _paths_for(run_id)
    _report_with_fix(paths, replacement=None, excerpt="  system(cmd);", start=3, end=3)

    monkeypatch.setenv(ENV_MODEL, "fake")
    seen: list[str] = []

    class Caller:
        def __init__(self, config):
            pass

        def call(self, schema, system, user, trace=None):
            seen.append(user)
            return Outcome.of(CandidateRemediation(summary="s", detail="d", replacement="  execv(cmd, 0);"))

    import agent.llm

    monkeypatch.setattr(agent.llm, "StructuredCaller", Caller)

    response = client.post(f"/agent/runs/{run_id}/propose", json={"finding_id": "f1"})
    assert response.status_code == 200, response.text

    budget = AgentConfig(model="fake").input_chars()
    assert len(source) > budget * 2, "the file must exceed the budget or this asserts nothing"
    assert seen, "the model was never asked"
    assert len(seen[0]) < budget * 1.5
    assert "system(cmd);" in seen[0]
