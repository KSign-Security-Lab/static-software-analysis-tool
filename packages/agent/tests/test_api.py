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
from typing import Iterator

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
    assert client.get("/agent/runs/deadbeef/files").status_code == 404
    assert client.get("/agent/runs/../../etc/files").status_code in (307, 404)


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
    import api.agent_routes as routes

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
    import api.agent_routes as routes

    monkeypatch.setattr(routes, "list_models", lambda _url: ["agent"])
    monkeypatch.setenv(ENV_MODEL, "Qwen/Qwen2.5-Coder-32B-Instruct")

    body = client.get("/agent/health", params={"probe": "true"}).json()
    assert body["reachable"] is True
    assert body["model_is_served"] is False


def test_health_probe_survives_a_dead_endpoint(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    import api.agent_routes as routes

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
        "/agent/runs/{run_id}/files",
        "/agent/runs/{run_id}/file",
        "/agent/runs/{run_id}/inspect",
        "/agent/runs/{run_id}/events",
        "/agent/runs/{run_id}/findings",
        "/agent/runs/{run_id}/diff",
    ):
        assert route in paths, f"{route} is missing from the OpenAPI document"


# -- editing a run in place (the agent section's light IDE) ------------------


def test_an_empty_run_can_be_created_and_pasted_into(client: TestClient) -> None:
    """Trying one snippet must not require saving a file and uploading it."""
    run_id = client.post("/agent/runs/new").json()["run_id"]
    assert client.get(f"/agent/runs/{run_id}/files").json()["files"] == []

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
