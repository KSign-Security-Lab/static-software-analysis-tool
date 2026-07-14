"""FastAPI backend for the F2-A testing web.

Endpoints
---------
GET  /health           liveness + Joern container name
POST /cpg              {source, language, filename?} -> {cpg, method_count}
POST /f2a              {cpg}                          -> F2AResult
POST /analyze          {source, language, filename?} -> {cpg, method_count, f2a}

The frontend extracts the AST/CG/DFG/CFG views from the returned CPG (GraphSON)
in TypeScript; this service only produces the CPG and the F2-A evidence.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from ssat.cpg.generator import _find_project_root, _worker_generate_one
from ssat.f2a import run_f2a

app = FastAPI(title="F2-A Test API", version="1.0.0")

# The Next.js dev server may call this service from localhost or over the
# tailnet (100.x.x.x / fd7a:… IPv6), so allow any origin for this dev tool.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Map a UI language choice to a source filename Joern understands.
_LANG_EXT = {"c": "main.c", "cpp": "main.cpp", "java": "Main.java"}


def _joern_container() -> str:
    user = os.getenv("USER") or os.getenv("USERNAME") or "user"
    return f"ssat-joern-{user}"


class CpgRequest(BaseModel):
    source: str = Field(..., description="Source code to analyze")
    language: str = Field("c", description="c | cpp | java")
    filename: Optional[str] = None


class F2aRequest(BaseModel):
    cpg: Dict[str, Any] = Field(..., description="CPG GraphSON document")


def _filename_for(req: CpgRequest) -> str:
    if req.filename:
        return req.filename
    return _LANG_EXT.get(req.language.lower(), "main.c")


def _generate_cpg(req: CpgRequest) -> Dict[str, Any]:
    """Generate a CPG GraphSON dict from source via the Joern container.

    Uses the same synchronous worker as the ``ssat cpg`` CLI
    (``_worker_generate_one``). The older async path produced intermittently
    incomplete data-flow (REACHING_DEF) overlays; this path is reliable.
    """
    filename = _filename_for(req)
    source = req.source if req.source.endswith("\n") else req.source + "\n"
    workspace = _find_project_root(Path.cwd()) / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)

    tmp = Path(tempfile.mkdtemp(prefix="f2a-cpg-"))
    try:
        src_path = tmp / filename
        src_path.write_text(source, encoding="utf-8")
        out_root = tmp / "out"
        result = _worker_generate_one(
            str(src_path), str(tmp), str(out_root), _joern_container(),
            str(workspace), "all", "graphson", False,
        )
        if not result.get("success"):
            raise HTTPException(
                status_code=502,
                detail=f"CPG generation failed: {result.get('error', 'unknown error')}",
            )
        cpg = json.loads(Path(result["output"]).read_text(encoding="utf-8"))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return {"cpg": cpg, "method_count": _count_methods(cpg)}


def _count_methods(cpg: Dict[str, Any]) -> int:
    """Count METHOD vertices in the GraphSON (the generator's own counter
    looks for a key that the graphson export does not contain)."""
    value = cpg.get("@value") if isinstance(cpg, dict) else None
    vertices = value.get("vertices", []) if isinstance(value, dict) else []
    return sum(1 for v in vertices if isinstance(v, dict) and v.get("label") == "METHOD")


@app.get("/health")
def health() -> Dict[str, Any]:
    return {"status": "ok", "joern_container": _joern_container()}


@app.post("/cpg")
def cpg(req: CpgRequest) -> Dict[str, Any]:
    return _generate_cpg(req)


@app.post("/f2a")
def f2a(req: F2aRequest) -> Dict[str, Any]:
    try:
        result = run_f2a(req.cpg)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"F2-A analysis failed: {exc}") from exc
    data: Dict[str, Any] = result.model_dump()
    return data


@app.post("/analyze")
def analyze(req: CpgRequest) -> Dict[str, Any]:
    generated = _generate_cpg(req)
    cpg_doc = generated["cpg"]
    try:
        f2a_result = run_f2a(cpg_doc)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"F2-A analysis failed: {exc}") from exc
    return {
        "cpg": cpg_doc,
        "method_count": generated["method_count"],
        "f2a": f2a_result.model_dump(),
    }
