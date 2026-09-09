from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

log = logging.getLogger(__name__)
DEFAULT_CANDIDATES: tuple[str, ...] = (
    "http://localhost:8000/v1",
    "http://localhost:8001/v1",
)

PROBE_TIMEOUT = 3.0


@dataclass(frozen=True)
class Endpoint:
    base_url: str
    models: tuple[str, ...]

    @property
    def only_model(self) -> str | None:
        return self.models[0] if len(self.models) == 1 else None


def list_models(base_url: str, timeout: float = PROBE_TIMEOUT) -> list[str]:
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
    models = list_models(base_url, timeout)
    return Endpoint(base_url=base_url, models=tuple(models)) if models else None


def discover(
    candidates: tuple[str, ...] = DEFAULT_CANDIDATES,
    timeout: float = PROBE_TIMEOUT,
) -> list[Endpoint]:
    found = [probe(url, timeout) for url in candidates]
    return [endpoint for endpoint in found if endpoint is not None]
