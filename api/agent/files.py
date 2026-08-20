"""Reading the files of one run's source tree.

Read-only. The tree a report was made from is never modified: that is what makes
a finding's anchor still mean something afterwards, and what makes a patch built
from it reproducible. Fixes leave as a patch or an archive -- see :mod:`.patch`.
"""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any, Dict

from fastapi import APIRouter, HTTPException

from agent.runs import iter_all_files

from .deps import RunDep

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


@router.get("/runs/{run_id}/files")
def run_files(run: RunDep) -> Dict[str, Any]:
    """Every file in the run.

    The run record deliberately carries at most ``LABEL_FILES`` names, because
    it is a label -- but that left no way at all to list a run's tree. Reopening
    a shared ``?run=`` link gave the editor an empty explorer, and the client
    had to reconstruct the list from whichever mutation it happened to perform
    last. Same helper the upload endpoint already returns.
    """
    return {"run_id": run.run_id, "files": sorted(iter_all_files(run))}


@router.get("/runs/{run_id}/file")
def run_file(run: RunDep, path: str) -> Dict[str, Any]:
    """One file's text, for the code a finding points at.

    A path from a query string used to need confining against escape; it is a
    column value now, so an unknown one is simply a miss.
    """
    content = run.read_file(path)
    if content is None:
        raise HTTPException(status_code=404, detail=f"no such file: {path}")

    return {"path": path, "content": content, "language": _language_for(path)}


def _language_for(path: str) -> str:
    return _MONACO_LANGUAGES.get(PurePosixPath(path).suffix.lower(), "plaintext")
