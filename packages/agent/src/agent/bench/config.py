from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from ..config import load_env_file, repo_root

ENV_ROOT = "SECB_ROOT"
ENV_SPLIT = "SECB_SPLIT"
ENV_INSTANCES = "SECB_INSTANCES"
ENV_LIMIT = "SECB_LIMIT"
ENV_DOCKER_HOST = "SECB_DOCKER_HOST"
ENV_IMAGE_PREFIX = "SECB_IMAGE_PREFIX"
ENV_IMAGE_TAG = "SECB_IMAGE_TAG"
ENV_PRUNE = "SECB_PRUNE"
ENV_RESUME = "SECB_RESUME"
ENV_CONTEXT = "SECB_CONTEXT"
ENV_CALLER_DEPTH = "SECB_CALLER_DEPTH"
ENV_AGENT_TIMEOUT = "SECB_AGENT_TIMEOUT"
ENV_EVAL_TIMEOUT = "SECB_EVAL_TIMEOUT"
ENV_WORKERS = "SECB_WORKERS"
SPLITS = ("cve", "oss")
CONTEXTS = ("sanitizer", "repo")
DEFAULT_IMAGE_PREFIX = "hwiwonlee/secb.eval.x86_64."
DEFAULT_IMAGE_TAG = "patch"
SOCKET_NAME = "run/docker.sock"


def load_env(path: Path | None = None) -> None:
    load_env_file(path)


def default_root() -> Path:
    override = os.getenv(ENV_ROOT)
    if override:
        path = Path(override).expanduser()
        return path if path.is_absolute() else repo_root() / path
    return repo_root() / "artifacts" / "secbench"


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_tuple(name: str) -> tuple[str, ...]:
    raw = os.getenv(name)
    if not raw:
        return ()
    return tuple(part.strip() for part in raw.split(",") if part.strip())


def _env_choice(name: str, allowed: tuple[str, ...], default: str) -> str:
    raw = (os.getenv(name) or "").strip()
    return raw if raw in allowed else default


@dataclass(frozen=True)
class BenchConfig:
    root: Path = field(default_factory=default_root)
    split: str = field(default_factory=lambda: _env_choice(ENV_SPLIT, SPLITS, "cve"))
    instances: tuple[str, ...] = field(default_factory=lambda: _env_tuple(ENV_INSTANCES))
    limit: int = field(default_factory=lambda: _env_int(ENV_LIMIT, 0))
    docker_host: str = ""
    image_prefix: str = field(default_factory=lambda: os.getenv(ENV_IMAGE_PREFIX, DEFAULT_IMAGE_PREFIX))
    image_tag: str = field(default_factory=lambda: os.getenv(ENV_IMAGE_TAG, DEFAULT_IMAGE_TAG))
    prune_after: bool = field(default_factory=lambda: os.getenv(ENV_PRUNE, "1") != "0")
    resume: bool = field(default_factory=lambda: os.getenv(ENV_RESUME, "1") != "0")
    context: str = field(default_factory=lambda: _env_choice(ENV_CONTEXT, CONTEXTS, "sanitizer"))
    caller_depth: int = field(default_factory=lambda: _env_int(ENV_CALLER_DEPTH, 1))
    agent_timeout: int = field(default_factory=lambda: _env_int(ENV_AGENT_TIMEOUT, 900))
    eval_timeout: int = field(default_factory=lambda: _env_int(ENV_EVAL_TIMEOUT, 1800))
    workers: int = field(default_factory=lambda: _env_int(ENV_WORKERS, 1))

    def __post_init__(self) -> None:
        if not self.docker_host:
            override = os.getenv(ENV_DOCKER_HOST)
            resolved = override or f"unix://{self.root / SOCKET_NAME}"
            object.__setattr__(self, "docker_host", resolved)

    @property
    def data_dir(self) -> Path:
        return self.root / "data"

    @property
    def dataset_file(self) -> Path:
        return self.data_dir / f"eval-{self.split}.jsonl"

    @property
    def runs_dir(self) -> Path:
        return self.root / "runs"

    @property
    def predictions_file(self) -> Path:
        return self.root / "preds.json"

    @property
    def results_dir(self) -> Path:
        return self.root / "results"

    def image_for(self, instance_id: str) -> str:
        return f"{self.image_prefix}{instance_id}:{self.image_tag}"

    def docker_env(self) -> dict[str, str]:
        return {**os.environ, "DOCKER_HOST": self.docker_host}

    def describe(self) -> dict[str, object]:
        return {
            "root": str(self.root),
            "split": self.split,
            "instances": list(self.instances) or "(all)",
            "limit": self.limit or "(none)",
            "docker_host": self.docker_host,
            "image_prefix": self.image_prefix,
            "image_tag": self.image_tag,
            "prune_after": self.prune_after,
            "resume": self.resume,
            "context": self.context,
            "caller_depth": self.caller_depth,
            "agent_timeout": self.agent_timeout,
            "eval_timeout": self.eval_timeout,
            "workers": self.workers,
        }
