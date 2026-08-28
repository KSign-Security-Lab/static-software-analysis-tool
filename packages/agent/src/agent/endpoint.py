"""Talking to the model server about itself.

``AGENT_MODEL`` has to be the id the server reports, not the Hugging Face path
it was loaded from -- ``Qwen/Qwen2.5-Coder-32B-Instruct`` versus whatever
``--served-model-name`` set. Getting that wrong is the usual first failure, and
the fix is to ask the server rather than to remember.

Shared by the CLI and by ``/agent/health`` so there is one implementation of
"what is actually running", not one per front end.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

log = logging.getLogger(__name__)

# 8001 is what the compose vllm service publishes; 8000 is vLLM's own
# default, which collides with the SSAT API.
DEFAULT_CANDIDATES: tuple[str, ...] = (
    "http://localhost:8001/v1",
    "http://localhost:8000/v1",
)

PROBE_TIMEOUT = 3.0


@dataclass(frozen=True)
class Endpoint:
    """A reachable OpenAI-compatible server and what it serves."""

    base_url: str
    models: tuple[str, ...]

    @property
    def only_model(self) -> str | None:
        """The single served id, when there is exactly one."""
        return self.models[0] if len(self.models) == 1 else None


def list_models(base_url: str, timeout: float = PROBE_TIMEOUT) -> list[str]:
    """Model ids the endpoint reports, or [] if it cannot be reached.

    Never raises: callers use this to decide whether a server is up, and an
    exception is not more informative than an empty list.
    """
    url = base_url.rstrip("/") + "/models"
    try:
        response = httpx.get(url, timeout=timeout)
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as err:
        log.debug("no models from %s: %s", url, err)
        return []

    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, list):
        return []
    return [entry["id"] for entry in data if isinstance(entry, dict) and isinstance(entry.get("id"), str)]


def context_window(base_url: str, model: str, timeout: float = PROBE_TIMEOUT) -> int | None:
    """How many tokens the endpoint will accept for ``model``, if it says.

    vLLM reports `max_model_len` per entry on `/v1/models`. Worth asking rather
    than assuming: every budget in this package was a character count invented
    against a window nobody had read, and a run that overflows says so as an
    error from the endpoint rather than as anything the agent could plan around.

    Never raises, for the same reason as :func:`list_models`. ``None`` means the
    endpoint did not say, which is different from a small window.
    """
    url = base_url.rstrip("/") + "/models"
    try:
        response = httpx.get(url, timeout=timeout)
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as err:
        log.debug("no window from %s: %s", url, err)
        return None

    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, list):
        return None
    for entry in data:
        if not isinstance(entry, dict) or entry.get("id") != model:
            continue
        window = entry.get("max_model_len")
        return window if isinstance(window, int) and window > 0 else None
    return None


def probe(base_url: str, timeout: float = PROBE_TIMEOUT) -> Endpoint | None:
    """An :class:`Endpoint` if the server answers with at least one model."""
    models = list_models(base_url, timeout)
    return Endpoint(base_url=base_url, models=tuple(models)) if models else None


def discover(
    candidates: tuple[str, ...] = DEFAULT_CANDIDATES,
    timeout: float = PROBE_TIMEOUT,
) -> list[Endpoint]:
    """Every candidate that is up, in the order given."""
    found = [probe(url, timeout) for url in candidates]
    return [endpoint for endpoint in found if endpoint is not None]
