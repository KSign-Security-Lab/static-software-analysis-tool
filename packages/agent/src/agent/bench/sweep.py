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
from ..config import repo_root
from .config import BenchConfig

MIN_HOST_FREE_GB = 4
MIN_DATA_FREE_GB = 20
PROBE_TIMEOUT = 10.0


def _red(message: str) -> None:
    print(f"\033[31m{message}\033[0m")


def _info(message: str) -> None:
    print(f"\033[36m{message}\033[0m")


def _step(message: str) -> None:
    print(f"\n\033[1m== {message}\033[0m")


@contextmanager
def _also_log(path: Path) -> Iterator[None]:
    sys.stdout.flush()
    sys.stderr.flush()
    read_fd, write_fd = os.pipe()
    saved_out, saved_err = os.dup(1), os.dup(2)
    os.dup2(write_fd, 1)
    os.dup2(write_fd, 2)
    os.close(write_fd)

    def pump() -> None:
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
        os.dup2(saved_out, 1)
        os.dup2(saved_err, 2)
        pumping.join(timeout=2)
        os.close(saved_out)
        os.close(saved_err)


def _compose(*args: str, capture: bool = False) -> subprocess.CompletedProcess[str]:
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
    probe = root / ".writable"
    try:
        probe.write_text("ok")
        return probe.read_text() == "ok"
    except OSError:
        return False
    finally:
        probe.unlink(missing_ok=True)


def _check_model() -> bool:
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
    ok = True

    if shutil.which("docker") is None:
        _red("missing: docker")
        ok = False

    ok = _check_model() and ok
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
