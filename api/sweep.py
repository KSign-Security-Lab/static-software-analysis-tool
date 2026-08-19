"""Starting the sweep from the surface, and surviving everything that would stop it.

A sweep is two hundred instances at roughly half an hour each. Nobody watches
that, so the only honest way to offer it from a web page is to make the run
outlive the page: its own session, its own process group, its own log, and a
pidfile that a later request -- in another browser, on another day, after the
API has reloaded a dozen times -- can find it by.

What this does *not* do is run the sweep in the API. A subprocess is the whole
point: uvicorn's reloader kills its children on every code change, and a sweep
that died because somebody saved a file would be worse than no button at all.

The script is the one at `scripts/secbench-sweep.sh` -- the same one you would
run in tmux. It already checks its preconditions, logs as it goes and resumes
where it stopped, so there is nothing here worth reimplementing, and two
implementations of "run the sweep" would drift.
"""

from __future__ import annotations

import json
import logging
import os
import re
import signal
import subprocess
import time
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

#: The repository root, from this file.
ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "secbench-sweep.sh"

#: How much of the log the surface gets. Enough to see the current instance and
#: what went wrong before it, not enough to make polling expensive.
TAIL_BYTES = 16_000
TAIL_LINES = 40

#: The script colours its own output, and the codes are in the file because
#: `tee` writes what it is given. Harmless in a terminal, literal in a browser.
_ANSI = re.compile(r"\x1b\[[0-9;]*m")

#: `bench: [7/200] njs.cve-2022-32414`, which the runner writes per instance.
_POSITION = re.compile(r"bench: \[(\d+)/(\d+)\] (\S+)")

#: Lines that are the sweep's own machinery talking to itself. The MCP server
#: logs a request per tool call, which at three thousand tool calls an hour
#: would be the entire tail.
_NOISE = (
    "Processing request of type",
    "server.py:",
    "HTTP Request:",
    # The second line of the MCP server's two-line format, which arrives on its
    # own and is otherwise indistinguishable from content.
    "CallToolRequest",
    "ListToolsRequest",
    # A langchain response object printed whole. The warning line above it
    # already says what went wrong; this is its argument.
    "additional_kwargs=",
)

#: Long enough for a filename and a reason, short enough that one langchain
#: response dump cannot become the whole panel.
LINE_CHARS = 240


def _paths() -> tuple[Path, Path, Path]:
    """`(pidfile, log, boot)` under whatever `SECB_ROOT` says.

    Imported here rather than at module scope for the same reason the dataset
    reader does it: the sweep's package is not part of the request path, and an
    import at the top would make that untrue in the import graph even though
    nothing calls it.
    """
    from agent.bench.config import BenchConfig

    root = BenchConfig().root
    return root / "sweep.pid", root / "sweep.log", root / "sweep.boot.log"


