from __future__ import annotations

import os
from typing import Any

from langchain_core.runnables import RunnableConfig

TRACING_VARS = ("LANGSMITH_TRACING", "LANGCHAIN_TRACING_V2")
API_KEY_VARS = ("LANGSMITH_API_KEY", "LANGCHAIN_API_KEY")
PROJECT_VARS = ("LANGSMITH_PROJECT", "LANGCHAIN_PROJECT")
ENDPOINT_VARS = ("LANGSMITH_ENDPOINT", "LANGCHAIN_ENDPOINT")
DEFAULT_PROJECT = "ssat-agent"


def _first(names: tuple[str, ...]) -> str | None:
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return None


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def refresh_env_cache() -> None:
    try:
        from langsmith.utils import get_env_var

        get_env_var.cache_clear()  # type: ignore[attr-defined]
    except ImportError, AttributeError:  # pragma: no cover - upstream shape change
        pass


def is_enabled() -> bool:
    return any(_truthy(os.getenv(name)) for name in TRACING_VARS)


def _effective() -> bool:
    try:
        from langsmith.utils import tracing_is_enabled
    except ImportError:  # pragma: no cover - langsmith ships with langchain
        return False
    return bool(tracing_is_enabled())


def status() -> dict[str, Any]:
    enabled = is_enabled()
    has_key = _first(API_KEY_VARS) is not None
    detail: str | None = None
    if not enabled:
        detail = f"set {TRACING_VARS[0]}=true to enable"
    elif not has_key:
        detail = f"tracing is on but no API key is set ({API_KEY_VARS[0]}); traces will not be delivered"
    elif not _effective():
        detail = "tracing is configured but langsmith read the environment before it was set; set it before starting the process"

    return {
        "enabled": enabled,
        "project": _first(PROJECT_VARS) or DEFAULT_PROJECT,
        "endpoint": _first(ENDPOINT_VARS),
        "api_key_set": has_key,
        "detail": detail,
    }


def apply_default_project() -> None:
    if _first(PROJECT_VARS) is None:
        os.environ[PROJECT_VARS[0]] = DEFAULT_PROJECT
        refresh_env_cache()


def call_config(
    *,
    step: str,
    run_id: str | None = None,
    chunk_id: str | None = None,
    file: str | None = None,
    symbol: str | None = None,
    subject: str | None = None,
    lens: str | None = None,
) -> RunnableConfig:
    name = f"{step}:{subject}" if subject else step
    metadata = {
        key: value
        for key, value in {
            "agent_run_id": run_id,
            "chunk_id": chunk_id,
            "file": file,
            "symbol": symbol,
            "step": step,
            "lens": lens,
        }.items()
        if value is not None
    }
    tags = [f"step:{step}"]
    if run_id:
        tags.append(f"run:{run_id}")
    return RunnableConfig(run_name=name, tags=tags, metadata=metadata)
