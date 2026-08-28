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
from dataclasses import dataclass
from typing import Iterable, Literal

from .llm import Outcome, StructuredCaller
from .schema import CandidateRemediation, Finding, Remediation, Span

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


def window_around(text: str, span: Span, budget: int) -> str:
    """The lines around a span, within a character budget.

    The fix prompt used to be handed the whole file. That is the one prompt path
    in this package with no budget at all, and on a real tree it is not close:
    `Ksign_ASN1.c` is 197KB, which is roughly 123 000 tokens against a 16 384
    window, and the endpoint answers `max_tokens must be at least 1, got
    -43420`. Run dbd2c9e7ca62 lost 48 fix calls that way -- every one of them in
    one of the four largest files, and 23 of that tree's 125 files are too large
    for the window on their own.

    Centred on the span rather than cut from the top, because a fix needs what
    surrounds the lines it replaces: the declaration of the buffer, the check
    that is missing, the `goto err` it should jump to. A prefix cut gives the
    top of the file, which for a 4000-line C file is the includes.

    Whole lines only. Handing a model half a statement invites it to complete
    the half it can see.
    """
    lines = text.splitlines()
    if not lines or budget <= 0:
        return ""

    first = max(1, span.start_line)
    last = min(len(lines), max(span.end_line, first))
    if first > len(lines):
        return ""

    # The span itself is not negotiable -- it is what the fix replaces -- so it
    # is taken first and the budget spent outward from there.
    kept = lines[first - 1 : last]
    used = sum(len(line) + 1 for line in kept)
    above, below = first - 1, last  # 0-based indices of the next line each way

    # Alternating, so a span near the top of a file still gets context below it
    # instead of stopping at the file's first line with budget unspent.
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
        # Said, so the model does not read a truncated file as a whole one and
        # conclude a caller never validates what it in fact validates offscreen.
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
    """The brief: what is wrong, the lines to replace, and the code around them.

    ``context`` is expected to be windowed already -- see :func:`window_around`.
    Both callers budget it, because the two must agree on what the model sees.
    """
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
    """Ask for a fix, as a value or a reason.

    Never raises. This is reached from a button on a page, and a model that
    times out or answers in the wrong shape should leave the reader where they
    were rather than showing them a stack trace.

    The reason travels with it because "there is no patch" and "the patch call
    died" look the same on screen otherwise -- and the surface was offering
    고칠 코드 만들기 for a call that had already failed on the token limit.
    """
    try:
        return caller.call(
            CandidateRemediation,
            # Tunable from the studio like every other step's, and only falling
            # back to the built-in when a caller has no prompt store to hand.
            prompt or FIX_SYSTEM,
            fix_user(title=title, explanation=explanation, span=span, excerpt=excerpt, context=context),
            trace=trace,
        )
    except Exception as err:  # noqa: BLE001 - reported to the reader as "no fix", not raised
        log.warning("fix proposal failed for %s: %s", span.file, err)
        return Outcome.failed("transport")


class Stale(ValueError):
    """The file is not what was analysed.

    Its own type because the two callers do different things with it: the API
    turns it into a 409 telling the reader to re-inspect, and the sweep counts
    the instance as unpatched rather than aborting the whole run.
    """


def splice(original: str, span: Span, replacement: str) -> str:
    """Put a finding's replacement over the lines it is anchored to.

    Here rather than in the route, because two things now apply a patch -- a
    person pressing 이대로 고치기, and the SEC-bench sweep taking what the agent
    produced -- and an off-by-one in one of two copies would corrupt source
    while the other stayed correct. The span is 1-based and inclusive, which is
    exactly the arithmetic worth having in one place.

    Refuses rather than guesses. A span past the end of the file, or an excerpt
    that no longer matches, means the file moved since it was analysed; applying
    to that is applying to code nobody looked at.
    """
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
    """A `git apply`-able patch for one file.

    What SEC-bench's evaluator consumes. Our agent works in replacements for a
    line range -- which is what an editor wants -- and every benchmark in this
    space speaks diffs, so the translation happens here and once.

    `a/`/`b/` prefixes because that is what `git apply` expects by default; the
    evaluator applies these inside the instance's work directory.
    """
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


#: Why a selected finding did not make it into the patch.
#:
#: Four reasons rather than a bool, because the reader's next move differs for
#: each: `no_replacement` is answered by asking for one, `overlap` by unticking
#: one of the two, `stale` by re-inspecting, and `unreadable` is ours to fix.
SkipReason = Literal["no_replacement", "overlap", "stale", "unreadable"]


@dataclass(frozen=True)
class Skip:
    """One finding that was asked for and refused, and why."""

    finding_id: str
    reason: SkipReason
    detail: str = ""


@dataclass(frozen=True)
class PatchSet:
    """Everything the selected findings amount to.

    `patch` is one `git apply`-able diff over however many files were touched;
    `files` is the same result as whole texts, because a zip cannot be built
    from a diff. Both come out of the same splices rather than being computed
    twice -- a patch and an archive that disagreed about what the fix was would
    be the worst possible bug here.
    """

    patch: str
    applied: list[str]
    skipped: list[Skip]
    files: dict[str, str]


def _overlaps(span: Span, taken: list[tuple[int, int]]) -> bool:
    return any(span.start_line <= end and start <= span.end_line for start, end in taken)


def _precedence(finding: Finding) -> tuple[int, float, str]:
    """Which of two overlapping fixes to keep.

    Widest span first. A fix covering lines 3-4 rewrites the line that a fix
    covering only line 4 was going to rewrite, so the wide one subsumes it;
    keeping the narrow one instead would apply the smaller change and drop the
    larger. Confidence breaks ties, then the id, so the answer does not depend
    on the order the ticks arrived in.

    Deliberately separate from the order the splices are *applied* in. That has
    to be bottom-up for the line arithmetic to hold, and letting position decide
    precedence too meant whichever finding happened to sit lower in the file
    won -- a rule nobody chose and nobody could explain to a reader.
    """
    width = finding.primary.end_line - finding.primary.start_line
    return (-width, -finding.confidence, finding.id)


def patch_set(sources: dict[str, str], findings: Iterable[Finding]) -> PatchSet:
    """The selected findings, as one patch and one patched tree.

    Two orderings, and they are not the same one. Conflicts are resolved by
    `_precedence` -- the wider fix wins the region -- and the survivors are then
    spliced **bottom-up**, because `splice` addresses lines by number: fixing
    line 12 before line 40 would shift line 40 by however many lines the first
    fix added, and the second splice would land on code nobody analysed.

    Refuses rather than guesses, and says which. `splice` catches an anchor that
    no longer matches; everything it cannot see -- a file this run does not have,
    a finding with advice and no code, a region already claimed -- is caught here.
    Every refusal is a `Skip` with a reason the reader can act on.
    """
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

        # Claim regions by precedence, so the winner does not depend on position.
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

        # Then splice bottom-up, so no fix moves another out from under itself.
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
