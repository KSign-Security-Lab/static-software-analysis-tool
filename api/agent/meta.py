"""Routes that describe the service rather than any one run: health, the graph
shape, and the editable prompt store.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from agent import promptstore as prompt_store
from agent.config import AgentConfig
from agent.endpoint import list_models
from agent.graph.build import NODES, graph_shape
from agent.steps import describe_nodes, describe_steps
from agent.tracing import status as tracing_status

log = logging.getLogger(__name__)
router = APIRouter()


@router.get("/health")
def agent_health(probe: bool = False) -> Dict[str, Any]:
    """Whether the agent is configured well enough to run.

    Configuration is answered from the environment, with no network call, so
    this stays usable as a liveness probe. Pass ``?probe=true`` to also ask the
    endpoint what it serves -- worth it when diagnosing an AGENT_MODEL that does
    not match any served id, which is the usual first failure.
    """
    config = AgentConfig()
    body: Dict[str, Any] = {
        "configured": bool(config.model),
        "base_url": config.base_url,
        "model": config.model or None,
        "sandbox": config.sandbox,
        "tools_enabled": config.enable_tools,
        "runs_dir": str(config.runs_dir),
        "tracing": tracing_status(),
    }
    if probe:
        served = list_models(config.base_url)
        body["reachable"] = bool(served)
        body["served_models"] = served
        body["model_is_served"] = config.model in served if (config.model and served) else False
    return body


@router.get("/graph")
def agent_graph() -> Dict[str, Any]:
    """The agent itself: its nodes, its edges, and what each step is.

    A property of the code, not of a run, so it answers before anything has
    been inspected -- the structure is the thing you want to look at first.

    ``steps`` is here rather than at a route of its own because it is the same
    question one level down. The graph says a chunk goes through `gather`; the
    steps say what that call may reach for -- ten tools, against `verify`'s
    none -- and which prompt each was given. A trace can
    never supply the second half: a tool that was offered and not called leaves
    no span behind.
    """
    # ``steppable`` is the subset a breakpoint can name: the real nodes, without
    # LangGraph's own start and end markers.
    return {
        **graph_shape(),
        "steppable": list(NODES),
        "steps": describe_steps(),
        # And what each *node* is. Five of them call no model at all, so there is
        # nothing of them in any trace -- which left half the drawing looking like
        # it did nothing. `routes` is read off the compiled graph, so it cannot
        # disagree with the edges above it.
        "node_notes": describe_nodes(),
    }


@router.get("/prompts")
def list_prompts() -> Dict[str, Any]:
    """The system prompts, their shipped defaults, and any tuning applied."""
    return {"prompts": prompt_store.describe(AgentConfig().prompts_file)}


class PromptRequest(BaseModel):
    text: str


@router.put("/prompts/{name}")
def put_prompt(name: str, request: PromptRequest) -> Dict[str, Any]:
    """Adopt a tuned prompt. Every later run uses it until it is cleared."""
    path = AgentConfig().prompts_file
    try:
        prompt_store.save(path, name, request.text)
    except prompt_store.UnknownPrompt as err:
        raise HTTPException(status_code=404, detail=str(err)) from err
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err
    return {"prompts": prompt_store.describe(path)}


@router.delete("/prompts/{name}")
def delete_prompt(name: str) -> Dict[str, Any]:
    """Go back to the prompt the code ships with."""
    path = AgentConfig().prompts_file
    try:
        prompt_store.clear(path, name)
    except prompt_store.UnknownPrompt as err:
        raise HTTPException(status_code=404, detail=str(err)) from err
    return {"prompts": prompt_store.describe(path)}
