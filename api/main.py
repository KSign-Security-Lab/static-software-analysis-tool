"""FastAPI backend for the SSAT web UI.

Endpoints
---------
GET  /health                 liveness + whether Joern can run here
POST /cpg-jpype              {source, language, filename?} -> {cpg, method_count}
POST /template               {source|cpg, ...}             -> template nodes
POST /ast                    {source|cpg, ...}             -> per-function ASTs
POST /dfg                    {source|cpg, ...}             -> per-function def-use DFGs
POST /analyze-functions      {source|cpg, ...}             -> AST + DFG per function
POST /f2a                    {cpg}                         -> F2AResult
POST /analyze                {source, language, filename?} -> {cpg, method_count, f2a}

The ``/agent/*`` routes are a separate line of analysis -- an LLM inspecting
uploaded source chunk by chunk -- and live in :mod:`api.agent`. They
share this app but nothing else: ``agent`` does not import ``ssat``.

Joern runs in this process, behind :mod:`ssat.cpg.backends`. There was a second
engine that shelled into a Joern container; it is gone, along with the container
and the `/cpg-docker` endpoint that reached it.

Note the frontend also derives AST/CFG/DFG/CG *views* from the returned CPG in
TypeScript, by edge label. Those are a different thing from the ``/ast`` and
``/dfg`` endpoints here, which return the SSAT pipeline's own artifacts.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Callable, Dict, List, Optional, cast

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from ssat.cpg.backends import EmbeddedBackend
from ssat.f2a import run_f2a
from ssat.pipeline import FunctionGraphs, analyze_template, generate_template, training_record
from ssat.types.cpg import CPGRoot

from agent.runs import abandon_live_runs

from .agent.channels import drain
from .agent import router as agent_router
from .bench import router as bench_router

log = logging.getLogger(__name__)


#: How long shutdown waits for in-flight workers to stop before leaving them.
SHUTDOWN_GRACE_SECONDS = 10.0


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Close the books on runs this process cannot possibly own, both ways.

    An inspection lives on a worker thread here and streams over an in-process
    channel, so anything still recorded as running when we start belongs to a
    process that is gone. Saying so once at startup is the difference between a
    dead run reading as failed and it reading as "실행 중" for ever.

    On the way out, stopping beats being killed. The threads are daemons, so
    shutdown would otherwise end them mid-frame: the session never closes, its
    MCP subprocess is orphaned, and the run is left for the *next* boot to mark
    failed -- where cancelling ends it as `cancelled` with what it found.
    """
    abandoned = abandon_live_runs()
    if abandoned:
        log.info("marked %d abandoned run(s) as failed: %s", len(abandoned), ", ".join(abandoned))
    yield
    stopped = await asyncio.to_thread(drain, SHUTDOWN_GRACE_SECONDS)
    if stopped:
        log.info("stopped %d in-flight run(s) on shutdown: %s", len(stopped), ", ".join(stopped))


app = FastAPI(title="SSAT API", version="2.0.0", lifespan=lifespan)

# The Next.js dev server may call this service from localhost or over the
# tailnet (100.x.x.x / fd7a:… IPv6), so allow any origin for this dev tool.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(agent_router)
app.include_router(bench_router)

# Map a UI language choice to a source filename Joern understands.
_LANG_EXT = {"c": "main.c", "cpp": "main.cpp", "java": "Main.java"}


class SourceRequest(BaseModel):
    source: str = Field(..., description="Source code to analyze")
    language: str = Field("c", description="c | cpp | java")
    filename: Optional[str] = None


class PipelineRequest(BaseModel):
    """Accepts either source to compile or an already-generated CPG."""

    source: Optional[str] = Field(None, description="Source code to analyze")
    cpg: Optional[Dict[str, Any]] = Field(None, description="CPG GraphSON document")
    language: str = Field("c", description="c | cpp | java")
    filename: Optional[str] = None


