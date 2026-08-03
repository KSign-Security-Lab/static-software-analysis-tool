"""Runtime configuration.

The served model and its endpoint are deployment facts, not code facts: the same
package runs against a vLLM server in production and whatever OpenAI-compatible
endpoint a developer has locally. Nothing here hard-codes a model id.

Every setting has an environment override so the API server, the CLI and the MCP
subprocess all agree without passing configuration through three layers.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

#: vLLM's OpenAI-compatible server listens here by default.
DEFAULT_BASE_URL = "http://localhost:8000/v1"

#: Deliberately empty. A wrong default model produces confident nonsense that
#: looks like a working system, so an unset model is an error at startup rather
#: than a surprise mid-run.
DEFAULT_MODEL = ""

ENV_BASE_URL = "AGENT_BASE_URL"
ENV_MODEL = "AGENT_MODEL"
ENV_API_KEY = "AGENT_API_KEY"
ENV_RUNS_DIR = "AGENT_RUNS_DIR"
ENV_SANDBOX = "AGENT_SANDBOX"
ENV_RUN_ROOT = "AGENT_RUN_ROOT"
ENV_INDEX_DB = "AGENT_INDEX_DB"


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def default_runs_dir() -> Path:
    """Where run workspaces live.

    Under ``artifacts/`` because uploads are generated data, not source: the
    directory is gitignored and documented as safe to delete.
    """
    override = os.getenv(ENV_RUNS_DIR)
    if override:
        return Path(override)
    current = Path.cwd().resolve()
    for candidate in (current, *current.parents):
        if (candidate / "pyproject.toml").exists():
            return candidate / "artifacts" / "agent-runs"
    return current / "artifacts" / "agent-runs"


@dataclass
class AgentConfig:
    """Everything the agent needs to run one inspection."""

    base_url: str = field(default_factory=lambda: os.getenv(ENV_BASE_URL, DEFAULT_BASE_URL))
    model: str = field(default_factory=lambda: os.getenv(ENV_MODEL, DEFAULT_MODEL))
    #: vLLM ignores the key but the OpenAI client insists on one being present.
    api_key: str = field(default_factory=lambda: os.getenv(ENV_API_KEY, "-"))
    temperature: float = 0.0

    #: Ceiling on how much source goes into one analyse call. Context packs are
    #: trimmed to fit rather than being allowed to overflow the model's window.
    context_char_budget: int = field(default_factory=lambda: _env_int("AGENT_CONTEXT_CHARS", 24_000))
    #: A chunk longer than this is analysed but its body is truncated; a 3000-line
    #: generated function is not something the model can reason about anyway.
    max_chunk_chars: int = field(default_factory=lambda: _env_int("AGENT_MAX_CHUNK_CHARS", 12_000))
    #: Callee notes injected per chunk, most-recently-relevant first.
    max_callee_notes: int = field(default_factory=lambda: _env_int("AGENT_MAX_CALLEE_NOTES", 12))
    #: Verification is a second model call per candidate, so it dominates cost
    #: on a noisy chunk. Cap it rather than letting one chunk stall the run.
    max_verify_per_chunk: int = field(default_factory=lambda: _env_int("AGENT_MAX_VERIFY_PER_CHUNK", 8))
    request_timeout: int = field(default_factory=lambda: _env_int("AGENT_REQUEST_TIMEOUT", 300))
    max_retries: int = field(default_factory=lambda: _env_int("AGENT_MAX_RETRIES", 2))

    #: "bwrap", "docker" or "none".
    sandbox: str = field(default_factory=lambda: os.getenv(ENV_SANDBOX, "bwrap"))
    sandbox_timeout: int = field(default_factory=lambda: _env_int("AGENT_SANDBOX_TIMEOUT", 20))

    runs_dir: Path = field(default_factory=default_runs_dir)

    def require_model(self) -> str:
        """The configured model, or a clear failure.

        Called before the first request so a misconfigured deployment fails at
        startup with an actionable message instead of at chunk 400 of 600.
        """
        if not self.model:
            raise RuntimeError(
                f"No model configured. Set {ENV_MODEL} to a model served by your endpoint "
                f"({ENV_BASE_URL}, currently {self.base_url!r}). "
                "There is no default on purpose: a wrong model silently produces plausible nonsense."
            )
        return self.model
