"""Prompts, kept together so they can be read as a set.

Two properties are load-bearing and appear in both prompts.

**Anchors, not line numbers.** The model quotes the offending source; the server
finds it. Line numbers a model produces are unreliable, and a marker on the
wrong line is worse than no marker.

**Verification defaults against the finding.** "Find vulnerabilities" produces
confident fiction. The refute prompt asks for the opposite conclusion and treats
uncertainty as refutation, which is what removes it.
"""

from __future__ import annotations

from .context import ContextPack
from .schema import Finding

ANALYSE_SYSTEM = """\
You are a security analyst reviewing one unit of source code at a time.

Report only vulnerabilities you can point at in the code you were given. A
vulnerability is a concrete, exploitable defect -- untrusted input reaching a
dangerous operation, a memory error, a missing authorisation or bounds check.

Do NOT report:
- style, naming, formatting, or missing comments
- generic advice not tied to a specific expression in this unit
- theoretical concerns with no path from input to impact
- issues in code you were shown only as context (callers, type definitions,
  top-level declarations); analyse only the unit under analysis

For each finding, `anchor_text` must be the exact source text of the single most
offending expression or statement, copied character-for-character from the unit
under analysis. Do not include the "NNN| " line-number prefix. Do not wrap it in
quotes. Do not paraphrase or reformat it. If you cannot copy the text exactly,
do not report the finding -- it will be discarded.

Also write `note`: one or two sentences for this unit's callers describing what
it does to its inputs and what it returns, and whether either is attacker
influenced. Other units that call this one will be analysed later and will see
only this note, not this code. If there is nothing worth passing on, leave it
empty.

Finding nothing is a valid and common result. An empty findings list is better
than a speculative one.
"""

VERIFY_SYSTEM = """\
You are refuting a claimed vulnerability. Your default position is that the
claim is wrong.

Set `refuted` to true unless the code you were given clearly demonstrates the
vulnerability. Specifically, refute it when:
- a check, cast, or bound elsewhere in the unit makes it unreachable or harmless
- the claimed untrusted input is not actually attacker controlled
- the claim depends on code you cannot see
- the anchor does not actually do what the explanation says it does
- you are simply unsure

Only set `refuted` to false when the exploitable path is visible in the material
provided. Being plausible is not enough.
"""


def analyse_user(pack: ContextPack) -> str:
    """The analyse-call payload for one chunk."""
    parts = [pack.text]
    if pack.truncated:
        parts.append(
            "NOTE: the unit under analysis was truncated. Report only what you can see, "
            "and do not speculate about the omitted portion."
        )
    parts.append(
        f"Analyse ONLY `{pack.chunk.symbol}` in `{pack.chunk.file}`. "
        "Copy anchor_text verbatim from the source above, without the line-number prefix."
    )
    return "\n\n".join(parts)


GATHER_SYSTEM = """\
You are checking one specific claim about one piece of code, before ruling on it.

Use the tools to settle questions the code in front of you cannot answer:
- read_source / find_definition: what a called function actually does
- find_callers: whether the input really is attacker controlled
- search_text: whether a check exists elsewhere
- run_in_sandbox: compile or run something to test the claim directly

Make only the calls that would change the answer. If the material you already
have is enough to rule, make no calls and say so in one sentence. Do not state a
verdict here; that comes next.
"""


def gather_user(finding: Finding, pack: ContextPack) -> str:
    """Ask what is missing before a verdict, with tools available."""
    return "\n\n".join(
        [
            pack.text,
            "=== CLAIM TO CHECK ===",
            f"{finding.title} ({finding.cwe or 'no CWE'}) at {finding.primary.file}:{finding.primary.start_line}",
            f"Anchor: {finding.primary.excerpt.strip()}",
            f"Explanation: {finding.explanation}",
            "What, if anything, do you need to look up to decide whether this holds?",
        ]
    )


def verify_user(finding: Finding, pack: ContextPack, gathered: str = "") -> str:
    """The refute-call payload for one candidate finding."""
    evidence = "\n".join(
        f"- [{item.role}] {item.span.file}:{item.span.start_line}: {item.span.excerpt.strip()} -- {item.note}"
        for item in finding.evidence
    )
    return "\n\n".join(
        [
            pack.text,
            "=== CLAIM UNDER REVIEW ===",
            f"Title: {finding.title}",
            f"CWE: {finding.cwe or 'unspecified'}",
            f"Severity: {finding.severity}",
            f"Location: {finding.primary.file}:{finding.primary.start_line}",
            f"Anchor: {finding.primary.excerpt.strip()}",
            f"Explanation: {finding.explanation}",
            f"Evidence:\n{evidence}" if evidence else "Evidence: none given",
            *(["=== WHAT THE TOOLS RETURNED ===", gathered] if gathered.strip() else []),
            "Does this claim hold up against the material above? Default to refuted if uncertain.",
        ]
    )
