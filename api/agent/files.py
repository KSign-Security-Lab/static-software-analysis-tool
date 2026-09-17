from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any, Dict

from fastapi import APIRouter, HTTPException

from agent.runs import iter_all_files

from .deps import RunDep

router = APIRouter()


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
    return {"run_id": run.run_id, "files": sorted(iter_all_files(run))}


@router.get("/runs/{run_id}/file")
def run_file(run: RunDep, path: str) -> Dict[str, Any]:
    content = run.read_file(path)
    if content is None:
        raise HTTPException(status_code=404, detail=f"no such file: {path}")

    return {"path": path, "content": content, "language": _language_for(path)}


def _language_for(path: str) -> str:
    return _MONACO_LANGUAGES.get(PurePosixPath(path).suffix.lower(), "plaintext")
