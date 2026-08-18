"""Consume the MCP tool surface from inside the agent.

The agent is a client of its own server, so there is one tool surface and no
in-process copy to drift. The adapters are async and the graph is sync, hence a
private event loop on a background thread behind a blocking facade.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import threading
from concurrent.futures import Future
from pathlib import Path
from types import TracebackType
from typing import Any, Sequence

from ..config import ENV_DATABASE_URL, ENV_RUN_ID, ENV_SANDBOX

log = logging.getLogger(__name__)

# Startup imports langchain, mcp and the tools in a subprocess.
STARTUP_TIMEOUT = 60.0
CALL_TIMEOUT = 120.0


def unwrap_tool_result(result: Any) -> str:
    """Adapter tools return content blocks, not bare strings."""
    if isinstance(result, str):
        return result
    if isinstance(result, list):
        parts = [block.get("text", "") for block in result if isinstance(block, dict)]
        return "".join(parts) if parts else str(result)
    return str(result)


class ToolSession:
    """A running ``agent-mcp`` subprocess and its tools. One per run, so the
    subprocess import cost is paid once."""

    def __init__(
        self,
        run_id: str,
        database_url: str | None = None,
        sandbox: str | None = None,
        allowed: Sequence[str] | None = None,
    ) -> None:
        self.run_id = run_id
        self.database_url = database_url
        self.sandbox = sandbox
        # None means the whole surface.
        self.allowed = frozenset(allowed) if allowed is not None else None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._client: Any = None
        self._tools: list[Any] = []
        self._by_name: dict[str, Any] = {}

    # -- lifecycle ---------------------------------------------------------

    def __enter__(self) -> ToolSession:
        self.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def _env(self) -> dict[str, str]:
        env = dict(os.environ)
        env[ENV_RUN_ID] = self.run_id
        if self.database_url:
            env[ENV_DATABASE_URL] = self.database_url
        if self.sandbox is not None:
            env[ENV_SANDBOX] = self.sandbox
        # `python -m agent.mcp` needs to find the package as this process did.
        existing = env.get("PYTHONPATH", "")
        src = str(Path(__file__).resolve().parents[2])
        env["PYTHONPATH"] = f"{src}{os.pathsep}{existing}" if existing else src
        return env

    def start(self) -> None:
        """Launch the server and load its tools. Raises if it cannot."""
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, name="agent-mcp-loop", daemon=True)
        self._thread.start()
        self._submit(self._connect()).result(timeout=STARTUP_TIMEOUT)

    def _run_loop(self) -> None:
        assert self._loop is not None
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def _submit(self, coro: Any) -> Future[Any]:
        assert self._loop is not None
        return asyncio.run_coroutine_threadsafe(coro, self._loop)

    async def _connect(self) -> None:
        from langchain_mcp_adapters.client import MultiServerMCPClient

        self._client = MultiServerMCPClient(
            {
                "agent": {
                    "command": sys.executable,
                    "args": ["-m", "agent.mcp"],
                    "transport": "stdio",
                    "env": self._env(),
                }
            }
        )
        self._tools = list(await self._client.get_tools())
        self._by_name = {tool.name: tool for tool in self._tools}
        log.info("MCP tools loaded: %s", ", ".join(sorted(self._by_name)))

    def close(self) -> None:
        if self._loop is None:
            return
        self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread is not None:
            self._thread.join(timeout=10)
        self._loop = None
        self._thread = None
        self._tools = []
        self._by_name = {}

    # -- use ---------------------------------------------------------------

    @property
    def tools(self) -> list[Any]:
        """The offered tools, as LangChain tools ready for ``bind_tools``."""
        if self.allowed is None:
            return list(self._tools)
        return [tool for tool in self._tools if tool.name in self.allowed]

    def names(self) -> list[str]:
        return sorted(self._by_name)

    def call(self, name: str, arguments: dict[str, Any]) -> str:
        """Never raises: a tool failure is something the model reads and works
        around, and must not abort an inspection."""
        tool = self._by_name.get(name)
        if tool is None:
            return f"error: no such tool: {name}"
        try:
            raw = self._submit(tool.ainvoke(arguments)).result(timeout=CALL_TIMEOUT)
        except Exception as err:  # noqa: BLE001 - reported to the model, not raised at the run
            log.warning("tool %s failed: %s", name, err)
            return f"error: tool {name} failed: {err}"
        return unwrap_tool_result(raw)


def open_session(
    run_id: str,
    database_url: str | None = None,
    sandbox: str | None = None,
    allowed: Sequence[str] | None = None,
) -> ToolSession | None:
    """None if the tool surface is unavailable: tools enhance verification, they
    are not a precondition for it."""
    session = ToolSession(run_id, database_url, sandbox, allowed)
    try:
        session.start()
    except Exception as err:  # noqa: BLE001 - any startup failure means "no tools"
        log.warning("MCP tools unavailable, verifying without them: %s", err)
        session.close()
        return None
    return session


#: What a specialist may reach for while reading a unit.
#:
#: Deterministic lookups only, and that is the line. Each of these is an index
#: query: the same question gives the same answer every time, in milliseconds,
#: with no model behind it. Asking "what is this callee actually declared as" is
#: a lookup, not exploration, and it is usually the fact the finding turns on.
#:
#: Not `read_source`, `search_text` or `search_semantic`. Those
#: are open-ended -- where a specialist goes with them differs run to run, and
#: they are what `gather` is for, one claim at a time, after something has been
#: found worth checking.
LENS_TOOLS: Sequence[str] = (
    "find_definition",
    "find_callers",
    "find_callees",
    "graph_neighbours",
)

# Not the whole surface: verification is about one claim, and an unbounded
# toolbox invites wandering.
VERIFY_TOOLS: Sequence[str] = (
    "read_source",
    "search_text",
    # Asked in a sentence rather than in a pattern. The one question the rest
    # answer badly -- whether a check exists somewhere -- needs the identifier
    # guessed, and the identifier is the thing you do not have.
    "search_semantic",
    # The only tool that looks outside this run. Everything else can answer at
    # most what this tree says about itself; a claim that this is CWE-121 was
    # checked against nothing until this existed.
    "search_corpus",
    "find_definition",
    "find_callers",
    "find_callees",
    # The graph, for the questions the one-relation tools answer badly: how far
    # something reaches, whether two things are connected at all, and what else
    # belongs with the code under review. Settling those by grep was the gap.
    "graph_neighbours",
    "graph_path",
    "graph_subsystem",
)


#: Every tool any step may use. The MCP session is opened once per run, so it
#: has to allow the union rather than one step's slice.
ALL_TOOLS: Sequence[str] = tuple(dict.fromkeys((*VERIFY_TOOLS, *LENS_TOOLS)))
