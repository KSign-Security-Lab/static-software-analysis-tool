from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from .config import AgentConfig
from .mcp.client import LENS_TOOLS, VERIFY_TOOLS
from .promptstore import lens_prompt
from .schema import CandidateRemediation, LENSES, ChunkAnalysis, PlanRevision, Scout, Triage, Verdict

STEP_NODE: dict[str, str] = {
    "replan": "replan",
    "triage": "triage",
    "scout": "scout",
    **{lens_prompt(lens): lens for lens in LENSES},
    "gather": "gather",
    "verify": "verify",
    "fix": "verify",
}

STEP_SCHEMA: dict[str, type[BaseModel] | None] = {
    "replan": PlanRevision,
    "triage": Triage,
    "scout": Scout,
    **{lens_prompt(lens): ChunkAnalysis for lens in LENSES},
    "gather": None,
    "verify": Verdict,
    "fix": CandidateRemediation,
}

STEP_TOOLS: dict[str, tuple[str, ...]] = {
    "gather": tuple(VERIFY_TOOLS),
    **{lens_prompt(lens): tuple(LENS_TOOLS) for lens in LENSES},
}

STEP_ORDER: tuple[str, ...] = ("triage", "scout", *(lens_prompt(lens) for lens in LENSES), "gather", "verify", "fix", "replan")


def _fields(schema: type[BaseModel] | None) -> list[str]:
    return list(schema.model_fields) if schema is not None else []


def describe_steps(config: AgentConfig | None = None) -> list[dict[str, Any]]:
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
                "prompt": step,
                "schema": schema.__name__ if schema is not None else None,
                "schema_fields": _fields(schema),
                "tools": [catalogue.get(name, {"name": name, "summary": "", "parameters": []}) for name in offered],
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
    try:
        from .mcp.server import describe_tools
    except Exception:  # noqa: BLE001 - a missing description is not an outage
        return {}
    return {tool["name"]: tool for tool in describe_tools()}


DETERMINISTIC: tuple[str, ...] = ("plan", "context", "skip", "locate", "reduce")
NODE_NOTES: dict[str, dict[str, Any]] = {
    "plan": {
        "does": "Takes the next wave off the queue: skips chunks already inspected, then cuts at the first call-depth boundary, because chunks at one depth cannot need each other's notes.",
        "reads": ["pending"],
        "writes": ["pending", "wave", "current"],
        "router": "has_work",
        "rule": "wave is empty -> __end__, otherwise -> context",
    },
    "context": {
        "does": "Assembles one context pack per chunk in the wave -- the unit's source, how the things it calls are declared and what analysing them found, the file's declarations, its callers -- once, for everyone who will read it.",
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
