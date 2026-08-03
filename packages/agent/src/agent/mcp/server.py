"""The tool surface, served over MCP.

This module is protocol only. Every tool delegates straight to
:mod:`agent.tools`, so there is one implementation and the MCP layer adds
nothing that could drift from it.

The agent connects to this server as a client, which means the tools it uses are
exactly the tools any other MCP client gets -- Claude Code included. The cost is
one subprocess hop per run, which is noise next to model latency.

Configuration arrives by environment, because the server is launched as a
subprocess by whoever wants it:

``AGENT_RUN_ROOT``
    The uploaded tree. Every filesystem tool is confined to it.
``AGENT_INDEX_DB``
    The chunk store, for the graph tools. Optional; without it those tools
    report that the tree has not been indexed rather than failing.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Callable

from mcp.server.fastmcp import FastMCP

from ..config import ENV_INDEX_DB, ENV_RUN_ROOT, ENV_SANDBOX, AgentConfig
from ..index.store import ChunkStore
from ..tools import (
    ToolError,
    callees_of,
    callers_of,
    definition_of,
    glob_files,
    grep,
    list_dir,
    read_file,
    run_sandboxed,
)

mcp = FastMCP("agent-code-tools")


def run_root() -> Path:
    root = os.getenv(ENV_RUN_ROOT)
    if not root:
        raise ToolError(f"{ENV_RUN_ROOT} is not set; the server does not know which tree to serve")
    return Path(root)


def _store() -> ChunkStore | None:
    path = os.getenv(ENV_INDEX_DB)
    if not path or not Path(path).exists():
        return None
    return ChunkStore(Path(path))


def _dump(value: Any) -> str:
    """Tools return text over MCP; structured results go as JSON."""
    return json.dumps(value, indent=2)


def _guard(fn: Callable[[], str]) -> str:
    """Turn a ToolError into a message the model can act on.

    A raised exception becomes an MCP protocol error, which the model sees as a
    dead tool. A returned string it can read and correct.
    """
    try:
        return fn()
    except ToolError as err:
        return f"error: {err}"


@mcp.tool()
def read_source(path: str, start_line: int = 0, end_line: int = 0) -> str:
    """Read a source file from the tree under analysis.

    Paths are relative to the upload root. Pass start_line/end_line (1-based,
    inclusive) to read a range; leave them at 0 for the whole file.
    """
    return _guard(
        lambda: read_file(
            run_root(),
            path,
            start_line=start_line or None,
            end_line=end_line or None,
        )
    )


@mcp.tool()
def list_directory(path: str = ".") -> str:
    """List the immediate contents of a directory in the tree under analysis."""
    return _guard(lambda: "\n".join(list_dir(run_root(), path)))


@mcp.tool()
def find_files(pattern: str) -> str:
    """Find files by glob pattern, e.g. '**/*.c'."""
    return _guard(lambda: "\n".join(glob_files(run_root(), pattern)))


@mcp.tool()
def search_text(pattern: str, glob: str = "") -> str:
    """Search the tree for a regular expression. Returns 'file:line:text'."""
    return _guard(lambda: "\n".join(grep(run_root(), pattern, glob or None)))


@mcp.tool()
def find_callers(symbol: str) -> str:
    """Which functions call this symbol.

    Answered from the resolved link graph, not by searching, so the result is
    exact rather than every textual mention of the name.
    """

    def run() -> str:
        store = _store()
        if store is None:
            return "error: the tree has not been indexed"
        try:
            return _dump(callers_of(store, symbol))
        finally:
            store.close()

    return _guard(run)


@mcp.tool()
def find_callees(symbol: str) -> str:
    """Which functions this symbol calls, from the resolved link graph."""

    def run() -> str:
        store = _store()
        if store is None:
            return "error: the tree has not been indexed"
        try:
            return _dump(callees_of(store, symbol))
        finally:
            store.close()

    return _guard(run)


@mcp.tool()
def find_definition(symbol: str) -> str:
    """Where a symbol is defined, with its source text."""

    def run() -> str:
        store = _store()
        if store is None:
            return "error: the tree has not been indexed"
        try:
            return _dump(definition_of(store, symbol))
        finally:
            store.close()

    return _guard(run)


@mcp.tool()
def run_in_sandbox(command: list[str]) -> str:
    """Run a command against the tree in an isolated sandbox.

    Network is denied and the tree is mounted read-only. Use this to *test* a
    claim -- compile a snippet, run it under a checker -- rather than to argue
    about it. Returns exit code, stdout and stderr.
    """
    config = AgentConfig()

    def run() -> str:
        result = run_sandboxed(
            run_root(),
            command,
            backend=os.getenv(ENV_SANDBOX, config.sandbox),
            timeout=config.sandbox_timeout,
        )
        return _dump(result.as_dict())

    return _guard(run)
