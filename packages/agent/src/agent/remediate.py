from __future__ import annotations

import difflib
import logging
from dataclasses import dataclass
from typing import Iterable, Literal

from .llm import Outcome, StructuredCaller
from .schema import CandidateRemediation, Finding, Remediation, Span

log = logging.getLogger(__name__)


def reindent(proposed: str, before: list[str]) -> str:
    if not before or not proposed:
        return proposed
    indent = before[0][: len(before[0]) - len(before[0].lstrip())]
    first = proposed.splitlines()[0]
    if not indent or first[:1].isspace():
        return proposed
    return "\n".join(indent + line if line.strip() else line for line in proposed.splitlines())


def build(candidate: CandidateRemediation, span: Span, text: str) -> Remediation:
    proposed = (candidate.replacement or "").strip("\n")
    if not proposed.strip():
        return Remediation(summary=candidate.summary, detail=candidate.detail)

    lines = text.splitlines()
    before = lines[span.start_line - 1 : span.end_line]
    proposed = reindent(proposed, before)
    if before == proposed.splitlines():
        return Remediation(summary=candidate.summary, detail=candidate.detail)

    after = lines[: span.start_line - 1] + proposed.splitlines() + lines[span.end_line :]
    diff = "".join(
        difflib.unified_diff(
            [f"{line}\n" for line in lines],
            [f"{line}\n" for line in after],
            fromfile=f"a/{span.file}",
            tofile=f"b/{span.file}",
            lineterm="\n",
            n=3,
        )
    )
    return Remediation(
        summary=candidate.summary,
        detail=candidate.detail,
        diff=diff or None,
        replacement=proposed,
    )


FIX_SYSTEM = """당신은 이미 확인된 취약점 하나를 실제로 고치는 중입니다.

취약점이 진짜인지는 다시 판단하지 마십시오. 이미 끝난 판단입니다.

`replacement` 에는 아래 '바꿀 부분' 의 줄들을 통째로 대신할 코드를 쓰십시오.
- 그 줄들만 대신합니다. 앞뒤 줄은 건드리지 않습니다.
- 원본과 같은 들여쓰기를 유지하십시오.
- 설명, 주석 표시, 코드 블록 표시(```)를 넣지 마십시오. 코드만 씁니다.
- 그 자리에서 고칠 수 없다면 `replacement` 를 비워 두십시오. 억지로 쓰는 것보다 낫습니다.

`summary` 와 `detail` 은 한국어 문장이어야 합니다."""


def window_around(text: str, span: Span, budget: int) -> str:
    lines = text.splitlines()
    if not lines or budget <= 0:
        return ""

    first = max(1, span.start_line)
    last = min(len(lines), max(span.end_line, first))
    if first > len(lines):
        return ""

    kept = lines[first - 1 : last]
    used = sum(len(line) + 1 for line in kept)
    above, below = first - 1, last

    while used < budget and (above > 0 or below < len(lines)):
        grew = False
        if above > 0:
            size = len(lines[above - 1]) + 1
            if used + size <= budget:
                above -= 1
                used += size
                grew = True
        if below < len(lines):
            size = len(lines[below]) + 1
            if used + size <= budget:
                below += 1
                used += size
                grew = True
        if not grew:
            break

    window = "\n".join(lines[above:below])
    if above > 0 or below < len(lines):
        window = f"... [{span.file} 의 {above + 1}-{below}번 줄]\n{window}"
    return window


def fix_user(
    *,
    title: str,
    explanation: str,
    span: Span,
    excerpt: str,
    context: str,
) -> str:
    where = f"{span.file}:{span.start_line}-{span.end_line}"
    parts = [
        f"=== 취약점 ===\n{title}\n\n{explanation}",
        f"=== 바꿀 부분 ({where}) ===\n{excerpt}",
    ]
    if context.strip():
        parts.append(f"=== 이 부분이 있는 코드 ===\n{context}")
    return "\n\n".join(parts)


