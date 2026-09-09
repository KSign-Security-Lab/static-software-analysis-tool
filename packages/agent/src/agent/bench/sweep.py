"""A SEC-bench sweep you can start and walk away from.

    agent bench sweep              # in tmux, and go home
    SECB_LIMIT=10 agent bench sweep

Runs in the foreground and logs as it goes, so tmux -- or screen, or nohup --
owns the detaching. There was a `--detach` flag doing that with setsid; it was
one more path to get wrong in the thing you are least able to watch, and tmux
already does it better.

Checks everything cheap before it spends anything expensive, because the failure
worth preventing is discovering at hour six that the model was down and ten
instances failed identically.

Resumable. `agent bench run` skips instances that already have a result, so
re-running this after a crash, a reboot or a Ctrl-C continues where it stopped
rather than starting over. That is what makes it safe to leave.

Every knob lives in `config.py` and is read from the environment; this sets none
of them and only reports what they are.
"""

from __future__ import annotations

import io
import os
import shutil
import subprocess
import sys
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import IO, Callable, Iterator

from ..endpoint import list_models
from .config import BenchConfig, repo_root

#: The tooling image builds on the *host* daemon, so `/` needs room too.
MIN_HOST_FREE_GB = 4

#: Evaluation images land under `root`, one at a time when pruning is on.
MIN_DATA_FREE_GB = 20

#: Generous: this decides whether hours of sweeping start at all.
PROBE_TIMEOUT = 10.0


def _red(message: str) -> None:
    print(f"\033[31m{message}\033[0m")


def _info(message: str) -> None:
    print(f"\033[36m{message}\033[0m")


def _step(message: str) -> None:
    print(f"\n\033[1m== {message}\033[0m")


@contextmanager
def _also_log(path: Path) -> Iterator[None]:
    """Everything this process and its children print, into `path` as well.

    At the file-descriptor level rather than by wrapping `print`, because most
    of the output is docker's. tmux scrollback is finite and this runs for days;
    the log is what you read afterwards to find the instance that went wrong.
    """
    sys.stdout.flush()
    sys.stderr.flush()
    read_fd, write_fd = os.pipe()
    saved_out, saved_err = os.dup(1), os.dup(2)
    os.dup2(write_fd, 1)
    os.dup2(write_fd, 2)
    os.close(write_fd)

    def pump() -> None:
        # Drains whatever happens. If the terminal has gone -- tmux killed,
        # the ssh session dropped -- or the log stops being writable partway
        # through, the pipe still has to be emptied: the alternative is the
        # sweep blocking on its next `print` for ever, hours in.
        with open(read_fd, "rb", buffering=0) as source:
            sink: IO[bytes] | None = path.open("ab")
            for chunk in iter(lambda: source.read(4096), b""):
                try:
                    os.write(saved_out, chunk)
                except OSError:
                    pass
                if sink is None:
                    continue
                try:
                    sink.write(chunk)
                    sink.flush()
                except OSError:
                    sink.close()
                    sink = None
            if sink is not None:
                sink.close()

    pumping = threading.Thread(target=pump, daemon=True)
    pumping.start()

    # Fd 1 is a pipe now, not a terminal, so python switches stdout to block
    # buffering on its own -- and the sweep's own lines would sit in an 8KB
    # buffer for minutes while docker's output, written by another process,
    # streamed past them. The log would read as though the phases happened out
    # of order.
    stream = sys.stdout if isinstance(sys.stdout, io.TextIOWrapper) else None
    was_line_buffered = stream.line_buffering if stream else False
    if stream:
        stream.reconfigure(line_buffering=True)
    try:
        yield
    finally:
        sys.stdout.flush()
        sys.stderr.flush()
        if stream:
            stream.reconfigure(line_buffering=was_line_buffered)
        # Restoring the descriptors drops the pipe's last writer, which is what
        # ends the pump; joining before that would wait for ever.
        os.dup2(saved_out, 1)
        os.dup2(saved_err, 2)
        pumping.join(timeout=2)
        os.close(saved_out)
        os.close(saved_err)


def _compose(*args: str, capture: bool = False) -> subprocess.CompletedProcess[str]:
    """`docker compose` for the secbench profile, from the checkout.

    The profile flag is not optional: Compose silently matches nothing without
    it, which reads as "already running" rather than as the mistake it is.
    """
    return subprocess.run(
        ["docker", "compose", "--profile", "secbench", *args],
        cwd=repo_root(),
        capture_output=capture,
        text=True,
        check=False,
    )


def _free_gb(path: Path | str) -> int:
    try:
        return int(shutil.disk_usage(path).free / 1024**3)
    except OSError:
        return 0


def _usable(root: Path) -> bool:
    """Whether `root` can actually be written to, by writing to it.

    Free space is not the same question as a working disk. `df` answers from the
    superblock and keeps answering after the filesystem has aborted its journal
    -- 207G free on a volume where every open() returns EIO. That state cost a
    sweep once; the only honest check is to use it.
    """
    probe = root / ".writable"
    try:
        probe.write_text("ok")
        return probe.read_text() == "ok"
    except OSError:
        return False
    finally:
        probe.unlink(missing_ok=True)


