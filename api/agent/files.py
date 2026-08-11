"""Reading and writing the files of one run's source tree."""

from __future__ import annotations

from agent.graph.state import initial_state

from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from agent.paths import PathEscape, resolve_within
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
def write_run_file(paths: RunDep, req: WriteFileRequest) -> Dict[str, Any]:
    """Write a file into the run and re-index.

    Confined with the same resolver the tools use: the path comes from the
    browser, so `../` and absolute paths are rejected rather than reinterpreted.
    """
    try:
        resolved = resolve_within(paths.source, req.path)
    except PathEscape as err:
        raise HTTPException(status_code=400, detail=str(err)) from err

    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(req.content, encoding="utf-8")
    return {"path": req.path, "index": _reindex(paths), "files": sorted(iter_all_files(paths))}


@router.delete("/runs/{run_id}/file")
def delete_run_file(paths: RunDep, path: str) -> Dict[str, Any]:
    try:
        resolved = resolve_within(paths.source, path)
    except PathEscape as err:
        raise HTTPException(status_code=400, detail=str(err)) from err
    if not resolved.is_file():
        raise HTTPException(status_code=404, detail=f"no such file: {path}")

    resolved.unlink()
    # Findings for the deleted file would otherwise linger in the report.
    store = paths.store()
    try:
        store.drop_findings_in_file(path)
    finally:
        store.close()
    return {"deleted": path, "index": _reindex(paths), "files": sorted(iter_all_files(paths))}


@router.get("/runs/{run_id}/input")
def run_input(paths: RunDep) -> Dict[str, Any]:
    """The state a fresh run would begin from.

    The studio shows this as the run's input *before* there is a run, so it
    cannot come from a checkpoint. Computed from the index instead, which is
    where the starting queue comes from anyway -- and it is a pure function of
    it, so this costs a read rather than a session.
    """
    store = paths.store()
    try:
        order = store.order()
    finally:
        store.close()

    stats = paths.read_meta().get("index", {})
    return {"run_id": paths.run_id, "values": dict(initial_state(order, len(order), stats))}


@router.get("/runs/{run_id}/files")
def run_files(paths: RunDep) -> Dict[str, Any]:
    """Every file in the run.

    The run record deliberately carries at most ``LABEL_FILES`` names, because
    it is a label -- but that left no way at all to list a run's tree. Reopening
    a shared ``?run=`` link gave the editor an empty explorer, and the client
    had to reconstruct the list from whichever mutation it happened to perform
    last. Same helper the upload and write endpoints already return.
    """
    return {"run_id": paths.run_id, "files": sorted(iter_all_files(paths))}


@router.get("/runs/{run_id}/file")
def run_file(paths: RunDep, path: str) -> Dict[str, Any]:
    """One file's text, for the editor.

    Confined with the same resolver the tools use, because this endpoint takes
    a path straight from a query string.
    """
    try:
        resolved = resolve_within(paths.source, path)
    except PathEscape as err:
        raise HTTPException(status_code=400, detail=str(err)) from err
    if not resolved.is_file():
        raise HTTPException(status_code=404, detail=f"no such file: {path}")

    return {
        "path": path,
        "content": resolved.read_text(encoding="utf-8", errors="replace"),
        "language": _language_for(resolved),
    }


def _language_for(path: Path) -> str:
    return _MONACO_LANGUAGES.get(path.suffix.lower(), "plaintext")
