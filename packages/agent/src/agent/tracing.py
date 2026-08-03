"""LangSmith tracing.

LangChain traces itself when ``LANGSMITH_TRACING=true`` and an API key are in
the environment; nothing here turns it on. What this adds is the part that makes
a trace usable afterwards.

A chunk-by-chunk run makes hundreds of model calls. Untagged they arrive as an
undifferentiated column of "ChatOpenAI", and answering "why was this finding
refuted" means opening spans until you find the right one. So every call is
named for what it was doing and to what -- ``analyse:fetch_firmware``,
``verify:CWE-78 download.c:28`` -- and carries the run id, chunk id, file and
symbol as metadata, which are the fields you would want to filter on.
"""

from __future__ import annotations

import os
from typing import Any

from langchain_core.runnables import RunnableConfig

#: Either enables tracing. LANGSMITH_* is current, LANGCHAIN_* is the older
#: spelling; both are honoured by langsmith itself, so both are reported here
#: rather than quietly preferring one.
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
    """Make langsmith re-read the environment.

    ``langsmith.utils.get_env_var`` is ``functools.lru_cache``d, so langsmith
    reads each variable once per process and never again. Anything setting a
    LANGSMITH_* variable from Python -- as :func:`apply_default_project` does --
    has to clear that cache or the change is silently ignored.
    """
    try:
        from langsmith.utils import get_env_var

        # Typed as an overload upstream, so the lru_cache attribute is invisible
        # to the checker even though it is there at runtime.
        get_env_var.cache_clear()  # type: ignore[attr-defined]
    except ImportError, AttributeError:  # pragma: no cover - upstream shape change
        pass


def is_enabled() -> bool:
    """True if tracing is switched on in the environment.

    Read directly rather than delegated to ``langsmith.tracing_is_enabled``,
    which answers from that cache and so reports whatever was true when
    langsmith was first imported. For a health endpoint the useful answer is
    what is configured now.
    """
    return any(_truthy(os.getenv(name)) for name in TRACING_VARS)


def _effective() -> bool:
    """What langsmith itself currently believes, cache and all.

    Differs from :func:`is_enabled` exactly when the environment was set too
    late, which is the failure worth reporting.
    """
    try:
        from langsmith.utils import tracing_is_enabled
    except ImportError:  # pragma: no cover - langsmith ships with langchain
        return False
    return bool(tracing_is_enabled())


def status() -> dict[str, Any]:
    """What tracing is doing, for ``/agent/health`` and the CLI.

    Reports the *reason* it is off rather than just the fact, because "on but
    the key is missing" and "not switched on" need different fixes and look
    identical from the outside.
    """
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
    """Group this tool's traces under one project unless told otherwise.

    Without it, runs land in LangSmith's ``default`` project alongside anything
    else on the machine.
    """
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
) -> RunnableConfig:
    """A LangChain ``config`` that names and tags one model call.

    ``step`` is ``analyse``, ``gather`` or ``verify``. ``subject`` is whatever
    identifies the thing being worked on, and lands in the span name so the
    trace list is readable without opening anything.
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
        }.items()
        if value is not None
    }
    tags = [f"step:{step}"]
    if run_id:
        tags.append(f"run:{run_id}")
    return RunnableConfig(run_name=name, tags=tags, metadata=metadata)
