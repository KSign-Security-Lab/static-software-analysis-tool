from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent.bench import dataset as ds
from agent.bench.config import BenchConfig

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


def test_the_reference_patch_never_reaches_the_agent(instance: ds.Instance) -> None:
    payload = instance.for_agent()

    assert "patch" not in payload
    body = json.dumps(payload, ensure_ascii=False)
    assert "njs_promise.c" not in body, "the patched file's name is a location hint"
    assert instance.patch not in body


def test_what_the_agent_does_get_is_what_a_triager_gets(instance: ds.Instance) -> None:
    payload = instance.for_agent()
    assert payload["bug_description"]
    assert "AddressSanitizer" in payload["sanitizer_report"]


def test_frames_are_parsed_innermost_first(instance: ds.Instance) -> None:
    frames = instance.frames()
    assert [f.depth for f in frames] == [0, 1, 2, 3]
    assert frames[0].function == "njs_vmcode_interpreter"
    assert frames[0].line == 802


def test_frames_outside_the_project_are_dropped(instance: ds.Instance) -> None:
    assert any("glibc" in f.path for f in instance.frames()), "the fixture should contain one"
    assert all("glibc" not in f.path for f in instance.project_frames())


def test_a_report_with_no_recognisable_project_keeps_every_frame_but_the_foreign_ones() -> None:
    odd = ds.Instance.from_record({**RECORD, "project_name": "somethingelse"})
    kept = odd.project_frames()
    assert len(kept) == len(odd.frames()) - 1, "only glibc dropped"
    assert all("glibc" not in f.path for f in kept)


def test_the_crash_file_comes_first(instance: ds.Instance) -> None:
    assert instance.crash_paths(depth=0) == ["src/njs_vmcode.c"]
    assert instance.crash_paths(depth=1) == ["src/njs_vmcode.c", "src/njs_async.c"]


def test_an_absolute_path_from_another_machine_becomes_repo_relative() -> None:
    assert ds.candidate_paths("/home/q1iq/origin/njs_f65981b/src/njs_vmcode.c", "njs") == ["src/njs_vmcode.c"]
    assert ds.candidate_paths("/build/njs/src/x.c", "njs") == ["src/x.c"]


def test_a_checkout_inside_a_directory_of_the_same_name() -> None:
    found = ds.candidate_paths("/home/fuzz/gpac/gpac/applications/mp4box/mp4box.c", "gpac")
    assert "applications/mp4box/mp4box.c" in found
    assert found[0].count("/") >= found[-1].count("/"), "longest first"


def test_a_path_relative_to_the_build_directory_loses_its_dots() -> None:
    assert ds.candidate_paths("../../programs/escape.c", "libredwg")[0] == "programs/escape.c"


def test_the_c_library_is_not_the_project_even_when_nothing_else_matches() -> None:
    odd = ds.Instance.from_record(
        {
            **RECORD,
            "project_name": "nomatch",
            "sanitizer_report": (
                "    #0 0x1 in __strcpy /usr/include/x86_64-linux-gnu/bits/string_fortified.h:128\n"
                "    #1 0x2 in main ../../programs/escape.c:46\n"
            ),
        }
    )
    assert [f.path for f in odd.project_frames()] == ["../../programs/escape.c"]


def test_a_path_with_no_project_marker_offers_suffixes_longest_first() -> None:
    found = ds.candidate_paths("/a/b/c/d/utils.c", "nothing")
    assert found[0].count("/") >= found[-1].count("/")
    assert found[-1] == "utils.c"


def test_defaults_are_repo_relative_so_a_checkout_runs_unconfigured(monkeypatch) -> None:
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
    monkeypatch.setenv("SECB_SPLIT", "cvee")
    monkeypatch.setenv("SECB_CONTEXT", "magic")

    config = BenchConfig()
    assert config.split == "cve"
    assert config.context == "sanitizer"


def test_the_sweep_never_defaults_to_the_host_daemon() -> None:
    monkeypatched = BenchConfig()
    assert "/var/run/docker.sock" not in monkeypatched.docker_host
    assert monkeypatched.docker_env()["DOCKER_HOST"] == monkeypatched.docker_host


