"""LangSmith wiring.

Tracing itself is LangChain's; what is tested here is the part that makes a
trace usable. A chunk-by-chunk run makes hundreds of calls, and untagged they
are an undifferentiated column of "ChatOpenAI".
"""

from __future__ import annotations

import pytest

from agent.tracing import (
    API_KEY_VARS,
    DEFAULT_PROJECT,
    PROJECT_VARS,
    TRACING_VARS,
    apply_default_project,
    call_config,
    refresh_env_cache,
    is_enabled,
    status,
)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in TRACING_VARS + API_KEY_VARS + PROJECT_VARS:
        monkeypatch.delenv(name, raising=False)


def test_tracing_is_off_by_default() -> None:
    assert is_enabled() is False
    assert status()["enabled"] is False


@pytest.mark.parametrize("var", TRACING_VARS)
def test_either_spelling_enables_tracing(var: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """LANGSMITH_* is current and LANGCHAIN_* is the older name; langsmith
    honours both, so neither may be quietly ignored here."""
    monkeypatch.setenv(var, "true")
    assert is_enabled() is True


def test_status_explains_why_it_is_off_rather_than_only_that_it_is() -> None:
    detail = status()["detail"]
    assert detail and TRACING_VARS[0] in detail


def test_status_flags_tracing_enabled_with_no_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """The failure that looks like success: switched on, exporting nowhere."""
    monkeypatch.setenv(TRACING_VARS[0], "true")
    body = status()
    assert body["enabled"] is True
    assert body["api_key_set"] is False
    assert body["detail"] and "no API key" in body["detail"]


def test_status_catches_the_environment_being_set_too_late(monkeypatch: pytest.MonkeyPatch) -> None:
    """langsmith lru_caches its env reads, so a variable set after it is first
    touched is silently ignored -- the trap this reports on."""
    monkeypatch.setenv(TRACING_VARS[0], "true")
    monkeypatch.setenv(API_KEY_VARS[0], "ls-fake")
    refresh_env_cache()
    from langsmith.utils import tracing_is_enabled

    assert tracing_is_enabled() is True, "clearing the cache should make the setting take effect"


def test_refreshing_the_cache_is_what_makes_a_late_assignment_work(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from langsmith.utils import get_env_var, tracing_is_enabled

    get_env_var.cache_clear()
    assert tracing_is_enabled() is False
    monkeypatch.setenv(TRACING_VARS[0], "true")
    assert tracing_is_enabled() is False, "expected the cached miss to win"
    refresh_env_cache()
    assert tracing_is_enabled() is True


def test_default_project_groups_runs_but_never_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    apply_default_project()
    assert status()["project"] == DEFAULT_PROJECT

    monkeypatch.setenv(PROJECT_VARS[0], "my-project")
    apply_default_project()
    assert status()["project"] == "my-project"


def test_call_config_names_the_span_for_what_it_did() -> None:
    """The span list should be readable without opening anything."""
    config = call_config(step="analyse", subject="fetch_firmware")
    assert config["run_name"] == "analyse:fetch_firmware"

    verify = call_config(step="verify", subject="CWE-78 download.c:28")
    assert verify["run_name"] == "verify:CWE-78 download.c:28"


def test_call_config_carries_the_fields_worth_filtering_on() -> None:
    config = call_config(
        step="verify",
        run_id="run123",
        chunk_id="chunk456",
        file="download.c",
        symbol="fetch_firmware",
        subject="CWE-78",
    )
    metadata = config["metadata"]
    assert metadata["agent_run_id"] == "run123"
    assert metadata["chunk_id"] == "chunk456"
    assert metadata["file"] == "download.c"
    assert metadata["symbol"] == "fetch_firmware"
    assert metadata["step"] == "verify"
    assert "step:verify" in config["tags"]
    assert "run:run123" in config["tags"]


def test_call_config_omits_absent_fields_rather_than_sending_nulls() -> None:
    config = call_config(step="analyse")
    assert config["metadata"] == {"step": "analyse"}
    assert config["tags"] == ["step:analyse"]
    assert config["run_name"] == "analyse"


def test_the_loop_tags_every_call_it_makes(tmp_path) -> None:
    """End to end: a run must produce named spans, not anonymous ones."""
    from agent.config import AgentConfig
    from agent.graph.build import run_inspection
    from agent.index import ChunkStore, build_index

    from test_graph import ScriptedCaller, _finding
    from agent.schema import ChunkAnalysis

    root = tmp_path / "src"
    root.mkdir()
    (root / "app.c").write_text(
        '#include <stdlib.h>\nvoid run(const char *a) { char c[64]; sprintf(c, "%s", a); system(c); }\n',
        encoding="utf-8",
    )
    store = ChunkStore(tmp_path / "index.db")
    build_index(root, store)

    caller = ScriptedCaller(analyses={"run": ChunkAnalysis(findings=[_finding("system(c);")])})
    run_inspection(
        run_id="r-abc",
        root=root,
        store=store,
        config=AgentConfig(model="fake", enable_tools=False),
        caller=caller,  # type: ignore[arg-type]
    )

    traces = [t for t in caller.traces if t]
    assert traces, "no call was tagged"
    assert all("step:" in tag for t in traces for tag in t["tags"] if tag.startswith("step"))
    assert any(t["run_name"].startswith("triage:") for t in traces)
    assert any(t["run_name"].startswith("lens:memory:") for t in traces), "a specialist should name its lens"
    assert any(t["run_name"].startswith("verify:") for t in traces)
    assert all(t["metadata"]["agent_run_id"] == "r-abc" for t in traces)
    store.close()
