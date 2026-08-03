"""Asking the server what it serves.

This exists so ``AGENT_MODEL`` never has to be guessed. It is also the code that
runs when nothing is working, so it has to fail quietly and informatively rather
than raise -- a discovery helper that throws is useless for discovery.
"""

from __future__ import annotations

import httpx
import pytest

from agent.endpoint import DEFAULT_CANDIDATES, Endpoint, discover, list_models, probe


def _transport(handler):
    return httpx.MockTransport(handler)


@pytest.fixture
def mock_get(monkeypatch: pytest.MonkeyPatch):
    """Replace httpx.get with a scripted responder keyed by URL."""

    def install(routes: dict[str, object]) -> list[str]:
        seen: list[str] = []

        def fake_get(url: str, **kwargs: object) -> httpx.Response:
            seen.append(url)
            outcome = routes.get(url)
            if outcome is None:
                raise httpx.ConnectError("connection refused", request=httpx.Request("GET", url))
            if isinstance(outcome, Exception):
                raise outcome
            return httpx.Response(200, json=outcome, request=httpx.Request("GET", url))

        monkeypatch.setattr(httpx, "get", fake_get)
        return seen

    return install


def _models(*ids: str) -> dict[str, object]:
    return {"object": "list", "data": [{"id": i, "object": "model"} for i in ids]}


def test_list_models_returns_the_served_ids(mock_get) -> None:
    mock_get({"http://localhost:8001/v1/models": _models("agent", "other")})
    assert list_models("http://localhost:8001/v1") == ["agent", "other"]


def test_trailing_slash_does_not_double_up(mock_get) -> None:
    seen = mock_get({"http://localhost:8001/v1/models": _models("agent")})
    assert list_models("http://localhost:8001/v1/") == ["agent"]
    assert seen == ["http://localhost:8001/v1/models"]


def test_an_unreachable_endpoint_is_empty_not_an_exception(mock_get) -> None:
    """Callers use this to decide whether a server is up at all."""
    mock_get({})
    assert list_models("http://localhost:9999/v1") == []


def test_malformed_payloads_are_survived(mock_get) -> None:
    for payload in ({"data": "not a list"}, {}, {"data": [{"no_id": 1}, "junk"]}):
        mock_get({"http://x/v1/models": payload})
        assert list_models("http://x/v1") == []


def test_probe_returns_none_when_nothing_is_served(mock_get) -> None:
    """An endpoint answering with zero models is not a usable endpoint."""
    mock_get({"http://x/v1/models": _models()})
    assert probe("http://x/v1") is None


def test_probe_returns_the_endpoint_when_it_answers(mock_get) -> None:
    mock_get({"http://x/v1/models": _models("agent")})
    found = probe("http://x/v1")
    assert found == Endpoint(base_url="http://x/v1", models=("agent",))
    assert found.only_model == "agent"


def test_only_model_is_none_when_the_choice_is_ambiguous(mock_get) -> None:
    mock_get({"http://x/v1/models": _models("a", "b")})
    found = probe("http://x/v1")
    assert found is not None and found.only_model is None


def test_discover_skips_dead_candidates_and_keeps_order(mock_get) -> None:
    mock_get({"http://localhost:8000/v1/models": _models("second")})
    found = discover()
    assert [e.base_url for e in found] == ["http://localhost:8000/v1"]


def test_discover_returns_every_live_candidate(mock_get) -> None:
    mock_get(
        {
            "http://localhost:8001/v1/models": _models("first"),
            "http://localhost:8000/v1/models": _models("second"),
        }
    )
    assert [e.models[0] for e in discover()] == ["first", "second"]


def test_the_script_port_is_probed_before_vllms_default() -> None:
    """8000 belongs to the SSAT API, so scripts/vllm.sh serves 8001 and that is
    the port checked first."""
    assert DEFAULT_CANDIDATES[0].endswith(":8001/v1")
    assert DEFAULT_CANDIDATES[1].endswith(":8000/v1")


def test_no_ollama_port_is_probed() -> None:
    """vLLM only. Ollama's 11434 was dropped deliberately."""
    assert not any("11434" in url for url in DEFAULT_CANDIDATES)
