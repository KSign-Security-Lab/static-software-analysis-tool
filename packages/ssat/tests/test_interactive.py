import io
from pathlib import Path
from typing import Callable, List

import pytest

from ssat.cli.interactive import (
    DOWN,
    ENTER,
    QUIT,
    UP,
    Choice,
    browse,
    build_argv,
    exts_for,
    run_interactive,
    select_one,
)


def keys(*sequence: str) -> Callable[[], str]:
    pending = list(sequence)
    return lambda: pending.pop(0)


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "corpus").mkdir()
    (tmp_path / "corpus" / "one.c").write_text("int main(void) { return 0; }\n")
    (tmp_path / "corpus" / "two.c").write_text("int f(void) { return 1; }\n")
    (tmp_path / "cpg").mkdir()
    (tmp_path / "cpg" / "one.c.json").write_text("{}")
    (tmp_path / "node_modules").mkdir()
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_select_one_wraps_and_picks() -> None:
    out = io.StringIO()
    choices = [Choice("a", 1), Choice("b", 2), Choice("c", 3)]
    assert select_one("pick", choices, read=keys(UP, ENTER), out=out) == 3
    assert select_one("pick", choices, read=keys(DOWN, DOWN, ENTER), out=out) == 3


def test_select_one_backs_out() -> None:
    assert select_one("pick", [Choice("a", 1)], read=keys(QUIT), out=io.StringIO()) is None


def test_browse_descends_then_picks_a_file(workspace: Path) -> None:
    # [use this directory] .. corpus/ cpg/ -> into corpus/ -> [use] .. one.c two.c
    picked = browse("Input", workspace, exts=["c"], read=keys(DOWN, DOWN, ENTER, DOWN, DOWN, ENTER), out=io.StringIO())
    assert picked == workspace / "corpus" / "one.c"


def test_browse_picks_the_directory_it_starts_in(workspace: Path) -> None:
    assert (
        browse("Input", workspace / "corpus", exts=["c"], read=keys(ENTER), out=io.StringIO()) == workspace / "corpus"
    )


def test_browse_hides_the_directories_nobody_means(workspace: Path) -> None:
    out = io.StringIO()
    browse("Input", workspace, exts=["c"], read=keys(QUIT), out=out)
    assert "node_modules" not in out.getvalue()


def test_exts_for_a_file_is_its_own_suffix(workspace: Path) -> None:
    assert exts_for(workspace / "cpg" / "one.c.json", ["c", "json"]) == ["json"]


def test_exts_for_a_directory_of_one_kind_asks_nothing(workspace: Path) -> None:
    assert exts_for(workspace / "corpus", ["c", "h", "json"]) == ["c"]


def test_exts_for_a_mixed_directory_asks(workspace: Path) -> None:
    (workspace / "corpus" / "one.c.json").write_text("{}")
    assert exts_for(workspace / "corpus", ["c", "json"], read=keys(ENTER), out=io.StringIO()) == ["json"]


def test_build_argv_carries_the_options() -> None:
    assert build_argv("cpg", Path("corpus"), Path("out"), ["c"], workers=4) == [
        "cpg",
        "corpus",
        "-o",
        "out",
        "--ext",
        "c",
        "--workers",
        "4",
    ]
    assert "--no-replace-macro" in build_argv("ast", Path("in"), None, ["json"], replace_macro=False)
    assert "--no-replace-macro" not in build_argv("ast", Path("in"), None, ["json"])
    assert "--workers" not in build_argv("ast", Path("in"), None, ["json"], workers=4)


def test_run_interactive_assembles_one_stage(workspace: Path) -> None:
    ran: List[List[str]] = []
    code = run_interactive(
        ran.append,
        read=keys(
            DOWN,
            DOWN,
            ENTER,  # stage: ast
            DOWN,
            DOWN,
            DOWN,
            ENTER,
            ENTER,  # input: into cpg/, then use it
            ENTER,  # output: the default
            ENTER,  # macros: fold
            ENTER,  # run it
        ),
        out=io.StringIO(),
        root=workspace,
    )
    assert code == 0
    assert len(ran) == 1
    mode, data, dash_o, output, ext_flag, ext = ran[0]
    assert (mode, data, dash_o, ext_flag, ext) == ("ast", "./cpg", "-o", "--ext", "json")
    assert output.startswith("./result/ast_")


def test_run_interactive_chains_cpg_into_full(workspace: Path) -> None:
    ran: List[List[str]] = []
    run_interactive(
        ran.append,
        read=keys(
            DOWN,
            DOWN,
            DOWN,
            DOWN,
            DOWN,
            DOWN,
            DOWN,
            ENTER,  # stage: cpg+full
            DOWN,
            DOWN,
            ENTER,
            ENTER,  # input: into corpus/, then use it
            ENTER,  # output: the default
            DOWN,
            ENTER,  # macros: leave them alone
            DOWN,
            ENTER,  # workers: 2
            ENTER,  # run it
        ),
        out=io.StringIO(),
        root=workspace,
    )
    assert [argv[0] for argv in ran] == ["cpg", "full"]
    assert ran[0][1] == "./corpus"
    assert ran[0][ran[0].index("--workers") + 1] == "2"
    assert "--no-replace-macro" not in ran[0]  # cpg has no macro handling to skip
    assert ran[1][1] == ran[0][ran[0].index("-o") + 1]  # full reads what cpg wrote
    assert "--no-replace-macro" in ran[1]


def test_backing_out_of_the_output_question_is_not_a_choice_of_directory(workspace: Path) -> None:
    ran: List[List[str]] = []
    out = io.StringIO()
    run_interactive(
        ran.append,
        read=keys(
            ENTER,  # stage: cpg
            DOWN,
            DOWN,
            ENTER,
            ENTER,  # input: into corpus/, then use it
            QUIT,  # output: back out
        ),
        out=out,
        root=workspace,
    )
    assert ran == []
    assert "Output directory" not in out.getvalue()


def test_run_interactive_runs_nothing_when_backed_out(workspace: Path) -> None:
    ran: List[List[str]] = []
    assert run_interactive(ran.append, read=keys(QUIT), out=io.StringIO(), root=workspace) == 0
    assert ran == []


def test_run_interactive_can_start_over(workspace: Path) -> None:
    ran: List[List[str]] = []
    run_interactive(
        ran.append,
        read=keys(
            ENTER,  # stage: cpg
            DOWN,
            DOWN,
            ENTER,
            ENTER,  # input: into corpus/, then use it
            ENTER,  # output: the default
            ENTER,  # workers: 1
            DOWN,
            ENTER,  # start over
            QUIT,  # and quit out of the stage menu
        ),
        out=io.StringIO(),
        root=workspace,
    )
    assert ran == []
