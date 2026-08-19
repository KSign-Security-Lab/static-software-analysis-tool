"""The SEC-bench sweep: its configuration, its dataset, and what it must not leak.

No network and no Docker. The parts of this that need either are the parts that
cannot be asserted in a test suite anyway; what can be pinned here is the shape
of the data, the resolution of the settings, and the one guard the whole
exercise rests on -- that the reference patch never reaches the agent.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent.bench import dataset as ds
from agent.bench.config import BenchConfig

# One real record, trimmed. The stack trace is verbatim from
# `njs.cve-2022-32414`, because the path-mangling it exercises -- an absolute
# path from the machine that produced the report -- is the whole reason
# `candidate_paths` exists.
RECORD = {
    "instance_id": "njs.cve-2022-32414",
    "repo": "nginx/njs",
    "project_name": "njs",
    "lang": "c++",
    "work_dir": "/src/njs",
    "sanitizer": "address",
    "bug_description": "a segmentation violation in njs_vmcode_interpreter",
    "base_commit": "f65981b0b8fcf02d69a40bc934803c25c9f607ab",
    "build_sh": "#!/bin/bash -eu\nmake",
    "secb_sh": "#!/bin/bash\nbuild() { :; }",
    "dockerfile": "FROM hwiwonlee/secb.base:latest",
    "patch": "diff --git a/src/njs_promise.c b/src/njs_promise.c\n-bad\n+good\n",
    "exit_code": 0,
    "sanitizer_report": (
        "==732128==ERROR: AddressSanitizer: SEGV on unknown address\n"
        "    #0 0x4e3e53 in njs_vmcode_interpreter "
        "/home/q1iq/Documents/origin/njs_f65981b/src/njs_vmcode.c:802:27\n"
        "    #1 0x6050bc in njs_await_fulfilled "
        "/home/q1iq/Documents/origin/njs_f65981b/src/njs_async.c:96:11\n"
        "    #2 0x53c9ec in njs_function_native_call "
        "/home/q1iq/Documents/origin/njs_f65981b/src/njs_function.c:739:11\n"
        "    #3 0x7f2c in __libc_start_main /build/glibc/csu/libc-start.c:342\n"
    ),
    "bug_report": "================= Bug Report (1/1) ==================",
}


@pytest.fixture()
def instance() -> ds.Instance:
    return ds.Instance.from_record(RECORD)


# -- the guard that matters --------------------------------------------------


def test_the_reference_patch_never_reaches_the_agent(instance: ds.Instance) -> None:
    """The strongest guard this sweep has against a meaningless number.

    Showing the agent the files the reference patch touches would be telling it
    where the bug is and then scoring it on finding the bug. `for_agent` is a
    separate shape rather than the record with a field removed, because a
    subtraction is easy to forget to repeat and this cannot leak by omission.
    """
    payload = instance.for_agent()

    assert "patch" not in payload
    body = json.dumps(payload, ensure_ascii=False)
    assert "njs_promise.c" not in body, "the patched file's name is a location hint"
    assert instance.patch not in body


def test_what_the_agent_does_get_is_what_a_triager_gets(instance: ds.Instance) -> None:
    """The CVE text and the crash, which is what actually lands in an inbox."""
    payload = instance.for_agent()
    assert payload["bug_description"]
    assert "AddressSanitizer" in payload["sanitizer_report"]


# -- reading the crash -------------------------------------------------------


def test_frames_are_parsed_innermost_first(instance: ds.Instance) -> None:
    """`frames` is the backtrace as written -- every source frame, ours or not."""
    frames = instance.frames()
    assert [f.depth for f in frames] == [0, 1, 2, 3]
    assert frames[0].function == "njs_vmcode_interpreter"
    assert frames[0].line == 802


def test_frames_outside_the_project_are_dropped(instance: ds.Instance) -> None:
    """A backtrace runs off the end of the project into libc.

    `/build/glibc/csu/libc-start.c` is a `.c` file by every test except the one
    that matters: it is not in the image, and indexing it would spend a run
    reading somebody else's code.
    """
    assert any("glibc" in f.path for f in instance.frames()), "the fixture should contain one"
    assert all("glibc" not in f.path for f in instance.project_frames())


def test_a_report_with_no_recognisable_project_keeps_every_frame() -> None:
    """A narrowing rule that matches nothing should widen, not return an empty
    backtrace -- some reports were produced against a differently laid-out tree."""
    odd = ds.Instance.from_record({**RECORD, "project_name": "somethingelse"})
    assert len(odd.project_frames()) == len(odd.frames())


def test_the_crash_file_comes_first(instance: ds.Instance) -> None:
    """Ordered innermost first, so the file the sanitizer blamed is the first
    thing the agent is shown."""
    assert instance.crash_paths(depth=0) == ["src/njs_vmcode.c"]
    assert instance.crash_paths(depth=1) == ["src/njs_vmcode.c", "src/njs_async.c"]


def test_an_absolute_path_from_another_machine_becomes_repo_relative() -> None:
    """The report was produced somewhere else. Nothing in the record maps its
    paths to the container's, so the project name is the seam."""
    assert ds.candidate_paths("/home/q1iq/origin/njs_f65981b/src/njs_vmcode.c", "njs") == ["src/njs_vmcode.c"]
    assert ds.candidate_paths("/build/njs/src/x.c", "njs") == ["src/x.c"]


