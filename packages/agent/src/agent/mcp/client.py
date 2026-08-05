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

from ..config import ENV_INDEX_DB, ENV_RUN_ROOT, ENV_SANDBOX

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
        run_root: Path,
        index_db: Path | None = None,
        sandbox: str | None = None,
        allowed: Sequence[str] | None = None,
    ) -> None:
        self.run_root = run_root
        self.index_db = index_db
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
        env[ENV_RUN_ROOT] = str(self.run_root)
        if self.index_db is not None:
            env[ENV_INDEX_DB] = str(self.index_db)
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
    run_root: Path,
    index_db: Path | None = None,
    sandbox: str | None = None,
    allowed: Sequence[str] | None = None,
) -> ToolSession | None:
    """None if the tool surface is unavailable: tools enhance verification, they
    are not a precondition for it."""
    session = ToolSession(run_root, index_db, sandbox, allowed)
    try:
        session.start()
    except Exception as err:  # noqa: BLE001 - any startup failure means "no tools"
        log.warning("MCP tools unavailable, verifying without them: %s", err)
        session.close()
        return None
    return session


# Not the whole surface: verification is about one claim, and an unbounded
# toolbox invites wandering.
VERIFY_TOOLS: Sequence[str] = (
    "read_source",
    "search_text",
    "find_definition",
    "find_callers",
    "find_callees",
    # The graph, for the questions the one-relation tools answer badly: how far
    # something reaches, whether two things are connected at all, and what else
    # belongs with the code under review. Settling those by grep was the gap.
    "graph_neighbours",
    "graph_path",
    "graph_subsystem",
    "run_in_sandbox",
)
