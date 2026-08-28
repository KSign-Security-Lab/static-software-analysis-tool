"""The tool surface, served over MCP. Protocol only -- every tool delegates to
:mod:`agent.tools`, so there is one implementation.

Configured by environment, since the server is launched as a subprocess:
``AGENT_RUN_ID`` (which run to serve) and ``AGENT_DATABASE_URL`` (where to find
it). Both the files and the index are rows on that run.
"""

from __future__ import annotations

import json
import os
from typing import Any, Callable

from graphify import Direction, describe_neighbours, describe_path, describe_subsystem
from mcp.server.fastmcp import FastMCP

from .. import knowledge
from ..config import ENV_RUN_ID
from ..index import embed
from ..index.store import ChunkStore
from ..rag import corpus
from ..tools import (
    ToolError,
    callees_of,
    callers_of,
    definition_of,
    glob_files,
    grep,
    list_dir,
    read_file,
)

mcp = FastMCP("agent-code-tools")


def _run_id() -> str:
    run_id = os.getenv(ENV_RUN_ID)
    if not run_id:
        raise ToolError(f"{ENV_RUN_ID} is not set; the server does not know which run to serve")
    return run_id


def run_files() -> dict[str, str]:
    """The run's tree, as `{path: text}`.

    Read per call rather than cached: the editor can write a file while a run is
    parked at a breakpoint, and a tool answering from a snapshot taken at
    startup would be describing code that is no longer there.
    """
    from ..runs import Run

    return Run(_run_id()).file_contents()


def _store() -> ChunkStore | None:
    try:
        return ChunkStore(_run_id())
    except ToolError:
        return None


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
            run_files(),
            path,
            start_line=start_line or None,
            end_line=end_line or None,
        )
    )


@mcp.tool()
def list_directory(path: str = ".") -> str:
    """List the immediate contents of a directory in the tree under analysis."""
    return _guard(lambda: "\n".join(list_dir(run_files(), path)))


@mcp.tool()
def find_files(pattern: str) -> str:
    """Find files by glob pattern, e.g. '**/*.c'."""
    return _guard(lambda: "\n".join(glob_files(run_files(), pattern)))


@mcp.tool()
def search_text(pattern: str, glob: str = "") -> str:
    """Search the tree for a regular expression. Returns 'file:line:text'."""
    return _guard(lambda: "\n".join(grep(run_files(), pattern, glob or None)))


@mcp.tool()
def plan_status() -> str:
    """What this run still intends to read, and what it has finished.

    Read-only, and that is the whole design rather than a limitation. Seeing
    what is left is useful -- it is the difference between judging a unit on its
    own and judging it knowing its callers are still coming. Being able to
    *reorder* it would put the model in charge of traversal, which is what makes
    two runs over one tree comparable, so there is no tool that does that.

    Returns a count per status and the next units in plan order.
    """

    def run() -> str:
        from ..graph.plan import PlanStore

        plan = PlanStore(_run_id())
        items = plan.items()
        if not items:
            return "no plan recorded for this run"

        counts = ", ".join(f"{status} {n}" for status, n in sorted(plan.summary().items()))
        upcoming = [item for item in items if item.status == "pending"][:20]
        lines = [counts]
        if upcoming:
            lines.append("")
            lines.append("next:")
            store = _store()
            for item in upcoming:
                chunk = store.chunk(item.chunk_id) if store is not None else None
                where = f"{chunk.file} :: {chunk.symbol}" if chunk is not None else item.chunk_id
                lines.append(f"  {where}")
        return "\n".join(lines)

    return _guard(run)


@mcp.tool()
def search_corpus(code: str, cwe: str = "", limit: int = 5) -> str:
    """Find recorded weaknesses that this *code* resembles. Pass code, not a description.

    The one question with nothing to look up by. Every other tool here takes a
    name and answers exactly; this takes a function body and answers with the
    weaknesses it is nearest to, out of a corpus that has nothing to do with the
    run and was recorded long before it.

    Measured on ten held-out functions: the right CWE came back first eight
    times. So it is a strong hint about *which class* of weakness this is, and
    no evidence at all that this code is exploitable -- resemblance is not
    reachability, and the corpus cannot see the path into this function.

    Each hit is labelled `vulnerable` or `fixed`. Read that as provenance, not
    as a judgement: the two are far too close in score to tell apart, so a
    `fixed` neighbour does **not** mean this code is patched.

    Returns 'score CWE variant file:symbol' with an excerpt, closest first.
    """

    def run() -> str:
        # Deliberately not `_store()`. Every other tool is scoped to the current
        # run because it describes one inspection; these describe weaknesses,
        # and are the same for every run there has ever been.
        try:
            hits = corpus.search(code, cwe=cwe, limit=limit)
        except corpus.Unavailable as err:
            return f"error: {err}"
        if not hits:
            return "no matches"
        out = []
        for score, sample in hits:
            excerpt = "\n".join(sample.body.splitlines()[:15])
            where = f"{sample.file}:{sample.symbol}"
            out.append(f"{score:.3f} {sample.cwe} {sample.variant} {where}\n{excerpt}")
        return "\n\n".join(out)

    return _guard(run)


@mcp.tool()
def search_semantic(query: str, limit: int = 5) -> str:
    """Find units that are *about* something, described in words rather than matched.

    For the question `search_text` answers badly: "is there a check on this
    anywhere?" needs the identifier guessed, and `is_authorized` contains none of
    the words you would guess. Ask in a sentence instead.

    Says what a unit resembles, never what reaches it -- use graph_path for that.
    Returns 'score file:line symbol', closest first.
    """

    def run() -> str:
        store = _store()
        if store is None:
            return "error: the tree has not been indexed"
        try:
            hits = embed.search(store, query, limit)
        except embed.Unavailable as err:
            return f"error: {err}"
        if not hits:
            return "no matches"
        return "\n".join(f"{score:.3f} {file}:{line} {symbol}" for score, file, symbol, line in hits)

    return _guard(run)


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
        return knowledge.load_or_build(store)
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


# `run_in_sandbox` was here.
#
# It ran a command against the run's tree, and a run has no tree: the files are
# rows and nothing materialises them. Removed rather than handed a scratch
# directory per call -- that would be a second source of truth with a lifetime,
# for the one tool that wanted it.
#
# `describe_tools` below reads the registry, so deleting the tool is what stops
# it being advertised. Nothing else needs editing.


def describe_tools() -> list[dict[str, Any]]:
    """Every tool this server offers, as facts a reader can be shown.

    Answered from the registry rather than by starting a server, so the API can
    say what a step is allowed to reach for before anything has run. That is the
    half of "what did the agent do" no trace can hold: a tool nobody called
    leaves no record, and "it had nine and used two" is a different account of a
    verification than "it used two".

    ``mcp.list_tools()`` is the async spelling of this same registry; the manager
    is its synchronous form, and answering this should not need an event loop.
    """
    return [
        {
            "name": tool.name,
            # First paragraph only: the rest of the docstring tells the model how
            # to use the tool, and a list wants one line.
            "summary": " ".join((tool.description or "").split("\n\n")[0].split()),
            "parameters": sorted((tool.parameters or {}).get("properties", {})),
        }
        for tool in sorted(mcp._tool_manager.list_tools(), key=lambda tool: tool.name)
    ]
