"""stdio entry point for the MCP server (``agent-mcp``).

Run it directly to drive the tools with the MCP Inspector, or let the agent
launch it as a subprocess. Either way it needs ``AGENT_RUN_ROOT`` pointing at
the tree to serve.
"""

from __future__ import annotations

from .server import mcp


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
