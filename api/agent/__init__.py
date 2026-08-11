"""HTTP surface for the LLM agent, split by what each group of routes is about.

Mounted on the existing FastAPI app rather than run as a second service, so
there is one dev server and one CORS policy. The dependency direction is the
same as for ``ssat``: ``api`` imports ``agent``, and ``agent`` imports neither
``ssat`` nor ``gnn``.

This was one 1220-line module. The routes are unchanged; they are grouped now,
and the run lookup nineteen of them repeated is a dependency in :mod:`.deps`.
"""

from __future__ import annotations

from fastapi import APIRouter

from . import files, inspection, meta, runs, trace

router = APIRouter(prefix="/agent", tags=["agent"])

# Order matters only where paths could shadow each other; these do not overlap.
for _group in (meta, runs, files, trace, inspection):
    router.include_router(_group.router)

__all__ = ["router"]
