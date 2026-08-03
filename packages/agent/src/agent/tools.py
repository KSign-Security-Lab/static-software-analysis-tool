"""The tool surface, as plain functions.

These are the implementations. :mod:`agent.mcp.server` wraps them for MCP and
adds nothing but the protocol; keeping the logic here means the tools can be
tested directly, without a subprocess and a JSON-RPC handshake in the way.

Every filesystem entry point takes the run root explicitly and pushes the path
through :func:`agent.paths.resolve_within`, so confinement cannot be forgotten
by a caller.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from .index.store import ChunkStore
from .paths import PathEscape, relative_to_root, resolve_within

#: Cap on what one read returns. A tool that dumps a megabyte into the context
#: window is worse than one that refuses.
MAX_READ_CHARS = 100_000
MAX_GREP_MATCHES = 200
MAX_LIST_ENTRIES = 1_000


@dataclass(frozen=True)
class ToolError(Exception):
    """A tool refused. Returned to the model as text, not raised at it."""

    message: str

    def __str__(self) -> str:
        return self.message


def read_file(root: Path, path: str, start_line: int | None = None, end_line: int | None = None) -> str:
    """Read a file under the run root, optionally a line range.

    Line numbers are 1-based and inclusive, matching every other coordinate in
    this system.
    """
    try:
        resolved = resolve_within(root, path)
    except PathEscape as err:
        raise ToolError(str(err)) from err
    if not resolved.is_file():
        raise ToolError(f"not a file: {path}")

    text = resolved.read_text(encoding="utf-8", errors="replace")
    if start_line is None and end_line is None:
        return text[:MAX_READ_CHARS]

    lines = text.splitlines()
    first = max(1, start_line or 1)
    last = min(len(lines), end_line or len(lines))
    return "\n".join(lines[first - 1 : last])[:MAX_READ_CHARS]


def list_dir(root: Path, path: str = ".") -> list[str]:
    """Immediate children of a directory, directories marked with a slash."""
    try:
        resolved = resolve_within(root, path)
    except PathEscape as err:
        raise ToolError(str(err)) from err
    if not resolved.is_dir():
        raise ToolError(f"not a directory: {path}")

    entries: list[str] = []
    for child in sorted(resolved.iterdir()):
        name = child.name + ("/" if child.is_dir() else "")
        entries.append(name)
    return entries[:MAX_LIST_ENTRIES]


def glob_files(root: Path, pattern: str) -> list[str]:
    """Run-relative paths matching a glob. Symlinks are never followed out."""
    matches: list[str] = []
    for path in sorted(root.glob(pattern)):
        if path.is_file() and not path.is_symlink():
            try:
                matches.append(relative_to_root(root, path))
            except ValueError:
                continue
    return matches[:MAX_LIST_ENTRIES]


def grep(root: Path, pattern: str, glob: str | None = None) -> list[str]:
    """Search the tree with ripgrep, falling back to a Python scan.

    ripgrep is used when present because it is dramatically faster on a large
    upload, but the fallback keeps the tool working on a host without it rather
    than silently returning nothing.
    """
    if shutil.which("rg"):
        command = ["rg", "--line-number", "--no-heading", "--color", "never", "-e", pattern]
        if glob:
            command += ["--glob", glob]
        try:
            completed = subprocess.run(command, cwd=root, capture_output=True, text=True, timeout=60, check=False)
        except (OSError, subprocess.SubprocessError) as err:
            raise ToolError(f"grep failed: {err}") from err
        # rg exits 1 for "no matches", which is not an error.
        if completed.returncode not in (0, 1):
            raise ToolError(f"grep failed: {completed.stderr.strip()}")
        return completed.stdout.splitlines()[:MAX_GREP_MATCHES]

    return _python_grep(root, pattern, glob)


def _python_grep(root: Path, pattern: str, glob: str | None) -> list[str]:
    import re

    try:
        compiled = re.compile(pattern)
    except re.error as err:
        raise ToolError(f"invalid pattern: {err}") from err

    results: list[str] = []
    for path in sorted(root.rglob(glob or "*")):
        if not path.is_file() or path.is_symlink():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for number, line in enumerate(text.splitlines(), start=1):
            if compiled.search(line):
                results.append(f"{relative_to_root(root, path)}:{number}:{line}")
                if len(results) >= MAX_GREP_MATCHES:
                    return results
    return results


# -- graph tools, answered from the index rather than by searching -----------


def _describe(chunk: Any) -> dict[str, Any]:
    return {
        "chunk_id": chunk.chunk_id,
        "file": chunk.file,
        "symbol": chunk.symbol,
        "kind": chunk.kind,
        "start_line": chunk.start_line,
        "end_line": chunk.end_line,
    }


def callers_of(store: ChunkStore, symbol: str) -> list[dict[str, Any]]:
    """Chunks that call a symbol. Exact, from the resolved link graph."""
    out: list[dict[str, Any]] = []
    for definition in store.definition_of(symbol):
        out.extend(_describe(chunk) for chunk in store.callers_of(definition.chunk_id))
    return out


def callees_of(store: ChunkStore, symbol: str) -> list[dict[str, Any]]:
    """Chunks a symbol calls."""
    out: list[dict[str, Any]] = []
    for definition in store.definition_of(symbol):
        out.extend(_describe(chunk) for chunk in store.callees_of(definition.chunk_id))
    return out


def definition_of(store: ChunkStore, symbol: str) -> list[dict[str, Any]]:
    """Where a symbol is defined, with its source."""
    return [{**_describe(chunk), "body": chunk.body[:MAX_READ_CHARS]} for chunk in store.definition_of(symbol)]


# -- sandboxed execution -----------------------------------------------------


@dataclass(frozen=True)
class SandboxResult:
    """Outcome of a sandboxed command."""

    exit_code: int
    stdout: str
    stderr: str
    backend: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "exit_code": self.exit_code,
            "stdout": self.stdout[:20_000],
            "stderr": self.stderr[:20_000],
            "backend": self.backend,
        }


def bwrap_available() -> bool:
    return shutil.which("bwrap") is not None


def _bwrap_command(root: Path, command: Sequence[str]) -> list[str]:
    """Wrap a command in bubblewrap with no network and a read-only system.

    The uploaded tree is bound read-only too. Verification needs to *run* code
    to test a claim, not to modify the thing it is testing, and a writable
    upload would let a compile step rewrite the source the findings point at.
    """
    return [
        "bwrap",
        "--unshare-all",  # no network, no IPC, no PID namespace sharing
        "--die-with-parent",
        "--ro-bind",
        "/usr",
        "/usr",
        "--ro-bind",
        "/lib",
        "/lib",
        "--ro-bind-try",
        "/lib64",
        "/lib64",
        "--ro-bind-try",
        "/bin",
        "/bin",
        "--ro-bind-try",
        "/sbin",
        "/sbin",
        "--ro-bind-try",
        "/etc/alternatives",
        "/etc/alternatives",
        "--proc",
        "/proc",
        "--dev",
        "/dev",
        "--tmpfs",
        "/tmp",
        "--ro-bind",
        str(root.resolve()),
        "/work",
        "--chdir",
        "/work",
        "--setenv",
        "HOME",
        "/tmp",
        "--",
        *command,
    ]


def run_sandboxed(
    root: Path,
    command: Sequence[str],
    *,
    backend: str = "bwrap",
    timeout: int = 20,
) -> SandboxResult:
    """Run a command against the uploaded tree, isolated.

    Used by the verify node to test a claim rather than argue about it -- "this
    buffer overflows" is checkable. Network is denied in every backend; a
    verification step that phones out is not verification.
    """
    if not command:
        raise ToolError("no command given")

    if backend == "bwrap":
        if not bwrap_available():
            raise ToolError("bubblewrap is not installed; set AGENT_SANDBOX=docker or none")
        argv = _bwrap_command(root, command)
    elif backend == "docker":
        argv = [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "--read-only",
            "--memory",
            "512m",
            "--pids-limit",
            "128",
            "-v",
            f"{root.resolve()}:/work:ro",
            "-w",
            "/work",
            "gcc:13",
            *command,
        ]
    elif backend == "none":
        raise ToolError("sandboxed execution is disabled (AGENT_SANDBOX=none)")
    else:
        raise ToolError(f"unknown sandbox backend: {backend}")

    try:
        completed = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired:
        return SandboxResult(exit_code=124, stdout="", stderr=f"timed out after {timeout}s", backend=backend)
    except OSError as err:
        raise ToolError(f"sandbox failed to start: {err}") from err

    return SandboxResult(
        exit_code=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
        backend=backend,
    )