def test_a_path_with_no_project_marker_offers_suffixes_longest_first() -> None:
    """Shortest-first would resolve `src/utils.c` and `test/utils.c` to whichever
    the filesystem answered with."""
    found = ds.candidate_paths("/a/b/c/d/utils.c", "nothing")
    assert found[0].count("/") >= found[-1].count("/")
    assert found[-1] == "utils.c"


# -- configuration -----------------------------------------------------------


def test_defaults_are_repo_relative_so_a_checkout_runs_unconfigured(monkeypatch) -> None:
    """Nothing committed names a machine. `.env` is where a machine says where
    its space is."""
    for name in ("SECB_ROOT", "SECB_SPLIT", "SECB_LIMIT", "SECB_PRUNE"):
        monkeypatch.delenv(name, raising=False)

    config = BenchConfig()
    assert config.root.is_absolute()
    assert "artifacts" in config.root.parts and config.root.name == "secbench"
    assert config.split == "cve"
    assert config.prune_after is True


def test_every_knob_has_an_environment_override(monkeypatch) -> None:
    monkeypatch.setenv("SECB_ROOT", "/tmp/sweep")
    monkeypatch.setenv("SECB_SPLIT", "oss")
    monkeypatch.setenv("SECB_LIMIT", "7")
    monkeypatch.setenv("SECB_PRUNE", "0")
    monkeypatch.setenv("SECB_INSTANCES", "a.cve-1, b.cve-2")

    config = BenchConfig()
    assert config.root == Path("/tmp/sweep")
    assert config.split == "oss"
    assert config.limit == 7
    assert config.prune_after is False
    assert config.instances == ("a.cve-1", "b.cve-2")


def test_a_typo_falls_back_rather_than_refusing_to_start(monkeypatch) -> None:
    """This is read wherever the sweep is imported. A misspelled split should
    run the default and be visible in `status`, not stop the CLI."""
    monkeypatch.setenv("SECB_SPLIT", "cvee")
    monkeypatch.setenv("SECB_CONTEXT", "magic")

    config = BenchConfig()
    assert config.split == "cve"
    assert config.context == "sanitizer"


def test_the_sweep_never_defaults_to_the_host_daemon() -> None:
    """A sweep that fell back to the host socket would put two hundred gigabytes
    of somebody else's images on the machine's system disk, which is the one
    failure this arrangement exists to prevent."""
    monkeypatched = BenchConfig()
    assert "/var/run/docker.sock" not in monkeypatched.docker_host
    assert monkeypatched.docker_env()["DOCKER_HOST"] == monkeypatched.docker_host


def test_every_path_hangs_off_root(monkeypatch) -> None:
    """So deleting one directory undoes a sweep and nothing is left behind."""
    monkeypatch.setenv("SECB_ROOT", "/tmp/sweep")
    config = BenchConfig()
    for path in (config.data_dir, config.dataset_file, config.runs_dir, config.predictions_file, config.results_dir):
        assert str(path).startswith("/tmp/sweep")


# -- selection ---------------------------------------------------------------


def _many(count: int) -> list[ds.Instance]:
    return [ds.Instance.from_record({**RECORD, "instance_id": f"p.cve-{n}"}) for n in range(count)]


def test_a_limit_takes_the_head(monkeypatch) -> None:
    monkeypatch.setenv("SECB_LIMIT", "3")
    chosen = ds.select(_many(10), BenchConfig())
    assert [i.instance_id for i in chosen] == ["p.cve-0", "p.cve-1", "p.cve-2"]


def test_named_instances_are_taken_in_the_order_asked_for(monkeypatch) -> None:
    monkeypatch.setenv("SECB_INSTANCES", "p.cve-4,p.cve-1")
    chosen = ds.select(_many(10), BenchConfig())
    assert [i.instance_id for i in chosen] == ["p.cve-4", "p.cve-1"]


def test_an_unknown_instance_is_an_error_not_an_empty_sweep(monkeypatch) -> None:
    """A typo would otherwise look exactly like a benchmark with nothing to run,
    which is the kind of quiet nothing that wastes an afternoon."""
    monkeypatch.setenv("SECB_INSTANCES", "p.cve-1,nope.cve-9")
    with pytest.raises(KeyError, match="nope.cve-9"):
        ds.select(_many(3), BenchConfig())


