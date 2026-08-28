"""LangSmith tracing.

LangChain exports the traces; this names and tags them. A run makes hundreds of
calls, and untagged they are an undifferentiated column of "ChatOpenAI".
"""

from __future__ import annotations

import os
from typing import Any

from langchain_core.runnables import RunnableConfig

# LANGSMITH_* is current, LANGCHAIN_* the older spelling; langsmith honours both.
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
    """``langsmith.utils.get_env_var`` is lru_cached, so a LANGSMITH_* variable
    set from Python after langsmith is imported is otherwise ignored."""
    try:
        from langsmith.utils import get_env_var

        # Typed as an overload upstream, so the lru_cache attribute is invisible
        # to the checker even though it is there at runtime.
        get_env_var.cache_clear()  # type: ignore[attr-defined]
    except ImportError, AttributeError:  # pragma: no cover - upstream shape change
        pass


def is_enabled() -> bool:
    """Read directly rather than via ``langsmith.tracing_is_enabled``, which
    answers from its cache. A health endpoint wants what is configured now."""
    return any(_truthy(os.getenv(name)) for name in TRACING_VARS)


def _effective() -> bool:
    """What langsmith believes, cache and all. Differs from :func:`is_enabled`
    exactly when the environment was set too late."""
    try:
        from langsmith.utils import tracing_is_enabled
    except ImportError:  # pragma: no cover - langsmith ships with langchain
        return False
    return bool(tracing_is_enabled())


def status() -> dict[str, Any]:
    """Reports *why* it is off, not just that it is: "on but no key" and "not
    switched on" need different fixes and look identical otherwise."""
    enabled = is_enabled()
    has_key = _first(API_KEY_VARS) is not None
    detail: str | None = None
    if not enabled:
        detail = f"set {TRACING_VARS[0]}=true to enable"
    elif not has_key:
        detail = f"tracing is on but no API key is set ({API_KEY_VARS[0]}); traces will not be delivered"
    elif not _effective():
        # Configured correctly but too late: langsmith cached the variable as
        # unset before it was assigned. Set it in the shell, not in Python.
        detail = "tracing is configured but langsmith read the environment before it was set; set it before starting the process"

    return {
        "enabled": enabled,
        "project": _first(PROJECT_VARS) or DEFAULT_PROJECT,
        "endpoint": _first(ENDPOINT_VARS),
        "api_key_set": has_key,
        "detail": detail,
    }


def apply_default_project() -> None:
    """Otherwise runs land in LangSmith's ``default`` project."""
    if _first(PROJECT_VARS) is None:
        os.environ[PROJECT_VARS[0]] = DEFAULT_PROJECT
        # Without this the assignment above does nothing: langsmith has already
        # cached the miss.
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
    """Names and tags one model call. ``step`` is analyse/gather/verify;
    ``subject`` lands in the span name so the trace list reads at a glance.

    ``lens`` is which specialist raised the claim this call is about. Only
    gather and verify have one, and without it a reader can see that a claim was
    investigated and refuted but not who made it -- the hand-off from analysis to
    verification was the one edge in the run that left no record.
    """
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
