from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from agent.remediate import patch_set, window_around
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
    return f"    strncpy({name}, x, 7);\n    {name}[7] = '\\0';"


def test_two_fixes_in_one_file_both_land() -> None:
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
    assert body.startswith("#include <string.h>\n")


def test_the_order_findings_arrive_in_does_not_matter() -> None:
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
    assert result.patch.index("a/a.c") < result.patch.index("a/z.c")
    assert result.patch.count("--- a/") == 2


def test_overlapping_selections_refuse_the_second() -> None:
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
    for path, text in result.files.items():
        assert (tmp_path / path).read_text(encoding="utf-8") == text


def _span(line: int, *, end: int | None = None, file: str = "src/big.c") -> Span:
    return Span(file=file, start_line=line, start_column=1, end_line=end or line, end_column=1, excerpt="")


def _numbered(count: int) -> str:
    return "\n".join(f"line {n:04d} aaaaaaaaaaaaaaaaaaaa" for n in range(1, count + 1))


def test_the_window_stays_inside_its_budget() -> None:
    text = _numbered(4000)
    window = window_around(text, _span(2000), 2_000)

    assert len(window) <= 2_000 + 80
    assert "line 2000" in window


def test_the_lines_being_replaced_are_always_in_it() -> None:
    text = _numbered(4000)
    window = window_around(text, _span(1500, end=1512), 400)

    for n in range(1500, 1513):
        assert f"line {n:04d}" in window


def test_it_is_centred_on_the_span_not_cut_from_the_top() -> None:
    text = _numbered(4000)
    window = window_around(text, _span(2000), 3_000)

    assert "line 1990" in window and "line 2010" in window
    assert "line 0001" not in window


def test_whole_lines_only() -> None:
    text = _numbered(4000)
    window = window_around(text, _span(2000), 1_337)
    body = [line for line in window.splitlines() if line.startswith("line ")]
    assert body
    assert all(line.endswith("aaaaaaaaaaaaaaaaaaaa") for line in body)


def test_a_span_at_either_end_of_the_file_still_gets_context() -> None:
    text = _numbered(200)
    top = window_around(text, _span(1), 600)
    bottom = window_around(text, _span(200), 600)

    assert "line 0001" in top and "line 0005" in top
    assert "line 0200" in bottom and "line 0196" in bottom


def test_a_small_file_arrives_whole_and_unannounced() -> None:
    text = _numbered(10)
    window = window_around(text, _span(5), 100_000)

    assert window == text
    assert "..." not in window


def test_a_cut_file_says_so() -> None:
    window = window_around(_numbered(4000), _span(2000), 2_000)

    assert window.startswith("... [src/big.c 의 ")


def test_nothing_to_show_is_empty_rather_than_a_guess() -> None:
    assert window_around("", _span(1), 1_000) == ""
    assert window_around(_numbered(10), _span(5), 0) == ""
    assert window_around(_numbered(10), _span(99), 1_000) == ""
