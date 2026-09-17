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
    runs_with_same_tree,
    write_files,
)

from agent.vcs import GitError, Origin, clone, label_for, read_tree

from .channels import _channels, _channels_lock, _live_channel
from .deps import OwnerDep, RunDep

log = logging.getLogger(__name__)
router = APIRouter()


@router.get("/runs")
def get_runs(owner: OwnerDep) -> Dict[str, Any]:
    return {"runs": list_runs(owner=owner)}


@router.delete("/runs/{run_id}")
def remove_run(run: RunDep) -> Dict[str, Any]:
    if _live_channel(run.run_id) is not None:
        raise HTTPException(status_code=409, detail="this run is in flight; stop it first")

    delete_run(run)
    with _channels_lock:
        _channels.pop(run.run_id, None)
    return {"deleted": run.run_id}


@router.post("/runs")
async def create_run(owner: OwnerDep, files: List[UploadFile] = File(...)) -> Dict[str, Any]:
    if not files:
        raise HTTPException(status_code=400, detail="no files uploaded")

    run = new_run(owner=owner)
    try:
        if len(files) == 1 and (files[0].filename or "").lower().endswith(".zip"):
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
        if tree.seen == 0:
            detail = "올린 파일이 없습니다."
        elif tree.skipped:
            detail = f"검사할 수 있는 소스가 없습니다. 파일 {tree.seen}개 가운데 {len(tree.skipped)}개는 너무 크거나 텍스트가 아니었습니다."
        else:
            detail = (
                f"검사할 수 있는 소스가 없습니다. 파일 {tree.seen}개를 봤지만 "
                "C·C++·Java·Python·JS/TS·Go·Rust·C# 가운데 하나가 아니었습니다."
            )
        raise HTTPException(status_code=400, detail=detail)

    return _indexed(run, tree, _origin_of(files, len(tree.files)), owner)


def _origin_of(files: List[UploadFile], written: int) -> Origin:
    first = (files[0].filename or "") if files else ""
    if len(files) == 1 and first.lower().endswith(".zip"):
        return Origin(kind="zip", label=first)
    return Origin(kind="upload", label=f"{written}개 파일")


def _indexed(run: Run, tree: Tree, origin: Origin, owner: str | None) -> Dict[str, Any]:
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
        "matches": runs_with_same_tree(run, owner),
    }


class CloneRequest(BaseModel):
    url: str
    ref: str | None = None


@router.post("/runs/git")
def create_run_from_git(owner: OwnerDep, request: CloneRequest) -> Dict[str, Any]:
    run = new_run(owner=owner)
    try:
        with tempfile.TemporaryDirectory(prefix="ssat-clone-") as tmp:
            cloned = clone(request.url, request.ref, Path(tmp) / "repo")
            tree = read_tree(cloned.root)
            run.put_files(tree.files)
    except UploadRejected as err:
        run.set_status(STATUS_FAILED, error=str(err))
        raise HTTPException(status_code=400, detail=str(err)) from err
    except GitError as err:
        run.set_status(STATUS_FAILED, error=str(err))
        raise HTTPException(status_code=502, detail=str(err)) from err

    origin = Origin(
        kind="git",
        label=label_for(request.url, cloned.ref),
        url=request.url,
        ref=cloned.ref,
        commit=cloned.commit,
    )
    return _indexed(run, tree, origin, owner)


def _reindex(run: Run) -> Dict[str, int]:
    store = run.store()
    try:
        store.clear_index()
        result = build_index(run.file_contents(), store)
    finally:
        store.close()
    stats = result.as_dict()
    run.write_meta(index=stats)
    return stats


@router.get("/runs/{run_id}")
def run_detail(run: RunDep) -> Dict[str, Any]:
    return describe_run(run)
