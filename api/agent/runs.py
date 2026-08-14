"""Creating, listing and deleting runs."""

from __future__ import annotations

from agent.runs import STATUS_FAILED, STATUS_INDEXING, iter_all_files

import logging
import tempfile
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, File, HTTPException, UploadFile

from agent.index import build_index
from agent.runs import (
    Run,
    UploadRejected,
    delete_run,
    describe_run,
    store_zip,
    list_runs,
    new_run,
    write_files,
)

from .channels import _channels, _channels_lock, _live_channel
from .deps import OwnerDep, RunDep

log = logging.getLogger(__name__)
router = APIRouter()


@router.get("/runs")
def get_runs(owner: OwnerDep) -> Dict[str, Any]:
    """Every run, most recently touched first, labelled by its files.

    Filtered to whoever the browser says it is. Not a permission check --
    see `owner_of` -- it is what stops a shared list being mostly other
    people's runs, which is the state it was in.
    """
    return {"runs": list_runs(owner=owner)}


@router.delete("/runs/{run_id}")
def remove_run(run: RunDep) -> Dict[str, Any]:
    """Delete a run and everything in it.

    Trying things out leaves workspaces behind, and a list full of abandoned
    ones is worse than useless. A run in flight is refused rather than pulled
    out from under its worker.
    """
    if _live_channel(run.run_id) is not None:
        raise HTTPException(status_code=409, detail="this run is in flight; stop it first")

    delete_run(run)
    with _channels_lock:
        _channels.pop(run.run_id, None)
    return {"deleted": run.run_id}


@router.post("/runs")
async def create_run(owner: OwnerDep, files: List[UploadFile] = File(...)) -> Dict[str, Any]:
    """Upload source and index it.

    Accepts either a single ``.zip`` or a set of individual files. Indexing runs
    here rather than in the background because it is seconds, not minutes, and
    the editor needs the file list before it can render anything.
    """
    if not files:
        raise HTTPException(status_code=400, detail="no files uploaded")

    run = new_run(owner=owner)
    try:
        if len(files) == 1 and (files[0].filename or "").lower().endswith(".zip"):
            # A real file only because `zipfile` wants a seekable path. It
            # is scratch: read, stored as rows, and gone before the request
            # ends -- the run itself never touches the filesystem.
            with tempfile.TemporaryDirectory() as tmp:
                archive = Path(tmp) / "upload.zip"
                archive.write_bytes(await files[0].read())
                written = store_zip(run, archive)
        else:
            payload = {(f.filename or "unnamed"): await f.read() for f in files}
            written = write_files(run, payload)
    except UploadRejected as err:
        run.set_status(STATUS_FAILED, error=str(err))
        raise HTTPException(status_code=400, detail=str(err)) from err

    if written == 0:
        raise HTTPException(status_code=400, detail="upload contained no files")

    run.set_status(STATUS_INDEXING)
    store = run.store()
    try:
        result = build_index(run.file_contents(), store)
    finally:
        store.close()
    run.write_meta(status="indexed", index=result.as_dict(), uploaded=written)

    return {
        "run_id": run.run_id,
        "uploaded": written,
        "index": result.as_dict(),
        "files": sorted(iter_all_files(run)),
    }


@router.post("/runs/new")
def create_empty_run(owner: OwnerDep) -> Dict[str, Any]:
    """An empty run to paste into.

    The upload endpoint needs files; starting from a blank editor does not have
    any yet, and making the user save a file to disk first to try one snippet
    is a poor trade.
    """
    run = new_run(owner=owner)
    run.write_meta(status="indexed", index={}, uploaded=0)
    return {"run_id": run.run_id, "uploaded": 0, "index": {}, "files": []}


def _reindex(run: Run) -> Dict[str, int]:
    """Rebuild the index after the tree changed.

    Cheap to do on every edit and necessary for correctness: the chunk store is
    what the inspection walks. Chunk ids are content-derived, so re-inspecting
    afterwards only pays for the chunks that actually changed.
    """
    store = run.store()
    try:
        store.clear_index()
        # Writes the knowledge graph beside the index too -- it is derived from
        # exactly this and goes stale with exactly this.
        result = build_index(run.file_contents(), store)
    finally:
        store.close()
    stats = result.as_dict()
    run.write_meta(index=stats)
    return stats


@router.get("/runs/{run_id}")
def run_detail(run: RunDep) -> Dict[str, Any]:
    """One run, described the way the list describes them.

    The trace view shows a single run rather than a list, so this is where its
    heading comes from: which files, what status, when it last did anything.
    """
    return describe_run(run)
