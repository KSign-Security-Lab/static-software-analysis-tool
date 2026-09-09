from __future__ import annotations

import logging
from typing import Any, Dict

from fastapi import APIRouter

from agent import promptstore as prompt_store
from agent.config import AgentConfig
from agent.endpoint import list_models
from agent.graph.build import NODES, graph_shape
from agent.steps import describe_nodes, describe_steps
from agent.tracing import status as tracing_status

log = logging.getLogger(__name__)
router = APIRouter()


def _redact(url: str) -> str:
    scheme, _, rest = url.partition("://")
    credentials, at, host = rest.rpartition("@")
    if not at:
        return url
    user = credentials.partition(":")[0]
    return f"{scheme}://{user}:***@{host}"


@router.get("/health")
def agent_health(probe: bool = False) -> Dict[str, Any]:
    config = AgentConfig()
    body: Dict[str, Any] = {
        "configured": bool(config.model),
        "base_url": config.base_url,
        "model": config.model or None,
        "sandbox": config.sandbox,
        "tools_enabled": config.enable_tools,
        "database": _redact(config.database_url),
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
    return {
        **graph_shape(),
        "steppable": list(NODES),
        "steps": describe_steps(),
        "node_notes": describe_nodes(),
    }


@router.get("/prompts")
def list_prompts() -> Dict[str, Any]:
    return {"prompts": prompt_store.describe(AgentConfig().prompts_file)}
