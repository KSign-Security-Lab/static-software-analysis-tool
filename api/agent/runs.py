"""Creating, listing and deleting runs."""

from __future__ import annotations

from agent.runs import STATUS_FAILED, STATUS_INDEXING, iter_all_files

import logging
import tempfile
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

from agent.index import build_index
from agent.files import Tree
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

from agent.vcs import GitError, Origin, clone, label_for, read_tree

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
                tree = store_zip(run, archive)
        else:
            payload = {(f.filename or "unnamed"): await f.read() for f in files}
            tree = write_files(run, payload)
    except UploadRejected as err:
        run.set_status(STATUS_FAILED, error=str(err))
        raise HTTPException(status_code=400, detail=str(err)) from err

    if not tree.files:
        # Distinguished, because the two mean different things to the reader: an
        # empty upload is a mistake to repeat differently, and an upload that was
        # *all* oversized artifacts is a tree with no source in it.
        detail = (
            f"올릴 수 있는 파일이 없습니다. {len(tree.skipped)}개가 한 파일 제한을 넘었습니다."
            if tree.skipped
            else "upload contained no files"
        )
        raise HTTPException(status_code=400, detail=detail)

    return _indexed(run, tree, _origin_of(files, len(tree.files)))


def _origin_of(files: List[UploadFile], written: int) -> Origin:
    """What to call an upload in the run list.

    A zip is named by its archive, a tree by how much of it there is. Neither is
    a git remote, so `kind` says so and the patch surface knows not to offer a
    push it has nowhere to send.
    """
    first = (files[0].filename or "") if files else ""
    if len(files) == 1 and first.lower().endswith(".zip"):
        return Origin(kind="zip", label=first)
    return Origin(kind="upload", label=f"{written}개 파일")


def _indexed(run: Run, tree: Tree, origin: Origin) -> Dict[str, Any]:
    """Index a populated run and describe it back.

    Shared by both intake routes so a repository and a zip cannot end up
    differently indexed, or differently described, for no reason a reader could
    see -- including what each passed over.

    `skipped` is carried on `meta` as well as returned, because the reason a file
    is missing from a later patch archive has to survive the request that decided
    it. A reader downloading the tree a week later still gets to know.
    """
    run.set_status(STATUS_INDEXING)
    store = run.store()
    try:
        result = build_index(run.file_contents(), store)
    finally:
        store.close()
    intake = tree.as_dict()
    run.write_meta(
        status="indexed",
        index=result.as_dict(),
        uploaded=len(tree.files),
        origin=origin.as_dict(),
        intake=intake,
    )

    return {
        "run_id": run.run_id,
        "uploaded": len(tree.files),
        "index": result.as_dict(),
        "files": sorted(iter_all_files(run)),
        "origin": origin.as_dict(),
        "intake": intake,
    }


class CloneRequest(BaseModel):
    """A repository to fetch, and optionally which branch or tag of it."""

    url: str
    ref: str | None = None


@router.post("/runs/git")
def create_run_from_git(owner: OwnerDep, request: CloneRequest) -> Dict[str, Any]:
    """Clone a repository and index it.

    Synchronous like the upload route, and for the same reason: the page cannot
    show anything until the file list exists. A shallow clone of a normal
    repository is seconds.

    The remote is recorded on the run -- URL, ref and the exact commit -- because
    that is what makes a patch from this run pushable later. Without the commit
    a push would have to guess what the fix was computed against.
    """
    run = new_run(owner=owner)
    try:
        with tempfile.TemporaryDirectory(prefix="ssat-clone-") as tmp:
            # Scratch, like the zip: the checkout is read into rows and gone
            # before the request ends. The run never touches the filesystem.
            cloned = clone(request.url, request.ref, Path(tmp) / "repo")
            tree = read_tree(cloned.root)
            run.put_files(tree.files)
    except UploadRejected as err:
        run.set_status(STATUS_FAILED, error=str(err))
        raise HTTPException(status_code=400, detail=str(err)) from err
    except GitError as err:
        # The remote's answer, not ours. 502 rather than 500: we reached out and
        # something upstream said no.
        run.set_status(STATUS_FAILED, error=str(err))
        raise HTTPException(status_code=502, detail=str(err)) from err

    origin = Origin(
        kind="git",
        label=label_for(request.url, cloned.ref),
        url=request.url,
        ref=cloned.ref,
        commit=cloned.commit,
    )
    return _indexed(run, tree, origin)


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
