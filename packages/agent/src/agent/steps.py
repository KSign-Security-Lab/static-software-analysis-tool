"""What each step of an inspection is: its prompt, its answer shape, its tools.

A property of the code rather than of a run, like the graph's shape, so this
answers before anything has been inspected -- and it answers the two questions a
trace cannot. A trace shows the calls that happened; it cannot show what the call
was *constrained* to answer, and it cannot show a tool that was offered and never
used. Both are the difference between reading a run and trusting it.

Assembled here rather than in the API route so the facts sit beside the things
they describe: a lens added to ``LENSES`` turns up without the route being
touched, and a prompt renamed without its step renamed fails a test here.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from .config import AgentConfig
from .mcp.client import VERIFY_TOOLS
from .promptstore import lens_prompt
from .schema import LENSES, ChunkAnalysis, Triage, Verdict

#: Which graph node makes each kind of call. Several steps run inside one node --
#: `gather` and `verify` are both the `verify` node -- which is exactly why the
#: node name alone was never enough to say what a call was for.
STEP_NODE: dict[str, str] = {
    "triage": "triage",
    **{lens_prompt(lens): lens for lens in LENSES},
    "gather": "verify",
    "verify": "verify",
}

#: What guided decoding constrains each step's reply to. ``gather`` is the odd
#: one out and the reason this is not derived from the prompt list: it is a
#: tool-calling loop that returns prose, so there is nothing to constrain.
STEP_SCHEMA: dict[str, type[BaseModel] | None] = {
    "triage": Triage,
    # Every specialist answers in the same shape -- the lens is in the prompt,
    # not in the shape of the answer.
    **{lens_prompt(lens): ChunkAnalysis for lens in LENSES},
    "gather": None,
    "verify": Verdict,
}

#: Which steps may call tools, and which ones. Only ``gather`` does, and not the
#: whole surface: verification is about one claim, and an unbounded toolbox
#: invites wandering.
STEP_TOOLS: dict[str, tuple[str, ...]] = {"gather": tuple(VERIFY_TOOLS)}

#: In the order a chunk passes through them, which is the order to read them in.
STEP_ORDER: tuple[str, ...] = ("triage", *(lens_prompt(lens) for lens in LENSES), "gather", "verify")


def _fields(schema: type[BaseModel] | None) -> list[str]:
    """The keys the reply must have. Shown instead of the whole JSON Schema,
    which is accurate, long, and read by nobody."""
    return list(schema.model_fields) if schema is not None else []


def describe_steps(config: AgentConfig | None = None) -> list[dict[str, Any]]:
    """Every step, with what it is given, what it must answer, and what it holds.

    ``enabled`` is this configuration's answer, not the code's: ``AGENT_LENSES``
    narrows the specialists and ``AGENT_TRIAGE=0`` drops the screening pass, and
    a step that will not run should not be presented as though it will.
    """
    settings = config if config is not None else AgentConfig()
    catalogue = _tool_catalogue()

    described: list[dict[str, Any]] = []
    for step in STEP_ORDER:
        schema = STEP_SCHEMA[step]
        offered = STEP_TOOLS.get(step, ())
        described.append(
            {
                "step": step,
                "node": STEP_NODE[step],
                # The prompt key is the step key by construction, and saying so
                # is what lets a call in the trace be traced back to the prompt
                # that produced it and edited from there.
                "prompt": step,
                "schema": schema.__name__ if schema is not None else None,
                "schema_fields": _fields(schema),
                "tools": [catalogue.get(name, {"name": name, "summary": "", "parameters": []}) for name in offered],
                # A step with tools is still toolless on an endpoint that cannot
                # call them, and that is a configuration fact, not a code one.
                "tools_enabled": bool(offered) and settings.enable_tools,
                "max_tool_calls": settings.max_tool_calls if offered else 0,
                "enabled": _enabled(step, settings),
            }
        )
    return described


def _enabled(step: str, config: AgentConfig) -> bool:
    if step == "triage":
        return config.triage
    if step.startswith("lens:"):
        return step in {lens_prompt(lens) for lens in config.lenses}
    return True


def _tool_catalogue() -> dict[str, dict[str, Any]]:
    """The served tools by name, or nothing if the surface cannot be read.

    Importing the MCP server pulls in FastMCP and the graph library. Worth it to
    describe the tools honestly rather than restating their names here, where the
    copy would drift -- but not worth failing the request over, so an import that
    goes wrong leaves the steps with their tool names and no descriptions.
    """
    try:
        from .mcp.server import describe_tools
    except Exception:  # noqa: BLE001 - a missing description is not an outage
        return {}
    return {tool["name"]: tool for tool in describe_tools()}
