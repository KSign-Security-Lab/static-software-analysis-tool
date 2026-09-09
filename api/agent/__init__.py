from __future__ import annotations

from fastapi import APIRouter

from . import files, inspection, meta, patch, runs, trace

router = APIRouter(prefix="/agent", tags=["agent"])

for _group in (meta, runs, files, trace, inspection, patch):
    router.include_router(_group.router)

__all__ = ["router"]
