"""Runtime configuration. Every setting has an environment override, so the API,
the CLI and the MCP subprocess agree without threading config through layers."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# 8001, not vLLM's default 8000, which the SSAT API owns.
DEFAULT_BASE_URL = "http://localhost:8001/v1"

# Empty on purpose: a wrong model produces plausible nonsense, so unset is an
# error rather than a surprise.
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
    """Under ``artifacts/``, which is gitignored: uploads are generated data."""
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
    # vLLM ignores it; the OpenAI client insists on one being present.
    api_key: str = field(default_factory=lambda: os.getenv(ENV_API_KEY, "-"))
    temperature: float = 0.0

    # Context packs are trimmed to this rather than overflowing the window.
    context_char_budget: int = field(default_factory=lambda: _env_int("AGENT_CONTEXT_CHARS", 24_000))
    max_chunk_chars: int = field(default_factory=lambda: _env_int("AGENT_MAX_CHUNK_CHARS", 12_000))
    max_callee_notes: int = field(default_factory=lambda: _env_int("AGENT_MAX_CALLEE_NOTES", 12))
    # Verification dominates cost on a noisy chunk; cap it so one chunk cannot
    # stall the run.
    max_verify_per_chunk: int = field(default_factory=lambda: _env_int("AGENT_MAX_VERIFY_PER_CHUNK", 8))
    request_timeout: int = field(default_factory=lambda: _env_int("AGENT_REQUEST_TIMEOUT", 300))
    max_retries: int = field(default_factory=lambda: _env_int("AGENT_MAX_RETRIES", 2))
    # Guided decoding guarantees shape, not termination: a model too small for
    # the schema emits a valid prefix until it runs out of context. Observed a
    # 0.5B spend 8048 tokens without closing the object.
    max_tokens: int = field(default_factory=lambda: _env_int("AGENT_MAX_TOKENS", 4096))

    # vLLM needs --tool-call-parser for this; without it the run falls back to
    # context-only verification and says so once.
    enable_tools: bool = field(default_factory=lambda: os.getenv("AGENT_TOOLS", "1") != "0")
    max_tool_calls: int = field(default_factory=lambda: _env_int("AGENT_MAX_TOOL_CALLS", 4))

    sandbox: str = field(default_factory=lambda: os.getenv(ENV_SANDBOX, "bwrap"))
    sandbox_timeout: int = field(default_factory=lambda: _env_int("AGENT_SANDBOX_TIMEOUT", 20))

    runs_dir: Path = field(default_factory=default_runs_dir)

    def require_model(self) -> str:
        """Called before the first request, so a misconfigured deployment fails
        at startup rather than at chunk 400 of 600."""
        if not self.model:
            raise RuntimeError(
                f"No model configured. Set {ENV_MODEL} to a model served by your endpoint "
                f"({ENV_BASE_URL}, currently {self.base_url!r}). "
                "There is no default on purpose: a wrong model silently produces plausible nonsense."
            )
        return self.model
