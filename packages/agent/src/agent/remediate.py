"""Turning a proposed fix into something that can be applied, and asking for one.

Two callers, and they must agree. During a run a specialist proposes a fix as
part of its finding; afterwards, a reader looking at a finding that arrived
without one can ask for it. If those two produced different shapes -- one with a
diff and one without, one re-indented and one not -- then whether the button
worked would depend on which path happened to make the fix, which is exactly the
kind of thing nobody would think to test.

So the building lives here and both import it. `nodes.py` calls `build` with what
the specialist already said; the API calls `propose` first to get the same
material out of the model, then `build`.
"""

from __future__ import annotations

import difflib
import logging

from .llm import StructuredCaller
from .schema import CandidateRemediation, Remediation, Span

log = logging.getLogger(__name__)


def reindent(proposed: str, before: list[str]) -> str:
    """Put back the indentation the model dropped.

    Asked for code that matches the original's indentation, a model returns
    `snprintf(...)` at column zero for a line that was four spaces in. In C that
    is untidy; in Python it is a syntax error, and this writes to real files.

    The original's own leading whitespace is right there, so it is used rather
    than trusted from the answer -- and only when the replacement clearly has
    none of its own, so a fix that deliberately re-indents is left alone.
    """
    if not before or not proposed:
        return proposed
    indent = before[0][: len(before[0]) - len(before[0].lstrip())]
    first = proposed.splitlines()[0]
    if not indent or first[:1].isspace():
        return proposed
    return "\n".join(indent + line if line.strip() else line for line in proposed.splitlines())


def build(candidate: CandidateRemediation, span: Span, text: str) -> Remediation:
    """The proposed fix, with the diff computed rather than quoted.

    The model supplies replacement lines for the span the anchor resolved to;
    the diff shown to a reader is generated from that and the file on disk. So
    what is displayed is what applying would actually do, instead of a patch the
    model wrote a description of -- those two drift, and the one on screen is
    the one that gets trusted.
    """
    proposed = (candidate.replacement or "").strip("\n")
    if not proposed.strip():
        return Remediation(summary=candidate.summary, detail=candidate.detail)

    lines = text.splitlines()
    before = lines[span.start_line - 1 : span.end_line]
    proposed = reindent(proposed, before)
    if before == proposed.splitlines():
        # Nothing to do, and offering to do it would be a lie.
        return Remediation(summary=candidate.summary, detail=candidate.detail)

    # Against the whole file, which is what makes it a diff somebody can read.
    # It used to diff the replaced lines against themselves in isolation, so a
    # change at line 6 was headed `@@ -1 +1 @@` -- the right change under the
    # wrong line number, with no surrounding code to place it. Three lines of
    # context and real offsets, which is `git diff`.
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


#: Asked of a finding that arrived with advice and no code.
#:
#: Narrower than the analysis prompt on purpose. The judgement is already made --
#: this is not being asked whether the problem is real, and inviting it to
#: re-litigate that is how a fix turns into a second opinion. It has one job, and
#: the constraint that makes the result applicable at all is the span: whatever it
#: writes replaces exactly those lines, so it must be a whole, self-contained
#: replacement for them and nothing else.
FIX_SYSTEM = """당신은 이미 확인된 취약점 하나를 실제로 고치는 중입니다.

취약점이 진짜인지는 다시 판단하지 마십시오. 이미 끝난 판단입니다.

`replacement` 에는 아래 '바꿀 부분' 의 줄들을 통째로 대신할 코드를 쓰십시오.
- 그 줄들만 대신합니다. 앞뒤 줄은 건드리지 않습니다.
- 원본과 같은 들여쓰기를 유지하십시오.
- 설명, 주석 표시, 코드 블록 표시(```)를 넣지 마십시오. 코드만 씁니다.
- 그 자리에서 고칠 수 없다면 `replacement` 를 비워 두십시오. 억지로 쓰는 것보다 낫습니다.

`summary` 와 `detail` 은 한국어 문장이어야 합니다."""


def fix_user(
    *,
    title: str,
    explanation: str,
    span: Span,
    excerpt: str,
    context: str,
) -> str:
    """The brief: what is wrong, the lines to replace, and the file around them."""
    where = f"{span.file}:{span.start_line}-{span.end_line}"
    parts = [
        f"=== 취약점 ===\n{title}\n\n{explanation}",
        f"=== 바꿀 부분 ({where}) ===\n{excerpt}",
    ]
    if context.strip():
        parts.append(f"=== 이 부분이 있는 파일 ===\n{context}")
    return "\n\n".join(parts)


def propose(
    caller: StructuredCaller,
    *,
    title: str,
    explanation: str,
    span: Span,
    excerpt: str,
    context: str,
    trace: dict | None = None,
) -> CandidateRemediation | None:
    """Ask for a fix. None when the model would not give one.

    Never raises. This is reached from a button on a page, and a model that
    times out or answers in the wrong shape should leave the reader where they
    were rather than showing them a stack trace.
    """
    try:
        return caller.call(
            CandidateRemediation,
            FIX_SYSTEM,
            fix_user(title=title, explanation=explanation, span=span, excerpt=excerpt, context=context),
            trace=trace,
        )
    except Exception as err:  # noqa: BLE001 - reported to the reader as "no fix", not raised
        log.warning("fix proposal failed for %s: %s", span.file, err)
        return None