def _check_model() -> bool:
    """Report the model the sweep will use, and pin it for the whole run.

    Every instance is an inspection, so without a model this produces a long row
    of identical failures. The served id is pinned into the environment here so
    that a server restarted mid-sweep cannot change what the later instances ran
    against without saying so.
    """
    base = os.getenv("AGENT_BASE_URL") or "http://localhost:8000/v1"
    models = list_models(base, timeout=PROBE_TIMEOUT)
    if not models:
        _red(f"no model answering at {base}")
        _red("  start one:  docker compose --profile vllm up -d --wait vllm")
        return False
    os.environ["AGENT_BASE_URL"] = base
    os.environ.setdefault("AGENT_MODEL", models[0])
    _info(f"  model            {os.environ['AGENT_MODEL']} at {base}")
    return True


def _preflight(config: BenchConfig) -> bool:
    """All of the cheap checks, before any of the expensive steps.

    Each one has actually cost an afternoon somewhere, so they all run and all
    report -- stopping at the first would hide the other three.
    """
    ok = True

    if shutil.which("docker") is None:
        _red("missing: docker")
        ok = False

    ok = _check_model() and ok

    # The sweep's own daemon. Its images must not land on the system disk.
    running = _compose("ps", "--status", "running", capture=True)
    if "secbench-docker" not in running.stdout:
        _info("  starting the sweep's docker daemon")
        if _compose("up", "-d", "--wait", "secbench-docker").returncode != 0:
            _red("could not start it")
            ok = False

    if not _usable(config.root):
        _red(f"cannot write to {config.root} -- the filesystem is not usable")
        _red(f"  check:  cat /sys/fs/ext4/$(findmnt -no SOURCE --target {config.root} | xargs basename)/errors_count")
        _red("          sudo dmesg | grep -iE 'ext4|I/O error'")
        ok = False

    host_free, data_free = _free_gb("/"), _free_gb(config.root)
    _info(f"  free             / {host_free}G · {config.root} {data_free}G")
    if host_free < MIN_HOST_FREE_GB:
        _red(f"under {MIN_HOST_FREE_GB}G free on / -- the tooling image builds there")
        ok = False
    if data_free < MIN_DATA_FREE_GB:
        _red(f"under {MIN_DATA_FREE_GB}G free on {config.root} -- evaluation images go there")
        ok = False

    if not config.prune_after:
        _red("  SECB_PRUNE=0 -- images are kept. The full set is ~200G on a shared volume.")

    return ok


def sweep(config: BenchConfig, run_action: Callable[[str], int]) -> int:
    """Preflight, fetch, sweep, re-score. `run_action` runs one `bench` action.

    The actions come back through the caller rather than being reimplemented
    here, so `agent bench run` and the `run` phase of a sweep cannot drift.
    """
    config.root.mkdir(parents=True, exist_ok=True)
    with _also_log(config.root / "sweep.log"):
        _info(f"SEC-bench sweep -- {time.strftime('%Y-%m-%d %H:%M:%S')}")

        _step("checking")
        if not _preflight(config):
            print()
            _red("refusing to start")
            return 1
        run_action("status")

        _step("dataset")
        if run_action("fetch") != 0:
            _red("fetch failed")
            return 1

        _step("sweeping")
        _info("each instance is a ~3GB pull, an inspection, a patch and its scoring -- allow ~30-40 minutes each")
        _info("scored as it goes, so results appear on 벤치마크 while this runs")
        _info("safe to interrupt: a re-run skips what already finished")
        started = time.monotonic()
        ran = run_action("run")
        _info(f"sweep phase finished in {int((time.monotonic() - started) / 60)} minutes")

        # Their evaluator, not ours. The sweep scores each instance as it goes,
        # while that instance's image is still on disk -- afterwards it has been
        # pruned, and scoring would have to download all two hundred again. This
        # pass is the safety net: it re-runs their batch evaluator over the
        # cumulative preds.json and fills in anything whose scoring failed.
        _step("re-scoring")
        _info("building SEC-bench's tooling image (cached after the first run)")
        if _compose("build", "secbench").returncode != 0:
            _red(f"build failed -- the patches are still in {config.predictions_file}")
            return 1
        _compose("up", "-d", "secbench", capture=True)
        if run_action("score") != 0:
            _red("scoring failed -- the sweep's own results are intact")

        _step("done")
        run_action("status")
        _info(f"results     {config.results_dir}")
        _info(f"patches     {config.predictions_file}")
        _info("on screen   http://localhost:3000/bench?dataset=sec-bench")
        _info("")
        _info("the daemon is still up; stop it with:")
        _info("  docker compose --profile secbench down")
        return ran