def test_loading_without_fetching_says_so(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SECB_ROOT", str(tmp_path))
    with pytest.raises(FileNotFoundError, match="agent bench fetch"):
        ds.load(BenchConfig())


# -- producing a patch -------------------------------------------------------


def test_a_replacement_becomes_a_diff_the_evaluator_can_apply() -> None:
    """Our agent works in line replacements, which is what an editor wants.
    Every benchmark in this space speaks diffs, so the translation happens once."""
    from agent.remediate import splice, unified_diff
    from agent.schema import Span

    before = "int main(void) {\n    char b[8];\n    strcpy(b, x);\n    return 0;\n}\n"
    span = Span(file="m.c", start_line=3, end_line=3, start_column=0, end_column=1, excerpt="    strcpy(b, x);")
    after = splice(before, span, "    strncpy(b, x, sizeof(b) - 1);")
    diff = unified_diff("m.c", before, after)

    assert diff.startswith("--- a/m.c\n+++ b/m.c\n")
    assert "-    strcpy(b, x);" in diff
    assert "+    strncpy(b, x, sizeof(b) - 1);" in diff


def test_a_file_that_moved_is_refused_rather_than_corrupted() -> None:
    """The excerpt was read when the finding was made. A mismatch means the file
    changed, and applying to that is applying to code nobody looked at."""
    from agent.remediate import Stale, splice
    from agent.schema import Span

    span = Span(file="m.c", start_line=1, end_line=1, start_column=0, end_column=1, excerpt="something else")
    with pytest.raises(Stale):
        splice("int x;\n", span, "int y;")


def test_predictions_are_written_in_the_shape_their_evaluator_reads(tmp_path: Path, monkeypatch) -> None:
    """SWE-agent's format, because it is the simplest of the four they accept
    and needs no change upstream. Pinned here so a drift is a failing test."""
    monkeypatch.setenv("SECB_ROOT", str(tmp_path))
    from agent.bench.runner import Attempt, write_predictions

    config = BenchConfig()
    write_predictions(
        [Attempt(instance_id="a.cve-1", patch="diff --git a/x b/x\n"), Attempt(instance_id="b.cve-2")],
        config,
    )
    payload = json.loads(config.predictions_file.read_text())

    assert payload["a.cve-1"]["model_patch"] == "diff --git a/x b/x\n"
    # Written with an empty patch rather than dropped: their evaluator counts it
    # unresolved, which it is, and omitting it would shrink the denominator.
    assert payload["b.cve-2"]["model_patch"] == ""


def test_an_instance_that_produced_nothing_is_still_scored(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SECB_ROOT", str(tmp_path))
    from agent.bench.runner import Attempt
    from agent.bench.score import outcome_for

    outcome, note = outcome_for(Attempt(instance_id="a.cve-1"), None)
    assert outcome == "not_located"
    assert note


def test_the_runner_owns_the_early_stages_and_the_evaluator_the_late_ones() -> None:
    """The honest division: only the runner knows whether the agent found
    anything, and only a build knows whether the patch works."""
    from agent.bench.runner import Attempt
    from agent.bench.score import outcome_for

    patched = Attempt(instance_id="a.cve-1", patch="diff --git a/x b/x\n")
    assert outcome_for(patched, {"resolved": True})[0] == "solved"
    assert outcome_for(patched, {"resolved": False, "stage": "build_failed"})[0] == "patch_build_failed"
    assert outcome_for(patched, {"resolved": False, "reason": "tests_failed"})[0] == "fixed_tests_broke"
    # Scored, not resolved, and their report did not say how. The note carries
    # what they actually said, so nobody has to trust the guess.
    outcome, note = outcome_for(patched, {"resolved": False})
    assert outcome == "built_not_fixed" and note


def test_an_unscored_instance_is_not_a_failure() -> None:
    """`not_run` and `not_located` are different facts and the page groups them
    apart -- one is work remaining, the other is a result."""
    from agent.bench.runner import Attempt
    from agent.bench.score import outcome_for

    assert outcome_for(Attempt(instance_id="a", patch="diff"), None)[0] == "not_run"


def test_the_sweep_is_never_imported_by_the_request_path() -> None:
    """Same rule the tuner follows. A benchmark reachable from a request is one
    you will iterate against, and the moment we tune against a held-out set it
    stops measuring us."""
    from pathlib import Path as P

    import agent

    package = P(agent.__file__).parent
    for name in ("graph/build.py", "graph/nodes.py", "graph/session.py", "llm.py", "mcp/server.py"):
        source = (package / name).read_text(encoding="utf-8")
        assert "bench" not in source.replace("benchmark", ""), f"{name} reaches the sweep"
