"""The tool surface, served over MCP. Protocol only -- every tool delegates to
:mod:`agent.tools`, so there is one implementation.

Configured by environment, since the server is launched as a subprocess:
``AGENT_RUN_ROOT`` (the tree; every fs tool is confined to it) and
``AGENT_INDEX_DB`` (optional; the graph tools need it).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Callable

from graphify import Direction, describe_neighbours, describe_path, describe_subsystem
from mcp.server.fastmcp import FastMCP

from .. import knowledge
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
    """A raised exception looks like a dead tool; a message the model can read,
    it can correct."""
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
    """Which functions call this symbol. From the resolved link graph, so exact
    rather than every textual mention."""

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


def _map() -> Any:
    """The run's knowledge graph, or a message saying why there is not one.

    Built on the spot when no document has been written, so a run indexed before
    the graph existed still gets working tools rather than an error.
    """
    store = _store()
    if store is None:
        return "error: the tree has not been indexed"
    try:
        root = run_root()
        return knowledge.load_or_build(store, root, store.path.parent / knowledge.GRAPH_FILE)
    finally:
        store.close()


@mcp.tool()
def graph_neighbours(symbol: str, hops: int = 1, direction: str = "both") -> str:
    """What a symbol is connected to in the tree, within `hops` steps.

    Wider than find_callers/find_callees, which answer one relation each: this
    walks callers, callees, types and the documents that mention it together.
    `direction` is "out" (what it uses), "in" (what uses it) or "both".
    """

    def run() -> str:
        loaded = _map()
        if isinstance(loaded, str):
            return loaded
        graph, _ = loaded
        node = knowledge.find(graph, symbol)
        if node is None:
            return f"error: nothing in this tree is called {symbol!r}"
        return describe_neighbours(graph, node, hops=hops, direction=_direction(direction))

    return _guard(run)


@mcp.tool()
def graph_path(start: str, end: str) -> str:
    """How two symbols are related: the shortest chain between them, or nothing.

    The tool for "is this input really reaching that sink" -- it answers with the
    units in between rather than leaving it to be guessed from a grep.
    """

    def run() -> str:
        loaded = _map()
        if isinstance(loaded, str):
            return loaded
        graph, _ = loaded
        a, b = knowledge.find(graph, start), knowledge.find(graph, end)
        if a is None or b is None:
            return f"error: nothing in this tree is called {start if a is None else end!r}"
        return describe_path(graph, a, b)

    return _guard(run)


@mcp.tool()
def graph_subsystem(symbol: str) -> str:
    """What else belongs with this symbol.

    The tree clustered by what actually depends on what, rather than by
    directory. Use it to find the code that would have to change with this, or
    the sibling that already handles the case being argued about.
    """

    def run() -> str:
        loaded = _map()
        if isinstance(loaded, str):
            return loaded
        graph, communities = loaded
        node = knowledge.find(graph, symbol)
        if node is None:
            return f"error: nothing in this tree is called {symbol!r}"
        return describe_subsystem(graph, communities, node)

    return _guard(run)


def _direction(given: str) -> Direction:
    return given if given in ("out", "in", "both") else "both"  # type: ignore[return-value]


@mcp.tool()
def run_in_sandbox(command: list[str]) -> str:
    """Run a command against the tree, isolated: no network, tree read-only.
    Use it to *test* a claim rather than argue about it."""
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