def _read_pidfile(pidfile: Path) -> dict[str, Any] | None:
    try:
        return json.loads(pidfile.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _alive(pid: int) -> bool:
    """Whether `pid` is still the sweep, rather than whatever inherited its number.

    A pidfile can outlive its process by days, and pids are reused. Signal 0
    says something is there; the cmdline says it is ours.
    """
    try:
        os.kill(pid, 0)
    except (ProcessLookupError, PermissionError):
        return False
    try:
        cmdline = Path(f"/proc/{pid}/cmdline").read_bytes().decode("utf-8", "replace")
    except OSError:
        # No procfs. Signal 0 succeeding is the best this platform offers.
        return True
    return "secbench-sweep" in cmdline


def _tail(path: Path) -> list[str]:
    """The end of the log, minus the parts that are the agent talking to itself."""
    try:
        with path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            start = max(0, handle.tell() - TAIL_BYTES)
            handle.seek(start)
            text = handle.read().decode("utf-8", "replace")
    except OSError:
        return []

    # The first line is dropped only when the seek landed inside one. On a file
    # shorter than the window it is whole, and dropping it lost the only line a
    # freshly-started run had.
    raw = text.splitlines()[1:] if start > 0 else text.splitlines()
    lines = [_ANSI.sub("", line).rstrip() for line in raw]
    kept = [line for line in lines if line.strip() and not any(n in line for n in _NOISE)]
    return [line if len(line) <= LINE_CHARS else line[:LINE_CHARS] + " …" for line in kept][-TAIL_LINES:]


def _position(lines: list[str]) -> tuple[str | None, int | None, int | None]:
    """`(instance, position, total)` from the last progress line, if there is one."""
    for line in reversed(lines):
        found = _POSITION.search(line)
        if found:
            return found.group(3), int(found.group(1)), int(found.group(2))
    return None, None, None


def status() -> dict[str, Any]:
    """What the sweep is doing, readable by anyone who opens the page.

    Everything here comes off disk, so it is the same answer in every browser
    and after every restart. There is no in-process state to lose.
    """
    pidfile, logfile, bootfile = _paths()
    record = _read_pidfile(pidfile)
    running = bool(record) and _alive(int(record.get("pid", -1)))
    lines = _tail(logfile)
    if not running:
        # Anything the script said before it took over its own logging, which is
        # the only window where a failure would otherwise vanish.
        lines += [f"[시작 실패] {line}" for line in _tail(bootfile)]
    instance, position, total = _position(lines)

    if not running and record:
        # It stopped. Whether it finished or died is in the log, and saying
        # which is better than an empty panel: "끝났습니다" over a log ending in
        # a traceback would be the page lying about its own run.
        record = {**record, "ended": True}

    return {
        "running": running,
        "pid": record.get("pid") if record else None,
        "started_at": record.get("started_at") if record else None,
        "instance": instance if running else None,
        "position": position,
        "of": total,
        "log": lines,
        "log_path": str(logfile),
    }


def start() -> dict[str, Any]:
    """Launch the sweep detached, and record where it went.

    `start_new_session` is the load-bearing argument: it puts the script in its
    own session and process group, so it does not die with the API worker that
    spawned it, and so stopping it later can signal the whole group rather than
    a shell that has already handed off to python.
    """
    pidfile, logfile, bootfile = _paths()
    record = _read_pidfile(pidfile)
    if record and _alive(int(record.get("pid", -1))):
        raise RuntimeError("이미 돌고 있습니다")
    if not SCRIPT.is_file():
        raise RuntimeError(f"{SCRIPT} 가 없습니다")

    logfile.parent.mkdir(parents=True, exist_ok=True)
    # Appended, never truncated: a sweep is resumable and the log of the run
    # that crashed is how you find out why.
    handle = logfile.open("a", encoding="utf-8")
    handle.write(f"\n=== web 에서 시작 {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n")
    handle.flush()

    env = {**os.environ}
    # Spawned from a service, PATH can be short of the things the script checks
    # for first. Adding rather than replacing, so a configured PATH still wins.
    env["PATH"] = env.get("PATH", "") + ":/usr/local/bin:/usr/bin:/bin"

    # Discarded, not written to the log. The script's own `tee` writes the log
    # *and* passes everything through to whatever it inherited, so pointing this
    # at the same file wrote every line twice.
    #
    # stderr goes to its own small file instead: after the script redirects, its
    # stderr goes through tee too, so this only ever catches what was said
    # before logging started -- which is exactly the output that would otherwise
    # be lost.
    boot = bootfile.open("w", encoding="utf-8")
    try:
        process = subprocess.Popen(  # noqa: S603 - fixed argv, no shell
            ["/usr/bin/env", "bash", str(SCRIPT)],
            cwd=str(ROOT),
            stdout=subprocess.DEVNULL,
            stderr=boot,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
            env=env,
        )
    finally:
        boot.close()
        handle.close()

    written = {"pid": process.pid, "started_at": time.time()}
    pidfile.write_text(json.dumps(written), encoding="utf-8")
    log.info("bench: sweep started as pid %d, logging to %s", process.pid, logfile)
    return status()


def stop() -> dict[str, Any]:
    """Ask the sweep to stop, and let it finish the instance it is on.

    SIGTERM to the group rather than the pid, because the pid is bash and the
    work is in its children. Resumable, so this costs the instance in flight and
    nothing else -- which is what makes it safe to offer as a button.
    """
    pidfile, _, _ = _paths()
    record = _read_pidfile(pidfile)
    if not record or not _alive(int(record.get("pid", -1))):
        raise RuntimeError("돌고 있지 않습니다")

    pid = int(record["pid"])
    try:
        os.killpg(os.getpgid(pid), signal.SIGTERM)
    except (ProcessLookupError, PermissionError) as err:
        raise RuntimeError(f"중지하지 못했습니다: {err}") from err

    # It has a moment to put the current instance down before the surface is
    # told it stopped; the status is read fresh either way.
    for _ in range(20):
        if not _alive(pid):
            break
        time.sleep(0.1)
    log.info("bench: sweep %d asked to stop", pid)
    return status()
