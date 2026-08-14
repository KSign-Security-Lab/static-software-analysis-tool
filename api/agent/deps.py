"""Request dependencies shared by the agent routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request

from agent.runs import Run, get_run

#: The header the browser sends, holding a name somebody typed.
#:
#: Not authentication and not treated as any: nobody is challenged for it, and a
#: run is readable by id whatever it says. It exists because the run list is
#: shared and nobody recognises a stranger's run -- see `owner` on the run row.
OWNER_HEADER = "x-ssat-owner"


def require_run(run_id: str) -> Run:
    """Resolve a ``{run_id}`` path parameter to its run, or 404.

    Used as a FastAPI dependency rather than called in each handler: nineteen
    routes opened by looking the run up and raising the same error, and a route
    that forgot to would have read from a path that does not exist.
    """
    run = get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"unknown run: {run_id}")
    return run


#: A run resolved from the request path. Depend on this instead of taking ``run_id``.
RunDep = Annotated[Run, Depends(require_run)]


def owner_of(request: Request) -> str | None:
    """Whoever the browser says it is, or nothing.

    Nothing is a legitimate answer: the CLI has no browser, and a request
    without the header is served rather than refused. Trimmed and capped
    because it lands in a column and is echoed back into a list.
    """
    raw = (request.headers.get(OWNER_HEADER) or "").strip()
    return raw[:128] or None


#: The typed name on this request, if the browser sent one.
OwnerDep = Annotated[str | None, Depends(owner_of)]
