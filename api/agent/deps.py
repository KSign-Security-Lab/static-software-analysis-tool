from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request

from agent.runs import Run, get_run

OWNER_HEADER = "x-ssat-owner"


def require_run(run_id: str) -> Run:
    run = get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"unknown run: {run_id}")
    return run


RunDep = Annotated[Run, Depends(require_run)]


def owner_of(request: Request) -> str | None:
    raw = (request.headers.get(OWNER_HEADER) or "").strip()
    return raw[:128] or None


OwnerDep = Annotated[str | None, Depends(owner_of)]
