"""Reading and writing the files of one run's source tree."""

from __future__ import annotations

from agent.graph.state import initial_state

from pathlib import PurePosixPath
from typing import Any, Dict

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from agent.files import UploadRejected
from agent.runs import iter_all_files

from .deps import RunDep
from .runs import _reindex

router = APIRouter()


#: Extension -> Monaco language id. Monaco's own names differ from tree-sitter's.
_MONACO_LANGUAGES = {
    ".c": "c",
    ".h": "c",
    ".cc": "cpp",
    ".cpp": "cpp",
    ".cxx": "cpp",
    ".hpp": "cpp",
    ".hh": "cpp",
    ".java": "java",
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".go": "go",
    ".rs": "rust",
    ".cs": "csharp",
    ".json": "json",
    ".md": "markdown",
}


class WriteFileRequest(BaseModel):
    """Create or replace one file in a run."""

    path: str
    content: str


@router.put("/runs/{run_id}/file")
def write_run_file(run: RunDep, req: WriteFileRequest) -> Dict[str, Any]:
    """Write a file into the run and re-index.

    The name is validated by the same rule the upload uses: it comes from the
    browser, and `../` or a drive letter is refused rather than normalised into
    something that collides with a real path.
    """
    try:
        stored = run.put_file(req.path, req.content.encode("utf-8"))
    except UploadRejected as err:
        raise HTTPException(status_code=400, detail=str(err)) from err
    return {"path": stored, "index": _reindex(run), "files": sorted(iter_all_files(run))}


@router.delete("/runs/{run_id}/file")
def delete_run_file(run: RunDep, path: str) -> Dict[str, Any]:
    """Remove one file from the run and re-index."""
    if not run.delete_file(path):
        raise HTTPException(status_code=404, detail=f"no such file: {path}")

    # Findings for the deleted file would otherwise linger in the report.
    store = run.store()
    try:
        store.drop_findings_in_file(path)
    finally:
        store.close()
    return {"deleted": path, "index": _reindex(run), "files": sorted(iter_all_files(run))}


@router.get("/runs/{run_id}/input")
def run_input(run: RunDep) -> Dict[str, Any]:
    """The state a fresh run would begin from.

    The studio shows this as the run's input *before* there is a run, so it
    cannot come from a checkpoint. Computed from the index instead, which is
    where the starting queue comes from anyway -- and it is a pure function of
    it, so this costs a read rather than a session.
    """
    store = run.store()
    try:
        order = store.order()
    finally:
        store.close()

    stats = run.read_meta().get("index", {})
    return {"run_id": run.run_id, "values": dict(initial_state(order, len(order), stats))}


@router.get("/runs/{run_id}/files")
def run_files(run: RunDep) -> Dict[str, Any]:
    """Every file in the run.

    The run record deliberately carries at most ``LABEL_FILES`` names, because
    it is a label -- but that left no way at all to list a run's tree. Reopening
    a shared ``?run=`` link gave the editor an empty explorer, and the client
    had to reconstruct the list from whichever mutation it happened to perform
    last. Same helper the upload and write endpoints already return.
    """
    return {"run_id": run.run_id, "files": sorted(iter_all_files(run))}


@router.get("/runs/{run_id}/file")
def run_file(run: RunDep, path: str) -> Dict[str, Any]:
    """One file's text, for the editor.

    A path from a query string used to need confining against escape; it is a
    column value now, so an unknown one is simply a miss.
    """
    content = run.read_file(path)
    if content is None:
        raise HTTPException(status_code=404, detail=f"no such file: {path}")

    return {"path": path, "content": content, "language": _language_for(path)}


def _language_for(path: str) -> str:
    return _MONACO_LANGUAGES.get(PurePosixPath(path).suffix.lower(), "plaintext")
