"""Turning a selection of findings into something that leaves the browser.

The report says what is wrong. This says what to do about it, in the three forms
somebody can actually use: a patch to review, a tree to build, or a branch to
open a pull request from.

Nothing here writes to the run. The tree a report was made from is immutable --
that is what makes a patch reproducible and what makes ``PatchSet.files`` the
same thing whether it is downloaded as an archive or applied by ``git apply``.
"""

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
    """Which findings to fix.

    Ids rather than the findings themselves: what gets spliced has to be what
    the run recorded, not what a client sends back. A browser that could post a
    replacement could post any replacement, and the result would still be
    labelled as the agent's fix.
    """

    finding_ids: List[str] = Field(min_length=1)


def _selected(run: Run, finding_ids: List[str]) -> tuple[List[Finding], Dict[str, str]]:
    """The findings named, and the sources they were found in.

    Refuses an unknown id instead of quietly patching a subset. A reader who
    ticked five things and got three fixes with no explanation would have no way
    to tell which two were dropped or why.
    """
    report = run.load_report()
    if report is None:
        raise HTTPException(status_code=409, detail="this run has no completed report")

    by_id = {finding.id: finding for finding in report.findings}
    unknown = [each for each in finding_ids if each not in by_id]
    if unknown:
        raise HTTPException(status_code=404, detail=f"unknown finding: {', '.join(sorted(unknown))}")

    # Report order, not request order, so the patch is stable across clients.
    wanted = set(finding_ids)
    findings = [finding for finding in report.sorted_findings() if finding.id in wanted]
    return findings, run.file_contents()


def _build(run: Run, finding_ids: List[str]) -> PatchSet:
    findings, sources = _selected(run, finding_ids)
    return patch_set(sources, findings)


@router.post("/runs/{run_id}/patch")
def run_patch(run: RunDep, request: PatchRequest) -> Dict[str, Any]:
    """The selected fixes as one unified diff, plus what did not make it.

    A preview, and the only thing the reader sees before deciding. The skipped
    list is the point: a finding with advice and no code, two ticks over one
    region, an anchor that moved -- each is answered differently, so each is
    reported with its own reason rather than as a smaller patch than expected.

    Returns 200 with an empty patch when nothing could be applied. That is an
    answer about the selection, not a failure of the request.
    """
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
    """The whole tree with the selected fixes in it, as a zip.

    Every source file this run analysed, not only the patched ones -- working out
    which of four hundred to combine a three-file zip with is exactly the work
    this was supposed to save.

    Not the *whole* tree, and it cannot be: intake stores only what the analyser
    reads, so a Makefile or a PNG was never here to ship. This is something to
    unpack over a checkout, not something to build from scratch, and the intake
    screen says which files were left out.

    Refuses when nothing applied. An archive identical to the upload, named as
    though it were fixed, is the one output here that could mislead somebody
    into shipping unpatched code.
    """
    findings, sources = _selected(run, request.finding_ids)
    built = patch_set(sources, findings)
    if not built.applied:
        raise HTTPException(
            status_code=409,
            detail="적용할 수 있는 패치가 없어 내려받을 소스가 없습니다.",
        )

    merged = {**sources, **built.files}
    buffer = io.BytesIO()
    # Deflated and deterministic: same selection, same bytes. ZIP_DEFLATED
    # rather than stored because source trees compress to a fraction and this
    # goes over a browser connection.
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
            # The count is in a header so the client can report it without
            # parsing the archive it just told the browser to save.
            "X-SSAT-Applied": str(len(built.applied)),
            "X-SSAT-Skipped": str(len(built.skipped)),
        },
    )


class PushRequest(PatchRequest):
    """Where to put the fix, and what may be used to put it there.

    `token` is a credential the caller supplies for this one request. It is held
    for the duration of the call, used only against the URL recorded on the run,
    and never written to the database or a log. This service has no login, so a
    server-side token would mean every user of the instance pushing as the same
    identity to anywhere that identity can reach -- a per-request token is the
    version of this that cannot outlive the request.
    """

    branch: str
    token: str = Field(min_length=1)
    open_pull_request: bool = False


@router.post("/runs/{run_id}/push")
def run_push(run: RunDep, request: PushRequest) -> Dict[str, Any]:
    """Apply the selected fixes on a fresh clone of the origin and push a branch.

    Only for a run that came from a git URL, because only then is there a remote
    and a base commit to be honest about. For an upload there is nothing to push
    to, and the client is expected not to offer the button at all rather than to
    show one that explains itself away.

    The patch is built here rather than taken from the client for the same
    reason `/patch` takes ids: a request that could carry its own diff could
    carry any diff, and it would still be pushed as the agent's fix.
    """
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
        # `vcs.redact` has already been through the message; the token cannot be
        # in it. 502 because the refusal came from the remote, not from us.
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
