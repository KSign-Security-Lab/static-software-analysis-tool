"""Every knob the SEC-bench sweep has, in one place.

The reason this file exists rather than a handful of constants next to the code
that reads them: a sweep is a thing you tune between runs -- which split, how
many instances, whether to keep the images, how long to wait -- and a parameter
you have to hunt for is a parameter nobody changes. Everything the sweep can be
told is here, and nothing else in `agent/bench/` holds a path or a number.

Defaults are **repo-relative**, so a fresh checkout runs unconfigured and the
committed files name no machine. `.env` is where a machine says where its space
is, and the same variables the compose profile mounts are the ones this reads --
one fact in one place rather than a path repeated in Python and in YAML.

The style is `agent/config.py`'s, deliberately: environment override on every
field, so the API, the CLI and a container all agree without anything threading
configuration through layers.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

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

#: The two splits the dataset ships. `cve` is the 200 real CVEs the published
#: numbers are about; `oss` is the wider OSS-Fuzz set.
SPLITS = ("cve", "oss")

#: What the agent is shown per instance.
#:
#: `sanitizer` indexes the files named in the crash's stack trace, which is what
#: a triaging engineer actually receives. `repo` indexes the whole project --
#: honest and far more expensive. There is deliberately no setting that shows
#: the files the reference patch touches: that would be telling the agent where
#: the bug is and then scoring it on finding the bug.
CONTEXTS = ("sanitizer", "repo")

#: Where the pre-built evaluation images live. Theirs, on Docker Hub.
DEFAULT_IMAGE_PREFIX = "hwiwonlee/secb.eval.x86_64."

#: The tag their evaluator uses, and therefore the one to pull.
#:
#: Each instance carries `latest`, `patch` and `poc`. `eval_instances.py` builds
#: `f"{PREFIX}.{id}:patch"` for a patch evaluation, so pulling the repository
#: untagged fetched `:latest` and left the evaluator to download a second image
#: per instance -- ~2.8GB each, over two hundred instances.
#:
#: The content is the same either way: measured on njs.cve-2022-32414, the two
#: tags share every layer and the crashing file is byte-identical in both. So
#: this was a bandwidth and ordering fault rather than a correctness one. Pulling
#: what the evaluator will use is still right: it makes "the tree we patched" and
#: "the tree that gets built" the same object rather than two that happen to
#: agree today.
DEFAULT_IMAGE_TAG = "patch"

#: The sweep's own daemon, as a socket under `root`.
#:
#: Not the host's: a sweep that fell back to the default socket would fill the
#: machine's system disk with two hundred gigabytes of somebody else's images,
#: which is the one failure this arrangement exists to prevent.
#:
#: A socket rather than a TCP port because an unauthenticated daemon on
#: 127.0.0.1 is reachable by every process on the machine with no credential;
#: a socket carries file permissions. Derived from `root` so the compose mount
#: and this cannot disagree.
SOCKET_NAME = "run/docker.sock"


def _repo_root() -> Path:
    """The checkout, found the way `default_prompts_file` finds it."""
    current = Path.cwd().resolve()
    for candidate in (current, *current.parents):
        if (candidate / "pyproject.toml").exists():
            return candidate
    return current


def default_root() -> Path:
    """Where the sweep keeps everything it downloads and writes.

    Repo-relative by default so a checkout works with no configuration, and
    under `artifacts/` because that is where this project already puts things
    that are large, regenerable and not source. A machine with a bigger disk
    points `SECB_ROOT` at it.
    """
    override = os.getenv(ENV_ROOT)
    if override:
        return Path(override).expanduser()
    return _repo_root() / "artifacts" / "secbench"


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
    """A setting that must be one of a few things.

    An unknown value falls back rather than raising: this is read wherever the
    sweep is imported, and a typo in an environment variable should not stop the
    CLI from starting -- it should run the default and be visible in `status`.
    """
    raw = (os.getenv(name) or "").strip()
    return raw if raw in allowed else default


@dataclass(frozen=True)
class BenchConfig:
    """One sweep's settings. Frozen: a run should not retune itself midway."""

    root: Path = field(default_factory=default_root)

    #: Which split to read. See :data:`SPLITS`.
    split: str = field(default_factory=lambda: _env_choice(ENV_SPLIT, SPLITS, "cve"))

    #: Specific instance ids, comma-separated. Empty means the whole split.
    instances: tuple[str, ...] = field(default_factory=lambda: _env_tuple(ENV_INSTANCES))

    #: Stop after this many. 0 means no cap. The first useful number comes from
    #: a subset, and two hundred instances is days of wall time.
    limit: int = field(default_factory=lambda: _env_int(ENV_LIMIT, 0))

    #: The sweep's daemon, never the host's.
    docker_host: str = ""  # resolved in __post_init__ from `root`, or overridden
    image_prefix: str = field(default_factory=lambda: os.getenv(ENV_IMAGE_PREFIX, DEFAULT_IMAGE_PREFIX))
    #: `patch` or `poc`. A setting rather than a rewrite, so the other track is
    #: reachable without touching the runner.
    image_tag: str = field(default_factory=lambda: os.getenv(ENV_IMAGE_TAG, DEFAULT_IMAGE_TAG))

    #: Remove an instance's image once it has been scored.
    #:
    #: On by default, and the reason is the volume rather than tidiness: the
    #: full set is around two hundred gigabytes on a disk shared with other
    #: accounts, so keeping every image would take most of the headroom
    #: everyone on it depends on. Off trades that space for not re-downloading.
    prune_after: bool = field(default_factory=lambda: os.getenv(ENV_PRUNE, "1") != "0")
    #: Carry forward an instance that already has a result rather than redoing
    #: it. On by default -- it is what makes a multi-day sweep safe to
    #: interrupt. Turned off to re-run a chosen few, which is the only case
    #: where spending the pull again is the point.
    resume: bool = field(default_factory=lambda: os.getenv(ENV_RESUME, "1") != "0")

    #: What the agent sees. See :data:`CONTEXTS`.
    context: str = field(default_factory=lambda: _env_choice(ENV_CONTEXT, CONTEXTS, "sanitizer"))
    #: How far out from the crashing frames to pull callers, in `sanitizer` mode.
    caller_depth: int = field(default_factory=lambda: _env_int(ENV_CALLER_DEPTH, 1))

    #: Seconds. An inspection that has not finished is a `not_located`, not a
    #: sweep that hangs.
    agent_timeout: int = field(default_factory=lambda: _env_int(ENV_AGENT_TIMEOUT, 900))
    #: Seconds. Their evaluator builds a C/C++ project and runs a sanitizer.
    eval_timeout: int = field(default_factory=lambda: _env_int(ENV_EVAL_TIMEOUT, 1800))

    #: Instances in flight. One by default: each holds a container that is
    #: compiling, and the model behind the inspection is the same one serving
    #: every other request on this machine.
    workers: int = field(default_factory=lambda: _env_int(ENV_WORKERS, 1))

    # -- derived paths -------------------------------------------------------
    #
    # Every path the sweep touches hangs off `root`, so deleting one directory
    # undoes a sweep and nothing is left behind anywhere else.

    def __post_init__(self) -> None:
        # `root` decides where the socket is, so the compose mount and the sweep
        # cannot drift. An explicit SECB_DOCKER_HOST still wins.
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
        """What the evaluator reads. SWE-agent's shape -- see `runner.py`."""
        return self.root / "preds.json"

    @property
    def results_dir(self) -> Path:
        return self.root / "results"

    def image_for(self, instance_id: str) -> str:
        """The exact reference their evaluator will use, tag and all."""
        return f"{self.image_prefix}{instance_id}:{self.image_tag}"

    def docker_env(self) -> dict[str, str]:
        """The environment a `docker` call needs to reach the sweep's daemon.

        Returned rather than exported, so nothing here can accidentally point
        the rest of the process at the wrong daemon.
        """
        return {**os.environ, "DOCKER_HOST": self.docker_host}

    def describe(self) -> dict[str, object]:
        """What `agent bench status` prints. Every knob, with where it came from."""
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
