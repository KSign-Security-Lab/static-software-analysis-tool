from __future__ import annotations

import logging
import os
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from .schema import LENSES, Lens

log = logging.getLogger(__name__)
DEFAULT_BASE_URL = "http://localhost:4403/v1"
DEFAULT_MODEL = ""
ENV_BASE_URL = "AGENT_BASE_URL"
ENV_MODEL = "AGENT_MODEL"
ENV_API_KEY = "AGENT_API_KEY"
ENV_DATABASE_URL = "AGENT_DATABASE_URL"
ENV_PROMPTS_FILE = "AGENT_PROMPTS_FILE"
ENV_CORPUS_DIR = "AGENT_CORPUS_DIR"
ENV_SANDBOX = "AGENT_SANDBOX"
ENV_REASONING_EFFORT = "AGENT_REASONING_EFFORT"
ENV_RUN_ID = "AGENT_RUN_ID"
ENV_ENV_FILE = "AGENT_ENV_FILE"


def repo_root() -> Path:
    current = Path.cwd().resolve()
    for candidate in (current, *current.parents):
        if (candidate / "pyproject.toml").exists():
            return candidate
    return current


def load_env_file(path: Path | None = None) -> Path | None:
    """Fill unset variables from a `.env` file, returning the file that was read.

    The real environment always wins, so an exported value beats the file and a
    missing file is not an error. `AGENT_ENV_FILE` points somewhere else, which
    is also how a test keeps the developer's own `.env` out of its way.
    """
    target = path or Path(os.getenv(ENV_ENV_FILE) or repo_root() / ".env")
    try:
        text = target.read_text(encoding="utf-8")
    except OSError:
        return None
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), os.path.expandvars(value.strip().strip("\"'")))
    return target


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_lenses(name: str) -> tuple[Lens, ...]:
    raw = os.getenv(name)
    if not raw:
        return LENSES
    picked = tuple(lens for lens in LENSES if lens in {part.strip() for part in raw.split(",")})
    return picked or LENSES


def _env_globs(name: str) -> tuple[str, ...]:
    raw = os.getenv(name)
    if not raw:
        return ()
    return tuple(part.strip() for part in raw.split(",") if part.strip())


DEFAULT_DATABASE_URL = "postgresql+psycopg://ssat:ssat@localhost:4402/ssat"


def default_database_url() -> str:
    return os.getenv(ENV_DATABASE_URL, DEFAULT_DATABASE_URL)


def default_prompts_file() -> Path:
    override = os.getenv(ENV_PROMPTS_FILE)
    if override:
        return Path(override)
    return repo_root() / "artifacts" / "prompts.json"


def default_corpus_dir() -> Path:
    override = os.getenv(ENV_CORPUS_DIR)
    if override:
        return Path(override)
    return repo_root() / "corpus"


