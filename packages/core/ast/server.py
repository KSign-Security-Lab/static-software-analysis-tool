# packages/core/ast/server.py
from __future__ import annotations

# server.py
import os
import sys
from typing import Any, Dict, Optional

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

sys.path.append(os.path.dirname(__file__))  # allow 'import ASTExtractor' as a sibling
from ASTExtractor import SCHEMA_VERSION, ASTExtractorV1_12

# --------- FastAPI setup ---------
app = FastAPI(
    title="C-AST Extractor API",
    version=SCHEMA_VERSION,
    description="Expose ASTExtractorV1_12.run() over HTTP",
)

# CORS (adjust for your TS dev server origin)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # or ["http://localhost:5173", "http://localhost:3000"]
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------- Schemas ---------
class RunOptions(BaseModel):
    lift_pure_cond_calls: bool = Field(
        default=False,
        description="Lift pure parse calls like atoi/strtol from conditions",
    )


class RunRequest(BaseModel):
    ast: Dict[str, Any] = Field(
        ..., description="Function-level AST JSON the extractor expects"
    )
    options: Optional[RunOptions] = None


class RunResponse(BaseModel):
    nodes: list[dict]
    edges_ast_pc: list[tuple[int, int, int]]
    edges_ast_sb: list[tuple[int, int, int]]
    edges_ast_guard: list[dict]
    schema_version: str = SCHEMA_VERSION


@app.post("/run", response_model=RunResponse)
def run(req: RunRequest):
    try:
        extractor = ASTExtractorV1_12(
            req.ast,
            lift_pure_cond_calls=bool(req.options and req.options.lift_pure_cond_calls),
        )
        out = extractor.run()
        # normalize tuples for JSON (FastAPI handles, but be explicit)
        return RunResponse(
            nodes=out.get("nodes", []),
            edges_ast_pc=[tuple(t) for t in out.get("edges_ast_pc", [])],
            edges_ast_sb=[tuple(t) for t in out.get("edges_ast_sb", [])],
            edges_ast_guard=out.get("edges_ast_guard", []),
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"extractor error: {e}")


if __name__ == "__main__":
    # Dev: uvicorn directly
    uvicorn.run("packages.core.ast.server:app", host="0.0.0.0", port=8000, reload=True)
