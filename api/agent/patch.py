from __future__ import annotations

import io
import logging
import zipfile
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from agent.remediate import PatchSet, patch_set
from agent.runs import Run
from agent.schema import Finding
from agent.vcs import GitError, Origin, open_pr, push

from .deps import RunDep

log = logging.getLogger(__name__)
router = APIRouter()


class PatchRequest(BaseModel):
    finding_ids: List[str] = Field(min_length=1)


def _selected(run: Run, finding_ids: List[str]) -> tuple[List[Finding], Dict[str, str]]:
    report = run.load_report()
    if report is None:
        raise HTTPException(status_code=409, detail="this run has no completed report")

    by_id = {finding.id: finding for finding in report.findings}
    unknown = [each for each in finding_ids if each not in by_id]
    if unknown:
        raise HTTPException(status_code=404, detail=f"unknown finding: {', '.join(sorted(unknown))}")

    wanted = set(finding_ids)
    findings = [finding for finding in report.sorted_findings() if finding.id in wanted]
    return findings, run.file_contents()


def _build(run: Run, finding_ids: List[str]) -> PatchSet:
    findings, sources = _selected(run, finding_ids)
    return patch_set(sources, findings)


@router.post("/runs/{run_id}/patch")
def run_patch(run: RunDep, request: PatchRequest) -> Dict[str, Any]:
    built = _build(run, request.finding_ids)
    return {
        "run_id": run.run_id,
        "patch": built.patch,
        "applied": built.applied,
        "skipped": [
            {"finding_id": skip.finding_id, "reason": skip.reason, "detail": skip.detail} for skip in built.skipped
        ],
        "files": sorted(built.files),
    }


@router.post("/runs/{run_id}/archive")
def run_archive(run: RunDep, request: PatchRequest) -> Response:
    findings, sources = _selected(run, request.finding_ids)
    built = patch_set(sources, findings)
    if not built.applied:
        raise HTTPException(
            status_code=409,
            detail="적용할 수 있는 패치가 없어 내려받을 소스가 없습니다.",
        )

    merged = {**sources, **built.files}
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(merged):
            info = zipfile.ZipInfo(path, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, merged[path])

    name = f"ssat-{run.run_id}-fixed.zip"
    return Response(
        content=buffer.getvalue(),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{name}"',
            "X-SSAT-Applied": str(len(built.applied)),
            "X-SSAT-Skipped": str(len(built.skipped)),
        },
    )


class PushRequest(PatchRequest):
    branch: str
    token: str = Field(min_length=1)
    open_pull_request: bool = False


@router.post("/runs/{run_id}/push")
def run_push(run: RunDep, request: PushRequest) -> Dict[str, Any]:
    origin = Origin.from_dict(run.read_meta().get("origin"))
    if origin is None or origin.kind != "git":
        raise HTTPException(
            status_code=400,
            detail="이 검사는 git 주소로 가져온 것이 아니어서 올릴 원격이 없습니다.",
        )

    built = _build(run, request.finding_ids)
    if not built.applied:
        raise HTTPException(status_code=409, detail="적용할 수 있는 패치가 없어 올릴 것이 없습니다.")

    title = f"fix: {len(built.applied)}건의 취약점 수정"
    body = "SSAT 검사에서 확인된 항목입니다.\n\n" + "\n".join(f"- {each}" for each in built.applied)

    try:
        pushed = push(origin, built.patch, request.branch, request.token, message=title)
    except GitError as err:
        raise HTTPException(status_code=502, detail=str(err)) from err

    pr_url = open_pr(origin, pushed.branch, request.token, title, body) if request.open_pull_request else None
    return {
        "run_id": run.run_id,
        "branch": pushed.branch,
        "commit": pushed.commit,
        "applied": built.applied,
        "skipped": [{"finding_id": s.finding_id, "reason": s.reason, "detail": s.detail} for s in built.skipped],
        "compare_url": pushed.compare_url,
        "pr_url": pr_url,
    }