@dataclass
class AgentConfig:
    base_url: str = field(default_factory=lambda: os.getenv(ENV_BASE_URL, DEFAULT_BASE_URL))
    model: str = field(default_factory=lambda: os.getenv(ENV_MODEL, DEFAULT_MODEL))
    api_key: str = field(default_factory=lambda: os.getenv(ENV_API_KEY, "-"))
    temperature: float = 0.0
    context_char_budget: int = field(default_factory=lambda: _env_int("AGENT_CONTEXT_CHARS", 24_000))
    context_window: int = field(default_factory=lambda: _env_int("AGENT_CONTEXT_WINDOW", 0))
    chars_per_token: float = field(default_factory=lambda: _env_float("AGENT_CHARS_PER_TOKEN", 1.6))
    max_chunk_chars: int = field(default_factory=lambda: _env_int("AGENT_MAX_CHUNK_CHARS", 12_000))
    max_callee_notes: int = field(default_factory=lambda: _env_int("AGENT_MAX_CALLEE_NOTES", 12))
    max_verify_per_chunk: int = field(default_factory=lambda: _env_int("AGENT_MAX_VERIFY_PER_CHUNK", 8))
    request_timeout: int = field(default_factory=lambda: _env_int("AGENT_REQUEST_TIMEOUT", 300))
    max_retries: int = field(default_factory=lambda: _env_int("AGENT_MAX_RETRIES", 2))
    max_tokens: int = field(default_factory=lambda: _env_int("AGENT_MAX_TOKENS", 4096))
    reasoning_effort: str = field(default_factory=lambda: os.getenv(ENV_REASONING_EFFORT, "low"))
    enable_tools: bool = field(default_factory=lambda: os.getenv("AGENT_TOOLS", "1") != "0")
    max_tool_calls: int = field(default_factory=lambda: _env_int("AGENT_MAX_TOOL_CALLS", 4))
    lens_tools: bool = field(default_factory=lambda: os.getenv("AGENT_LENS_TOOLS", "1") != "0")
    max_lens_tool_calls: int = field(default_factory=lambda: _env_int("AGENT_MAX_LENS_TOOL_CALLS", 2))
    wave_width: int = field(default_factory=lambda: _env_int("AGENT_WAVE_WIDTH", 4))
    max_concurrency: int = field(default_factory=lambda: _env_int("AGENT_MAX_CONCURRENCY", 16))
    lenses: tuple[Lens, ...] = field(default_factory=lambda: _env_lenses("AGENT_LENSES"))
    triage: bool = field(default_factory=lambda: os.getenv("AGENT_TRIAGE", "1") != "0")
    entry_points: tuple[str, ...] = field(default_factory=lambda: _env_globs("AGENT_ENTRY_POINTS"))
    planning: str = field(default_factory=lambda: os.getenv("AGENT_PLANNING", "computed"))

    @property
    def advisory_planning(self) -> bool:
        return self.planning == "advisory"

    sandbox: str = field(default_factory=lambda: os.getenv(ENV_SANDBOX, "bwrap"))
    sandbox_timeout: int = field(default_factory=lambda: _env_int("AGENT_SANDBOX_TIMEOUT", 20))
    cache_results: bool = field(default_factory=lambda: os.getenv("AGENT_CACHE", "1") != "0")
    prompts_file: Path = field(default_factory=default_prompts_file)
    corpus_dir: Path = field(default_factory=default_corpus_dir)
    database_url: str = field(default_factory=default_database_url)

    def require_model(self) -> str:
        if not self.model:
            self.model = self.resolve_model()
        if not self.model:
            raise RuntimeError(
                f"No model configured. Set {ENV_MODEL} to a model served by your endpoint "
                f"({ENV_BASE_URL}, currently {self.base_url!r}). "
                "There is no default on purpose: a wrong model silently produces plausible nonsense."
            )
        return self.model

    def model_for(self, served: Sequence[str]) -> str:
        """The model a run would use, given what the endpoint serves.

        One definition, so `/agent/health` cannot claim a run is unconfigured
        when starting one would have picked a model perfectly well.
        """
        if self.model:
            return self.model
        return served[0] if len(served) == 1 else ""

    def resolve_model(self) -> str:
        from .endpoint import list_models

        served = list_models(self.base_url)
        picked = self.model_for(served)
        if picked:
            log.info("using %s, the only model %s serves", picked, self.base_url)
        elif len(served) > 1:
            log.warning("%s serves %s, set %s to one of them", self.base_url, ", ".join(served), ENV_MODEL)
        return picked

    OVERHEAD_TOKENS = 1_500

    def input_chars(self) -> int:
        if not self.context_window:
            return self.context_char_budget
        room = self.context_window - self.max_tokens - self.OVERHEAD_TOKENS
        return max(2_000, int(room * self.chars_per_token))

    def resolve_window(self) -> int:
        if self.context_window or not self.model:
            return self.context_window
        from .endpoint import context_window

        found = context_window(self.base_url, self.model)
        if found:
            self.context_window = found
        return self.context_window