def propose(
    caller: StructuredCaller,
    *,
    title: str,
    explanation: str,
    span: Span,
    excerpt: str,
    context: str,
    prompt: str | None = None,
    trace: dict | None = None,
) -> Outcome[CandidateRemediation]:
    try:
        return caller.call(
            CandidateRemediation,
            prompt or FIX_SYSTEM,
            fix_user(title=title, explanation=explanation, span=span, excerpt=excerpt, context=context),
            trace=trace,
        )
    except Exception as err:  # noqa: BLE001 - reported to the reader as "no fix", not raised
        log.warning("fix proposal failed for %s: %s", span.file, err)
        return Outcome.failed("transport")


class Stale(ValueError):
    pass


def splice(original: str, span: Span, replacement: str) -> str:
    body = replacement.strip("\n")
    if not body.strip():
        raise Stale("this finding has no fix that can be applied in place")

    lines = original.splitlines(keepends=True)
    if span.start_line < 1 or span.end_line > len(lines):
        raise Stale("the file no longer has the lines this finding is anchored to")

    current = "".join(lines[span.start_line - 1 : span.end_line]).rstrip("\n")
    if span.excerpt.strip() and current.strip() != span.excerpt.strip():
        raise Stale("the file changed after it was analysed")

    ending = "\n" if lines[span.end_line - 1].endswith("\n") else ""
    return "".join(lines[: span.start_line - 1]) + body + ending + "".join(lines[span.end_line :])


def unified_diff(path: str, before: str, after: str) -> str:
    if before == after:
        return ""
    patch = difflib.unified_diff(
        before.splitlines(keepends=True),
        after.splitlines(keepends=True),
        fromfile=f"a/{path}",
        tofile=f"b/{path}",
        n=3,
    )
    return "".join(patch)


SkipReason = Literal["no_replacement", "overlap", "stale", "unreadable"]


@dataclass(frozen=True)
class Skip:
    finding_id: str
    reason: SkipReason
    detail: str = ""


@dataclass(frozen=True)
class PatchSet:
    patch: str
    applied: list[str]
    skipped: list[Skip]
    files: dict[str, str]


def _overlaps(span: Span, taken: list[tuple[int, int]]) -> bool:
    return any(span.start_line <= end and start <= span.end_line for start, end in taken)


def _precedence(finding: Finding) -> tuple[int, float, str]:
    width = finding.primary.end_line - finding.primary.start_line
    return (-width, -finding.confidence, finding.id)


def patch_set(sources: dict[str, str], findings: Iterable[Finding]) -> PatchSet:
    applied: list[str] = []
    skipped: list[Skip] = []
    patched: dict[str, str] = {}
    by_file: dict[str, list[Finding]] = {}
    for finding in findings:
        by_file.setdefault(finding.primary.file, []).append(finding)

    for path in sorted(by_file):
        original = sources.get(path)
        if original is None:
            for finding in sorted(by_file[path], key=_precedence):
                skipped.append(Skip(finding.id, "unreadable", f"{path} 은 이 검사에 없는 파일입니다"))
            continue

        winners: list[Finding] = []
        taken: list[tuple[int, int]] = []
        for finding in sorted(by_file[path], key=_precedence):
            if not (finding.remediation.replacement or "").strip():
                skipped.append(Skip(finding.id, "no_replacement"))
                continue
            if _overlaps(finding.primary, taken):
                skipped.append(
                    Skip(finding.id, "overlap", f"{path}:{finding.primary.start_line} 은 이미 고칠 줄과 겹칩니다")
                )
                continue
            taken.append((finding.primary.start_line, finding.primary.end_line))
            winners.append(finding)

        text = original
        for finding in sorted(winners, key=lambda f: (-f.primary.start_line, f.id)):
            try:
                text = splice(text, finding.primary, finding.remediation.replacement or "")
            except Stale as err:
                skipped.append(Skip(finding.id, "stale", str(err)))
                continue
            applied.append(finding.id)

        if text != original:
            patched[path] = text

    patch = "".join(unified_diff(path, sources[path], patched[path]) for path in sorted(patched))
    return PatchSet(patch=patch, applied=applied, skipped=skipped, files=patched)
