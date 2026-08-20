"""Applying more than one fix at once.

`splice` and `unified_diff` are covered by ``test_secbench.py`` -- one finding,
one file, which is what the benchmark scores. What is not covered there is the
thing the patch button actually does: several findings, possibly several files,
in one patch that has to apply cleanly as a whole.

The ordering test below is the reason `patch_set` exists at all. Everything else
here is about refusing clearly rather than corrupting quietly.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from agent.remediate import patch_set
from agent.schema import Finding, Remediation, Span

TWO_HOLES = """#include <string.h>
void a(char *x) {
    char b[8];
    strcpy(b, x);
}
void c(char *y) {
    char d[8];
    strcpy(d, y);
}
"""


def _finding(
    *,
    id: str,
    file: str,
    line: int,
    excerpt: str,
    replacement: str | None,
    end_line: int | None = None,
) -> Finding:
    return Finding(
        id=id,
        chunk_id=f"{file}::chunk",
        severity="high",
        confidence=0.9,
        title="버퍼 오버플로",
        cwe="CWE-787",
        primary=Span(
            file=file,
            start_line=line,
            start_column=1,
            end_line=end_line or line,
            end_column=1,
            excerpt=excerpt,
        ),
        explanation="경계 검사 없이 복사합니다.",
        remediation=Remediation(summary="길이를 제한합니다", detail="strncpy 로 바꿉니다", replacement=replacement),
        verified=True,
    )


def _grow(name: str) -> str:
    """A replacement that is two lines where the original was one."""
    return f"    strncpy({name}, x, 7);\n    {name}[7] = '\\0';"


def test_two_fixes_in_one_file_both_land() -> None:
    """The lower fix must not move the upper one out from under itself.

    Both replacements grow their line by one. Applied top-down, the second
    finding's span would point one line short of the code it was anchored to and
    `splice` would refuse it as changed-since-analysed -- a fix silently lost
    because of the order the dict happened to be in.
    """
    findings = [
        _finding(id="upper", file="m.c", line=4, excerpt="    strcpy(b, x);", replacement=_grow("b")),
        _finding(id="lower", file="m.c", line=8, excerpt="    strcpy(d, y);", replacement=_grow("d")),
    ]

    result = patch_set({"m.c": TWO_HOLES}, findings)

    assert sorted(result.applied) == ["lower", "upper"]
    assert result.skipped == []
    body = result.files["m.c"]
    assert "strncpy(b, x, 7);" in body
    assert "strncpy(d, x, 7);" in body
    assert "strcpy(" not in body
    # Untouched lines stay untouched: this splices, it does not rewrite.
    assert body.startswith("#include <string.h>\n")


def test_the_order_findings_arrive_in_does_not_matter() -> None:
    """Same two fixes, reversed input. `patch_set` sorts, callers need not."""
    args = [
        dict(id="lower", file="m.c", line=8, excerpt="    strcpy(d, y);", replacement=_grow("d")),
        dict(id="upper", file="m.c", line=4, excerpt="    strcpy(b, x);", replacement=_grow("b")),
    ]
    forward = patch_set({"m.c": TWO_HOLES}, [_finding(**each) for each in args])  # type: ignore[arg-type]
    backward = patch_set({"m.c": TWO_HOLES}, [_finding(**each) for each in reversed(args)])  # type: ignore[arg-type]

    assert forward.files == backward.files
    assert forward.patch == backward.patch


def test_several_files_make_one_patch_in_path_order() -> None:
    sources = {
        "z.c": "void z(void) {\n    gets(buf);\n}\n",
        "a.c": "void a(void) {\n    gets(buf);\n}\n",
    }
    findings = [
        _finding(id="z", file="z.c", line=2, excerpt="    gets(buf);", replacement="    fgets(buf, 8, stdin);"),
        _finding(id="a", file="a.c", line=2, excerpt="    gets(buf);", replacement="    fgets(buf, 8, stdin);"),
    ]

    result = patch_set(sources, findings)

    assert sorted(result.applied) == ["a", "z"]
    # Sorted by path, so the patch is the same whichever order they were ticked.
    assert result.patch.index("a/a.c") < result.patch.index("a/z.c")
    assert result.patch.count("--- a/") == 2


def test_overlapping_selections_refuse_the_second() -> None:
    """Two findings over one region is a tick to undo, not a merge to attempt."""
    findings = [
        _finding(
            id="wide",
            file="m.c",
            line=3,
            end_line=4,
            excerpt="    char b[8];\n    strcpy(b, x);",
            replacement="    char b[64];\n    strncpy(b, x, 63);",
        ),
        _finding(id="narrow", file="m.c", line=4, excerpt="    strcpy(b, x);", replacement=_grow("b")),
    ]

    result = patch_set({"m.c": TWO_HOLES}, findings)

    assert result.applied == ["wide"]
    assert [(s.finding_id, s.reason) for s in result.skipped] == [("narrow", "overlap")]
    assert "char b[64];" in result.files["m.c"]


def test_advice_without_code_is_reported_not_guessed() -> None:
    result = patch_set(
        {"m.c": TWO_HOLES},
        [_finding(id="prose", file="m.c", line=4, excerpt="    strcpy(b, x);", replacement=None)],
    )

    assert result.applied == []
    assert [(s.finding_id, s.reason) for s in result.skipped] == [("prose", "no_replacement")]
    assert result.patch == ""
    assert result.files == {}


def test_an_anchor_that_no_longer_matches_is_stale() -> None:
    result = patch_set(
        {"m.c": TWO_HOLES},
        [_finding(id="moved", file="m.c", line=4, excerpt="    memcpy(b, x, 99);", replacement=_grow("b"))],
    )

    assert result.applied == []
    assert [s.reason for s in result.skipped] == ["stale"]


def test_a_file_the_run_does_not_have_is_its_own_reason() -> None:
    result = patch_set(
        {"m.c": TWO_HOLES},
        [_finding(id="gone", file="other.c", line=1, excerpt="x", replacement="y")],
    )

    assert [(s.finding_id, s.reason) for s in result.skipped] == [("gone", "unreadable")]


def test_one_good_fix_survives_a_bad_neighbour() -> None:
    """A refusal is per finding. It must not cost the file its other fixes."""
    findings = [
        _finding(id="ok", file="m.c", line=4, excerpt="    strcpy(b, x);", replacement=_grow("b")),
        _finding(id="bad", file="m.c", line=8, excerpt="    nothing_like_this();", replacement=_grow("d")),
    ]

    result = patch_set({"m.c": TWO_HOLES}, findings)

    assert result.applied == ["ok"]
    assert [s.reason for s in result.skipped] == ["stale"]
    assert "strncpy(b, x, 7);" in result.files["m.c"]


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_the_emitted_patch_is_one_git_apply_can_take(tmp_path: Path) -> None:
    """The claim the whole feature rests on, checked by git rather than by us.

    A patch that reads correctly and does not apply is worse than no patch: it
    is handed over as a deliverable and fails on somebody else's machine.
    """
    findings = [
        _finding(id="upper", file="m.c", line=4, excerpt="    strcpy(b, x);", replacement=_grow("b")),
        _finding(id="lower", file="m.c", line=8, excerpt="    strcpy(d, y);", replacement=_grow("d")),
        _finding(id="other", file="a.c", line=2, excerpt="    gets(buf);", replacement="    fgets(buf, 8, stdin);"),
    ]
    sources = {"m.c": TWO_HOLES, "a.c": "void a(void) {\n    gets(buf);\n}\n"}

    result = patch_set(sources, findings)
    assert sorted(result.applied) == ["lower", "other", "upper"]

    for path, text in sources.items():
        (tmp_path / path).write_text(text, encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)  # noqa: S603, S607 - fixed argv, no shell

    check = subprocess.run(  # noqa: S603, S607 - fixed argv, no shell
        ["git", "apply", "--check", "-"],
        cwd=tmp_path,
        input=result.patch,
        capture_output=True,
        text=True,
    )
    assert check.returncode == 0, check.stderr

    applied = subprocess.run(  # noqa: S603, S607 - fixed argv, no shell
        ["git", "apply", "-"], cwd=tmp_path, input=result.patch, capture_output=True, text=True
    )
    assert applied.returncode == 0, applied.stderr
    # And what git produced is what the archive would have shipped.
    for path, text in result.files.items():
        assert (tmp_path / path).read_text(encoding="utf-8") == text
