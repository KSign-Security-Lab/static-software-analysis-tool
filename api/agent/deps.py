"""Request dependencies shared by the agent routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException

from agent.runs import RunPaths, get_run


def require_run(run_id: str) -> RunPaths:
    """Resolve a ``{run_id}`` path parameter to its run, or 404.

    Used as a FastAPI dependency rather than called in each handler: nineteen
    routes opened by looking the run up and raising the same error, and a route
    that forgot to would have read from a path that does not exist.
    """
    paths = get_run(run_id)
    if paths is None:
        raise HTTPException(status_code=404, detail=f"unknown run: {run_id}")
    return paths


#: A run resolved from the request path. Depend on this instead of taking ``run_id``.
RunDep = Annotated[RunPaths, Depends(require_run)]