class F2aRequest(BaseModel):
    cpg: Dict[str, Any] = Field(..., description="CPG GraphSON document")


def _filename_for(language: str, filename: Optional[str]) -> str:
    return filename or _LANG_EXT.get(language.lower(), "main.c")


def _generate(req: SourceRequest) -> Dict[str, Any]:
    """Generate a CPG, surfacing Joern failures to the UI as 502s."""
    backend = EmbeddedBackend()
    try:
        result = backend.generate(req.source, filename=_filename_for(req.language, req.filename))
    except Exception as exc:  # noqa: BLE001 - surface the Joern error to the UI
        raise HTTPException(status_code=502, detail=f"CPG generation failed ({backend.name}): {exc}") from exc
    return {"cpg": result.graphson, "method_count": result.method_count, "backend": result.backend}


def _fail_as_400(what: str, fn: Callable[[], Any]) -> Any:
    try:
        return fn()
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"{what} failed: {exc}") from exc


def _cpg_document(req: PipelineRequest) -> CPGRoot:
    """Resolve a request to the ``{"export": ...}`` shape the pipeline reads."""
    if req.cpg is not None:
        # Accept both a bare GraphSON doc and one already wrapped.
        return cast(CPGRoot, req.cpg if "export" in req.cpg else {"export": req.cpg})
    if not req.source:
        raise HTTPException(status_code=400, detail="provide either 'source' or 'cpg'")

    generated = _generate(SourceRequest(source=req.source, language=req.language, filename=req.filename))
    return CPGRoot(export=generated["cpg"])


def _functions(req: PipelineRequest) -> List[FunctionGraphs]:
    document = _cpg_document(req)
    nodes = _fail_as_400("template generation", lambda: generate_template(document))
    result: List[FunctionGraphs] = _fail_as_400("analysis", lambda: analyze_template(nodes, source=req.filename or ""))
    return result


@app.get("/health")
def health() -> Dict[str, Any]:
    embedded = EmbeddedBackend()
    # Still a map, though there is one engine now: the web client reads it by
    # key, and `{jpype: false}` is what tells a reader their JOERN_HOME is
    # wrong rather than their request.
    return {"status": "ok", "backends": {embedded.name: embedded.is_available()}}


@app.post("/cpg-jpype")
def cpg_jpype(req: SourceRequest) -> Dict[str, Any]:
    return _generate(req)


@app.post("/template")
def template(req: PipelineRequest) -> Dict[str, Any]:
    document = _cpg_document(req)
    nodes = _fail_as_400("template generation", lambda: generate_template(document))
    return {"template": [n if isinstance(n, dict) else n.model_dump() for n in nodes]}


@app.post("/ast")
def ast(req: PipelineRequest) -> Dict[str, Any]:
    return {"functions": [{"name": fn.name, "ast": fn.ast} for fn in _functions(req)]}


@app.post("/dfg")
def dfg(req: PipelineRequest) -> Dict[str, Any]:
    return {"functions": [{"name": fn.name, "dfg": fn.dfg} for fn in _functions(req)]}


@app.post("/analyze-functions")
def analyze_functions(req: PipelineRequest) -> Dict[str, Any]:
    return {"functions": [training_record(fn, include_template=False) for fn in _functions(req)]}


@app.post("/f2a")
def f2a(req: F2aRequest) -> Dict[str, Any]:
    result = _fail_as_400("F2-A analysis", lambda: run_f2a(req.cpg))
    data: Dict[str, Any] = result.model_dump()
    return data


@app.post("/analyze")
def analyze(req: SourceRequest) -> Dict[str, Any]:
    """CPG + F2-A in one call -- what the F2-A web UI uses."""
    generated = _generate(req)
    cpg_doc = generated["cpg"]
    result = _fail_as_400("F2-A analysis", lambda: run_f2a(cpg_doc))
    return {
        "cpg": cpg_doc,
        "method_count": generated["method_count"],
        "f2a": result.model_dump(),
    }