def test_every_path_hangs_off_root(monkeypatch) -> None:
    monkeypatch.setenv("SECB_ROOT", "/tmp/sweep")
    config = BenchConfig()
    for path in (config.data_dir, config.dataset_file, config.runs_dir, config.predictions_file, config.results_dir):
        assert str(path).startswith("/tmp/sweep")


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
    monkeypatch.setenv("SECB_INSTANCES", "p.cve-1,nope.cve-9")
    with pytest.raises(KeyError, match="nope.cve-9"):
        ds.select(_many(3), BenchConfig())


def test_loading_without_fetching_says_so(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SECB_ROOT", str(tmp_path))
    with pytest.raises(FileNotFoundError, match="agent bench fetch"):
        ds.load(BenchConfig())


def test_a_replacement_becomes_a_diff_the_evaluator_can_apply() -> None:
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
    from agent.remediate import Stale, splice
    from agent.schema import Span

    span = Span(file="m.c", start_line=1, end_line=1, start_column=0, end_column=1, excerpt="something else")
    with pytest.raises(Stale):
        splice("int x;\n", span, "int y;")


def test_predictions_are_written_in_the_shape_their_evaluator_reads(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SECB_ROOT", str(tmp_path))
    from agent.bench.runner import Attempt, write_predictions

    config = BenchConfig()
    write_predictions(
        [Attempt(instance_id="a.cve-1", patch="diff --git a/x b/x\n"), Attempt(instance_id="b.cve-2")],
        config,
    )
    payload = json.loads(config.predictions_file.read_text())

    assert payload["a.cve-1"]["model_patch"] == "diff --git a/x b/x\n"
    assert payload["b.cve-2"]["model_patch"] == ""


def test_an_instance_that_produced_nothing_is_still_scored(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SECB_ROOT", str(tmp_path))
    from agent.bench.runner import Attempt
    from agent.bench.score import outcome_for

    outcome, note = outcome_for(Attempt(instance_id="a.cve-1"), None)
    assert outcome == "not_located"
    assert note


def test_the_runner_owns_the_early_stages_and_the_evaluator_the_late_ones() -> None:
    from agent.bench.runner import Attempt
    from agent.bench.score import outcome_for

    patched = Attempt(instance_id="a.cve-1", patch="diff --git a/x b/x\n")
    assert outcome_for(patched, {"resolved": True})[0] == "solved"
    assert outcome_for(patched, {"resolved": False, "stage": "build_failed"})[0] == "patch_build_failed"
    assert outcome_for(patched, {"resolved": False, "reason": "tests_failed"})[0] == "fixed_tests_broke"
    outcome, note = outcome_for(patched, {"resolved": False})
    assert outcome == "built_not_fixed" and note


def test_an_unscored_instance_is_not_a_failure() -> None:
    from agent.bench.runner import Attempt
    from agent.bench.score import outcome_for

    assert outcome_for(Attempt(instance_id="a", patch="diff"), None)[0] == "awaiting_score"
    assert outcome_for(Attempt(instance_id="a", patch=""), None)[0] == "not_located"
    assert outcome_for(Attempt(instance_id="a", patch="diff"), {"resolved": True})[0] == "solved"


def test_the_sweep_is_never_imported_by_the_request_path() -> None:
    from pathlib import Path as P

    import agent

    package = P(agent.__file__).parent
    for name in ("graph/build.py", "graph/nodes.py", "graph/session.py", "llm.py", "mcp/server.py"):
        source = (package / name).read_text(encoding="utf-8")
        assert "bench" not in source.replace("benchmark", ""), f"{name} reaches the sweep"


def test_a_sweep_resumes_rather_than_starting_over(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SECB_ROOT", str(tmp_path))
    from agent.bench import runner as bench_runner
    from agent.bench.runner import Attempt, sweep

    config = BenchConfig()
    bench_runner._write_attempt(Attempt(instance_id="p.cve-0", patch="diff --git a/x b/x\n"), config)

    ran: list[str] = []
    monkeypatch.setattr(bench_runner, "prepare", lambda instance, _c: ran.append(instance.instance_id) or True)
    monkeypatch.setattr(bench_runner, "run_one", lambda instance, _c: Attempt(instance_id=instance.instance_id))

    instances = [ds.Instance.from_record({**RECORD, "instance_id": f"p.cve-{n}"}) for n in range(3)]
    attempts = sweep(instances, config)

    assert ran == ["p.cve-1", "p.cve-2"], "the finished instance must not be touched again"
    assert len(attempts) == 3, "and it must still be in the result"
    assert attempts[0].patch, "carried forward with what it produced"


def test_asking_for_the_work_again_is_possible(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SECB_ROOT", str(tmp_path))
    from agent.bench import runner as bench_runner
    from agent.bench.runner import Attempt, sweep

    config = BenchConfig()
    bench_runner._write_attempt(Attempt(instance_id="p.cve-0"), config)

    ran: list[str] = []
    monkeypatch.setattr(bench_runner, "prepare", lambda instance, _c: ran.append(instance.instance_id) or True)
    monkeypatch.setattr(bench_runner, "run_one", lambda instance, _c: Attempt(instance_id=instance.instance_id))

    sweep([ds.Instance.from_record({**RECORD, "instance_id": "p.cve-0"})], config, resume=False)
    assert ran == ["p.cve-0"]


def test_the_image_reference_is_the_one_their_evaluator_builds() -> None:
    config = BenchConfig()
    reference = config.image_for("njs.cve-2022-32414")

    assert reference.endswith(":patch")
    assert reference == f"{config.image_prefix}njs.cve-2022-32414:patch"


def test_the_track_is_a_setting_not_a_rewrite(monkeypatch) -> None:
    monkeypatch.setenv("SECB_IMAGE_TAG", "poc")
    assert BenchConfig().image_for("a.cve-1").endswith(":poc")


def test_an_instance_is_scored_before_its_image_is_removed(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SECB_ROOT", str(tmp_path))
    from agent.bench import runner as bench_runner
    from agent.bench.runner import Attempt, sweep

    calls: list[str] = []

    monkeypatch.setattr(bench_runner, "prepare", lambda i, _c: calls.append(f"pull:{i.instance_id}") or True)
    monkeypatch.setattr(
        bench_runner, "run_one", lambda i, _c: Attempt(instance_id=i.instance_id, patch="diff --git a/x b/x\n")
    )
    monkeypatch.setattr(
        bench_runner, "_score_now", lambda a, _c: calls.append(f"score:{a.instance_id}") or {"resolved": True}
    )

    class Listed:
        returncode = 0
        stdout = ""
        stderr = ""

    monkeypatch.setattr(
        bench_runner,
        "_docker",
        lambda _c, *args, **kw: (calls.append(f"{args[0]}:{args[-1].split(':')[0]}"), Listed())[1],
    )

    sweep([ds.Instance.from_record({**RECORD, "instance_id": "a.cve-1"})], BenchConfig())

    assert calls.index("score:a.cve-1") < calls.index("rmi:hwiwonlee/secb.eval.x86_64.a.cve-1"), (
        "the image must still be there when the evaluator wants it"
    )


def test_the_verdict_is_kept_with_the_attempt(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SECB_ROOT", str(tmp_path))
    from agent.bench import runner as bench_runner
    from agent.bench.runner import Attempt, load_attempts

    config = BenchConfig()
    bench_runner._write_attempt(
        Attempt(instance_id="a.cve-1", patch="diff", verdict={"resolved": True}), config
    )
    assert load_attempts(config)[0].verdict == {"resolved": True}


def test_an_unpatched_instance_costs_no_container(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SECB_ROOT", str(tmp_path))
    from agent.bench.runner import Attempt
    from agent.bench.score import score_one

    assert score_one(Attempt(instance_id="a.cve-1", patch=""), BenchConfig()) is None


def test_an_instance_takes_its_leavings_with_it(monkeypatch) -> None:
    from agent.bench import runner

    calls: list[tuple] = []

    class Result:
        returncode = 0
        stdout = "hwiwonlee/secb.eval.x86_64.njs.cve-1:patch\nsecb.eval.njs.cve-1.built:latest\n"
        stderr = ""

    monkeypatch.setattr(runner, "_docker", lambda config, *argv, **kw: (calls.append(argv), Result())[1])
    runner._prune("njs.cve-1", BenchConfig())

    removed = [argv[2] for argv in calls if argv[0] == "rmi"]
    assert "hwiwonlee/secb.eval.x86_64.njs.cve-1:patch" in removed, "ours, by name"
    assert "secb.eval.njs.cve-1.built:latest" in removed, "theirs, by search"
    assert ("image", "prune", "-f") in calls, "dangling layers"
    assert ("image", "prune", "-af") not in calls, "-a would take the shared base too"


def test_a_relative_root_means_the_checkout_not_the_working_directory(monkeypatch) -> None:
    from agent.config import repo_root

    repo = repo_root()
    monkeypatch.setenv("SECB_ROOT", "./artifacts/secbench")
    monkeypatch.chdir(repo / "docs")

    assert BenchConfig().root == repo / "artifacts" / "secbench"


def test_the_env_file_never_overrides_the_environment(monkeypatch) -> None:
    import os

    from agent.bench.config import load_env

    monkeypatch.setattr(os, "environ", dict(os.environ))
    env_file = Path(__file__).parent / "fixtures" / "sweep.env"
    env_file.write_text('# a comment\nSECB_SPLIT=oss\nSECB_LIMIT=7\nSECB_QUOTED="a"\n', encoding="utf-8")
    os.environ["SECB_SPLIT"] = "cve"
    os.environ.pop("SECB_LIMIT", None)
    try:
        load_env(env_file)
    finally:
        env_file.unlink()

    assert os.environ["SECB_SPLIT"] == "cve"
    assert os.environ["SECB_LIMIT"] == "7"
    assert os.environ["SECB_QUOTED"] == "a"


def test_a_missing_env_file_is_not_an_error(tmp_path: Path) -> None:
    from agent.bench.config import load_env

    load_env(tmp_path / "nothing-here")


def test_the_log_carries_what_the_terminal_showed(tmp_path: Path, capfd) -> None:
    import subprocess
    import sys

    from agent.bench.sweep import _also_log

    log = tmp_path / "sweep.log"
    with capfd.disabled():
        with _also_log(log):
            print("a line of our own")
            subprocess.run([sys.executable, "-c", "print('a line of docker\\'s')"], check=True)
        print("after the sweep, terminal only")

    assert log.read_text(encoding="utf-8").splitlines() == ["a line of our own", "a line of docker's"]


def test_a_failed_precondition_spends_nothing(tmp_path: Path, monkeypatch) -> None:
    from agent.bench import sweep as sweep_module

    monkeypatch.setenv("SECB_ROOT", str(tmp_path))
    monkeypatch.setattr(sweep_module, "_preflight", lambda config: False)
    ran: list[str] = []
    code = sweep_module.sweep(BenchConfig(), lambda action: ran.append(action) or 0)

    assert code == 1
    assert ran == []


def test_a_failed_fetch_never_reaches_the_expensive_phase(tmp_path: Path, monkeypatch) -> None:
    from agent.bench import sweep as sweep_module

    monkeypatch.setenv("SECB_ROOT", str(tmp_path))
    monkeypatch.setattr(sweep_module, "_preflight", lambda config: True)
    ran: list[str] = []

    def action(name: str) -> int:
        ran.append(name)
        return 1 if name == "fetch" else 0

    assert sweep_module.sweep(BenchConfig(), action) == 1
    assert "run" not in ran and "score" not in ran


def test_the_phases_are_the_bench_actions_themselves(tmp_path: Path, monkeypatch) -> None:
    from agent.bench import sweep as sweep_module

    monkeypatch.setenv("SECB_ROOT", str(tmp_path))
    monkeypatch.setattr(sweep_module, "_preflight", lambda config: True)
    monkeypatch.setattr(sweep_module, "_compose", lambda *a, **kw: _Compose())
    ran: list[str] = []

    assert sweep_module.sweep(BenchConfig(), lambda action: ran.append(action) or 0) == 0
    assert ran == ["status", "fetch", "run", "score", "status"]


class _Compose:
    returncode = 0
    stdout = ""
    stderr = ""
