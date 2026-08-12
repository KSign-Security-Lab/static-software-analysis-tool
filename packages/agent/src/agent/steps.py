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
from .schema import LENSES, ChunkAnalysis, Scout, Triage, Verdict

#: Which graph node makes each kind of call.
#:
#: A step key is not a node name and this is the only thing that says so:
#: `lens:memory` runs in `memory`. It used to carry a second job as well --
#: `gather` and `verify` were both the `verify` node, so the node name could not
#: say what a call was for -- and that is now a node of its own, because the
#: step that reaches for tools is the step worth being able to stop at.
STEP_NODE: dict[str, str] = {
    "triage": "triage",
    "scout": "scout",
    **{lens_prompt(lens): lens for lens in LENSES},
    "gather": "gather",
    "verify": "verify",
}

#: What guided decoding constrains each step's reply to. ``gather`` is the odd
#: one out and the reason this is not derived from the prompt list: it is a
#: tool-calling loop that returns prose, so there is nothing to constrain.
STEP_SCHEMA: dict[str, type[BaseModel] | None] = {
    "triage": Triage,
    "scout": Scout,
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
STEP_ORDER: tuple[str, ...] = ("triage", "scout", *(lens_prompt(lens) for lens in LENSES), "gather", "verify")


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


#: The nodes that never call a model.
#:
#: Five of the twelve. They are ordinary Python: they take work off a queue, build
#: the text a specialist reads, resolve what one quoted back to a real span, and
#: write down what survived. Named here rather than inferred from the absence of a
#: step so that adding a node to the graph has to say which kind it is --
#: `test_every_node_is_classified` fails until it does, and a model-calling node
#: left out of `STEP_NODE` would otherwise be described as plain code.
DETERMINISTIC: tuple[str, ...] = ("plan", "context", "skip", "locate", "reduce")

#: What each deterministic node does, and which router decides where it goes next.
#:
#: `routes` is deliberately absent: it is read off the compiled graph in
#: :func:`describe_nodes`, so it cannot drift from the graph it describes. What is
#: declared here is what no amount of introspection can recover -- the channels a
#: node reads and writes, and the rule the router applies.
NODE_NOTES: dict[str, dict[str, Any]] = {
    "plan": {
        "does": "Takes the next wave off the queue: skips chunks already inspected, then cuts at the first call-depth boundary, because chunks at one depth cannot need each other's notes.",
        "reads": ["pending"],
        "writes": ["pending", "wave", "current"],
        "router": "has_work",
        "rule": "wave is empty -> __end__, otherwise -> context",
    },
    "context": {
        "does": "Assembles one context pack per chunk in the wave -- the unit's source, its callees' notes, the file's declarations, its callers -- once, for everyone who will read it.",
        "reads": ["wave"],
        "writes": ["packs"],
        "router": "dispatch",
        "rule": "AGENT_TRIAGE=1 -> one triage per chunk; off -> every configured lens per chunk directly",
    },
    "skip": {
        "does": "Nothing, and that is the point: every chunk passes through this layer so the join below the specialists fires exactly once per wave.",
        "reads": [],
        "writes": [],
        "router": None,
        "rule": "always -> locate",
    },
    "locate": {
        "does": "Merges what the specialists found, resolves each quoted anchor to a real line span, drops what cannot be found in the source, and treats two lenses reporting one expression as agreement rather than two findings.",
        "reads": ["candidates"],
        "writes": ["located"],
        "router": "claims",
        "rule": "one gather per finding under AGENT_MAX_VERIFY_PER_CHUNK; none left -> reduce",
    },
    "reduce": {
        "does": "Writes what survived to the run's store and closes the wave. Findings over the verify cap are kept but marked unverified rather than silently blessed.",
        "reads": ["located", "verdicts", "wave"],
        "writes": ["confirmed"],
        "router": None,
        "rule": "always -> plan",
    },
}


def describe_nodes() -> list[dict[str, Any]]:
    """Every node of the graph, and what kind of thing it is.

    Half the graph is deterministic and looked exactly like the half that is not.
    A node that calls no model has no prompt, no reply and no tools, so there is
    nothing of it in a trace -- and nothing said why.

    ``routes`` comes off the compiled graph rather than from the table above, so it
    is always the edges that actually exist. ``steps`` likewise: a node is an agent
    because a step names it, not because anything here says so.
    """
    from .graph.build import NODES, graph_shape

    shape = graph_shape()
    out_edges: dict[str, list[str]] = {}
    for edge in shape["edges"]:
        out_edges.setdefault(edge["source"], []).append(edge["target"])

    by_node: dict[str, list[dict[str, Any]]] = {}
    for step in describe_steps():
        by_node.setdefault(step["node"], []).append(step)

    described: list[dict[str, Any]] = []
    for name in NODES:
        steps = by_node.get(name, [])
        notes = NODE_NOTES.get(name, {})
        described.append(
            {
                "node": name,
                # An agent because a step names it. Nothing declares this twice.
                "agent": bool(steps),
                "steps": [step["step"] for step in steps],
                "calls": len(steps),
                "tools": max((len(step["tools"]) for step in steps), default=0),
                "does": notes.get("does"),
                "reads": notes.get("reads", []),
                "writes": notes.get("writes", []),
                "router": notes.get("router"),
                "rule": notes.get("rule"),
                "routes": sorted(out_edges.get(name, [])),
            }
        )
    return described
