"""Runtime configuration. Every setting has an environment override, so the API,
the CLI and the MCP subprocess agree without threading config through layers."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from .schema import LENSES, Lens

# 8001, not vLLM's default 8000, which the SSAT API owns.
DEFAULT_BASE_URL = "http://localhost:8001/v1"

# Empty on purpose: a wrong model produces plausible nonsense, so unset is an
# error rather than a surprise.
DEFAULT_MODEL = ""

ENV_BASE_URL = "AGENT_BASE_URL"
ENV_MODEL = "AGENT_MODEL"
ENV_API_KEY = "AGENT_API_KEY"
ENV_RUNS_DIR = "AGENT_RUNS_DIR"
ENV_PROMPTS_FILE = "AGENT_PROMPTS_FILE"
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


def _env_lenses(name: str) -> tuple[Lens, ...]:
    """A comma-separated subset of the specialists, or all of them.

    An unknown name is dropped rather than raising: this is read at import time
    in a dozen places, and a typo in an environment variable should not stop the
    server from starting. An empty result falls back to all four, because "run
    no analysts at all" is never what was meant.
    """
    raw = os.getenv(name)
    if not raw:
        return LENSES
    picked = tuple(lens for lens in LENSES if lens in {part.strip() for part in raw.split(",")})
    return picked or LENSES


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


def default_prompts_file() -> Path:
    """Beside the runs, for the same reason: it is tuned data, not source.

    The defaults live in ``prompts.py``, in git. This file only ever holds what
    someone has deliberately changed.
    """
    override = os.getenv(ENV_PROMPTS_FILE)
    if override:
        return Path(override)
    return default_runs_dir().parent / "prompts.json"


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

    # -- how wide the run goes ------------------------------------------------
    #
    # Chunks at one call depth cannot need each other's notes, so they can be
    # inspected together. Width is how many at once; concurrency is the ceiling
    # on requests actually in flight, which is what stops `width x lenses`
    # arriving at the endpoint as one thundering herd.
    # 16 is `wave_width` times the number of specialists: enough for one wave's
    # analyses to go at once, and no more. Measured rather than guessed -- on
    # the sample tree, 8 spent 2m31 and 16 spent 2m00 on identical work, because
    # a batching server answers sixteen requests in not much longer than eight.
    wave_width: int = field(default_factory=lambda: _env_int("AGENT_WAVE_WIDTH", 4))
    max_concurrency: int = field(default_factory=lambda: _env_int("AGENT_MAX_CONCURRENCY", 16))

    # Which specialists run. Narrowing this is the lever for a small model that
    # cannot hold four separate briefs; `AGENT_LENSES=injection` is a fast,
    # single-purpose scan.
    lenses: tuple[Lens, ...] = field(default_factory=lambda: _env_lenses("AGENT_LENSES"))

    # The screening pass in front of the specialists. Off means every chunk gets
    # every lens, which is thorough, slow, and occasionally what you want.
    triage: bool = field(default_factory=lambda: os.getenv("AGENT_TRIAGE", "1") != "0")

    sandbox: str = field(default_factory=lambda: os.getenv(ENV_SANDBOX, "bwrap"))
    sandbox_timeout: int = field(default_factory=lambda: _env_int("AGENT_SANDBOX_TIMEOUT", 20))

    runs_dir: Path = field(default_factory=default_runs_dir)
    prompts_file: Path = field(default_factory=default_prompts_file)

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
