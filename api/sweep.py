from __future__ import annotations

import json
import logging
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parent.parent
SWEEP_ARGV = (sys.executable, "-m", "agent.cli", "bench", "sweep")
TAIL_BYTES = 16_000
TAIL_LINES = 40
_ANSI = re.compile(r"\x1b\[[0-9;]*m")

_POSITION = re.compile(r"bench: \[(\d+)/(\d+)\] (\S+)")
_NOISE = (
    "Processing request of type",
    "server.py:",
    "HTTP Request:",
    "CallToolRequest",
    "ListToolsRequest",
    "additional_kwargs=",
)

LINE_CHARS = 240


def _paths() -> tuple[Path, Path, Path]:
    from agent.bench.config import BenchConfig

    root = BenchConfig().root
    return root / "sweep.pid", root / "sweep.log", root / "sweep.boot.log"


def _read_pidfile(pidfile: Path) -> dict[str, Any] | None:
    try:
        return json.loads(pidfile.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except (ProcessLookupError, PermissionError):
        return False
    try:
        cmdline = Path(f"/proc/{pid}/cmdline").read_bytes().decode("utf-8", "replace")
    except OSError:
        return True
    return "agent.cli" in cmdline and "sweep" in cmdline


def _tail(path: Path) -> list[str]:
    try:
        with path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            start = max(0, handle.tell() - TAIL_BYTES)
            handle.seek(start)
            text = handle.read().decode("utf-8", "replace")
    except OSError:
        return []

    raw = text.splitlines()[1:] if start > 0 else text.splitlines()
    lines = [_ANSI.sub("", line).rstrip() for line in raw]
    kept = [line for line in lines if line.strip() and not any(n in line for n in _NOISE)]
    return [line if len(line) <= LINE_CHARS else line[:LINE_CHARS] + " …" for line in kept][-TAIL_LINES:]


def _position(lines: list[str]) -> tuple[str | None, int | None, int | None]:
    for line in reversed(lines):
        found = _POSITION.search(line)
        if found:
            return found.group(3), int(found.group(1)), int(found.group(2))
    return None, None, None


def status() -> dict[str, Any]:
    pidfile, logfile, bootfile = _paths()
    record = _read_pidfile(pidfile)
    running = bool(record) and _alive(int(record.get("pid", -1)))
    lines = _tail(logfile)
    if not running:
        lines += [f"[시작 실패] {line}" for line in _tail(bootfile)]
    instance, position, total = _position(lines)

    if not running and record:
        record = {**record, "ended": True}

    return {
        "running": running,
        "pid": record.get("pid") if record else None,
        "started_at": record.get("started_at") if record else None,
        "split": record.get("split") if record else None,
        "chose": record.get("instances") or [] if record else [],
        "instance": instance if running else None,
        "position": position,
        "of": total,
        "log": lines,
        "log_path": str(logfile),
    }


def start(instances: list[str] | None = None, split: str = "cve", resume: bool = True) -> dict[str, Any]:
    pidfile, logfile, bootfile = _paths()
    record = _read_pidfile(pidfile)
    if record and _alive(int(record.get("pid", -1))):
        raise RuntimeError("이미 돌고 있습니다")

    try:
        logfile.parent.mkdir(parents=True, exist_ok=True)
        handle = logfile.open("a", encoding="utf-8")
        handle.write(f"\n=== web 에서 시작 {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n")
        handle.flush()
    except OSError as err:
        raise RuntimeError(f"{logfile.parent} 에 쓸 수 없습니다 — 디스크를 확인하세요: {err}") from err

    env = {**os.environ}
    env["PATH"] = env.get("PATH", "") + ":/usr/local/bin:/usr/bin:/bin"

    env["SECB_SPLIT"] = split
    env["SECB_INSTANCES"] = ",".join(instances or ())
    env["SECB_RESUME"] = "1" if resume else "0"

    boot = bootfile.open("w", encoding="utf-8")
    try:
        process = subprocess.Popen(  # noqa: S603 - fixed argv, no shell
            list(SWEEP_ARGV),
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

    written = {
        "pid": process.pid,
        "started_at": time.time(),
        "split": split,
        "instances": list(instances or ()),
    }
    pidfile.write_text(json.dumps(written), encoding="utf-8")
    log.info("bench: sweep started as pid %d, logging to %s", process.pid, logfile)
    return status()


def stop() -> dict[str, Any]:
    pidfile, _, _ = _paths()
    record = _read_pidfile(pidfile)
    if not record or not _alive(int(record.get("pid", -1))):
        raise RuntimeError("돌고 있지 않습니다")

    pid = int(record["pid"])
    try:
        os.killpg(os.getpgid(pid), signal.SIGTERM)
    except (ProcessLookupError, PermissionError) as err:
        raise RuntimeError(f"중지하지 못했습니다: {err}") from err

    for _ in range(20):
        if not _alive(pid):
            break
        time.sleep(0.1)
    log.info("bench: sweep %d asked to stop", pid)
    return status()
