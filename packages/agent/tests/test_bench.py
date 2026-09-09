from __future__ import annotations

import pytest

from api import bench


def _instance(**over):
    base = {"id": "x.c", "outcome": "solved", "config_hash": "cfg", "run_id": "r1"}
    return bench.Instance(**{**base, **over})


def test_the_two_kinds_are_never_worded_the_same() -> None:
    labels = {d.kind: d.score_label for d in bench.DATASETS}
    assert labels["held_out"] != labels["pinned"]
    assert {d.kind for d in bench.DATASETS} == {"held_out", "pinned"}


def test_nothing_computes_across_datasets() -> None:
    import inspect

    params = list(inspect.signature(bench._score).parameters)
    assert params == ["dataset", "instances"]


def test_a_dataset_declares_which_stages_it_can_reach() -> None:
    corpus = bench._BY_ID["corpus"]
    assert "patch_build_failed" not in corpus.stages
    assert "false_flagged" in corpus.stages

    sec = bench._BY_ID["sec-bench"]
    assert "patch_build_failed" in sec.stages
    assert "false_flagged" not in sec.stages


def test_a_score_without_a_config_hash_is_unavailable() -> None:
    corpus = bench._BY_ID["corpus"]
    score = bench._score(corpus, [_instance(config_hash=None), _instance(id="y.c", config_hash=None)])

    assert score.available is False
    assert score.value is None
    assert "설정 해시" in score.unavailable_reason


def test_a_score_with_mixed_configs_is_unavailable() -> None:
    corpus = bench._BY_ID["corpus"]
    score = bench._score(corpus, [_instance(config_hash="a"), _instance(id="y.c", config_hash="b")])

    assert score.available is False
    assert "설정이 2가지" in score.unavailable_reason


def test_a_score_with_nothing_run_is_unavailable() -> None:
    corpus = bench._BY_ID["corpus"]
    score = bench._score(corpus, [_instance(outcome="not_run"), _instance(id="y.c", outcome="not_run")])

    assert score.available is False
    assert "아직" in score.unavailable_reason


def test_a_score_whose_config_has_no_model_is_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(bench, "_model_for", lambda _hash: None)
    corpus = bench._BY_ID["corpus"]
    score = bench._score(corpus, [_instance()])

    assert score.available is False
    assert "모델" in score.unavailable_reason


def test_every_refusal_says_why() -> None:
    corpus = bench._BY_ID["corpus"]
    for instances in ([], [_instance(outcome="not_run")], [_instance(config_hash=None)]):
        score = bench._score(corpus, instances)
        assert score.available is False
        assert score.unavailable_reason, "an unavailable score must name what is missing"


def test_a_score_renders_when_all_three_are_there(monkeypatch) -> None:
    monkeypatch.setattr(bench, "_model_for", lambda _hash: "a-model")
    corpus = bench._BY_ID["corpus"]
    score = bench._score(corpus, [_instance(), _instance(id="y.c", outcome="misread")])

    assert score.available is True
    assert score.value == 0.5
    assert score.model == "a-model" and score.config_hash == "cfg"


def test_contaminated_instances_leave_the_score_and_not_the_list(monkeypatch) -> None:
    monkeypatch.setattr(bench, "_model_for", lambda _hash: "a-model")
    corpus = bench._BY_ID["corpus"]
    instances = [_instance(), _instance(id="y.c", contaminated=True, outcome="misread")]
    score = bench._score(corpus, instances)

    assert score.excluded == 1
    assert score.scored == 1
    assert score.value == 1.0
    assert len(instances) == 2, "the contaminated one is still in the list"


def test_everything_contaminated_is_unavailable_rather_than_perfect() -> None:
    corpus = bench._BY_ID["corpus"]
    score = bench._score(corpus, [_instance(contaminated=True)])

    assert score.available is False
    assert score.excluded == 1


def test_a_subdirectory_run_still_matches_its_instances() -> None:
    corpus_paths = {"CWE-121_stack/copy_bad.c", "CWE-78_cmd/exec_bad.c"}
    assert bench._match("copy_bad.c", corpus_paths) == "CWE-121_stack/copy_bad.c"
    assert bench._match("CWE-78_cmd/exec_bad.c", corpus_paths) == "CWE-78_cmd/exec_bad.c"


def test_an_ambiguous_path_is_refused_rather_than_guessed() -> None:
    corpus_paths = {"CWE-121_stack/copy_bad.c", "CWE-122_heap/copy_bad.c"}
    assert bench._match("copy_bad.c", corpus_paths) is None


def test_a_path_that_is_not_corpus_matches_nothing() -> None:
    assert bench._match("src/main.c", {"CWE-121_stack/copy_bad.c"}) is None


def _corpus_root():
    from pathlib import Path

    root = Path(__file__).resolve().parents[3] / "corpus"
    if not root.is_dir():
        pytest.skip("the seed corpus is not checked out")
    return root


def test_the_declared_total_matches_the_corpus_on_disk() -> None:
    root = _corpus_root()
    files = [p for p in root.rglob("*.c") if "scraped" not in p.parts]
    assert len(files) == bench._BY_ID["corpus"].total


def test_an_instance_is_a_file_not_a_function() -> None:
    from agent.rag import corpus as corpus_module

    samples, _ = corpus_module.read(_corpus_root())
    by_file = {sample.file for sample in samples}

    assert len(by_file) == bench._BY_ID["corpus"].total
    assert len(samples) >= len(by_file)


def test_an_empty_dataset_says_what_to_run() -> None:
    for dataset in bench.DATASETS:
        assert dataset.how_to_run, f"{dataset.id} has no instructions for when it is empty"


def test_the_excluded_track_is_shown_as_a_decision() -> None:
    sec = bench._BY_ID["sec-bench"]
    assert sec.excluded_tracks
    assert "PoC" in sec.excluded_tracks[0]["track"]
    assert sec.excluded_tracks[0]["reason"]


def test_no_baseline_ships_as_a_number_without_its_model_and_source() -> None:
    for dataset in bench.DATASETS:
        for baseline in dataset.baselines:
            if baseline.resolved is not None:
                assert baseline.model and baseline.source, f"{baseline.name} has a figure but no provenance"


def test_a_sibling_cwe_is_the_same_weakness() -> None:
    assert bench.same_family("CWE-121", "CWE-120")
    assert bench.same_family("CWE-121", "CWE-119")
    assert bench.same_family("CWE-787", "CWE-125")


def test_a_different_weakness_is_still_wrong() -> None:
    assert not bench.same_family("CWE-121", "CWE-78")
    assert not bench.same_family("CWE-78", "CWE-22")
    assert not bench.same_family("CWE-416", "CWE-401")


def test_every_corpus_cwe_is_in_a_family() -> None:
    covered = {cwe for family in bench.CWE_FAMILIES for cwe in family}
    root = _corpus_root()
    labels = {p.name.split("_")[0] for p in root.iterdir() if p.is_dir() and p.name.startswith("CWE-")}
    assert labels <= covered, f"no family for {sorted(labels - covered)}"


def test_exact_and_family_are_reported_apart(monkeypatch) -> None:
    monkeypatch.setattr(bench, "_model_for", lambda _hash: "a-model")
    corpus = bench._BY_ID["corpus"]
    score = bench._score(
        corpus,
        [_instance(matched="exact"), _instance(id="y.c", matched="family")],
    )
    assert score.solved == 2
    assert score.exact == 1


def test_the_run_is_detached_from_the_api_that_started_it(tmp_path, monkeypatch) -> None:
    from api import sweep

    monkeypatch.setattr(sweep, "_paths", lambda: (tmp_path / "p", tmp_path / "l", tmp_path / "b"))
    seen: dict = {}

    class Fake:
        pid = 4242

    def fake_popen(argv, **kwargs):
        seen.update(kwargs)
        return Fake()

    monkeypatch.setattr(sweep.subprocess, "Popen", fake_popen)
    sweep.start()

    assert seen["start_new_session"] is True


def test_the_log_is_not_written_twice(tmp_path, monkeypatch) -> None:
    import subprocess as sp

    from api import sweep

    monkeypatch.setattr(sweep, "_paths", lambda: (tmp_path / "p", tmp_path / "l", tmp_path / "b"))
    seen: dict = {}

    class Fake:
        pid = 4243

    monkeypatch.setattr(sweep.subprocess, "Popen", lambda argv, **kw: (seen.update(kw), Fake())[1])
    sweep.start()

    assert seen["stdout"] is sp.DEVNULL
    assert seen["stderr"] is not sp.DEVNULL


def test_a_stale_pidfile_does_not_report_a_running_sweep(tmp_path, monkeypatch) -> None:
    from api import sweep

    monkeypatch.setattr(sweep, "_paths", lambda: (tmp_path / "p", tmp_path / "l", tmp_path / "b"))
    (tmp_path / "p").write_text('{"pid": %d, "started_at": 1}' % __import__("os").getpid())

    assert sweep.status()["running"] is False


def test_the_panel_shows_the_sweep_and_not_the_agent_talking_to_itself(tmp_path, monkeypatch) -> None:
    from api import sweep

    log = tmp_path / "l"
    log.write_text(
        "INFO Processing request of type            server.py:733\n"
        "                             CallToolRequest\n"
        "\x1b[36mbench: [7/200] njs.cve-2022-32414\x1b[0m\n"
        f"WARNING agent.llm: content='' additional_kwargs={{'x': '{'y' * 500}'}}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(sweep, "_paths", lambda: (tmp_path / "p", log, tmp_path / "b"))

    found = sweep.status()

    assert found["log"] == ["bench: [7/200] njs.cve-2022-32414"], "escape codes and noise both gone"
    assert (found["position"], found["of"]) == (7, 200)


def test_a_failure_before_logging_starts_is_still_reported(tmp_path, monkeypatch) -> None:
    from api import sweep

    (tmp_path / "b").write_text("bash: .env: Permission denied\n", encoding="utf-8")
    monkeypatch.setattr(sweep, "_paths", lambda: (tmp_path / "p", tmp_path / "l", tmp_path / "b"))

    assert any("Permission denied" in line for line in sweep.status()["log"])


def test_the_list_is_the_whole_split_not_only_what_ran(tmp_path, monkeypatch) -> None:
    from api import bench

    class Record:
        def __init__(self, instance_id):
            self.instance_id = instance_id
            self.project_name = instance_id.split(".")[0]
            self.bug_description = "a crash"

    class Attempt:
        instance_id = "b.cve-2"
        patch = "diff"
        stage = ""
        note = ""
        cwe = "CWE-125"
        run_id = "r"
        config_hash = "cfg"
        verdict = None

    monkeypatch.setattr(
        bench,
        "_secbench_sources",
        lambda split="cve": ([Record("a.cve-1"), Record("b.cve-2"), Record("c.cve-3")], [Attempt()], {}),
    )
    found = bench._secbench_instances()

    assert [i.id for i in found] == ["a.cve-1", "b.cve-2", "c.cve-3"], "dataset order, so it matches [n/200]"
    assert [i.outcome for i in found] == ["not_run", "awaiting_score", "not_run"]


def test_a_chosen_few_reach_the_runner(tmp_path, monkeypatch) -> None:
    from api import sweep

    monkeypatch.setattr(sweep, "_paths", lambda: (tmp_path / "p", tmp_path / "l", tmp_path / "b"))
    seen: dict = {}

    class Fake:
        pid = 4244

    monkeypatch.setattr(sweep.subprocess, "Popen", lambda argv, **kw: (seen.update(kw), Fake())[1])
    sweep.start(["a.cve-1", "b.cve-2"], "oss", resume=False)

    env = seen["env"]
    assert env["SECB_INSTANCES"] == "a.cve-1,b.cve-2"
    assert env["SECB_SPLIT"] == "oss"
    assert env["SECB_RESUME"] == "0"


def test_running_the_whole_split_resumes(tmp_path, monkeypatch) -> None:
    from api import sweep

    monkeypatch.setattr(sweep, "_paths", lambda: (tmp_path / "p", tmp_path / "l", tmp_path / "b"))
    seen: dict = {}

    class Fake:
        pid = 4245

    monkeypatch.setattr(sweep.subprocess, "Popen", lambda argv, **kw: (seen.update(kw), Fake())[1])
    sweep.start()

    assert seen["env"]["SECB_RESUME"] == "1"
    assert seen["env"]["SECB_INSTANCES"] == ""


def test_the_two_splits_are_separate_datasets_that_add_up() -> None:
    from api import bench

    splits = {d.id: d.split for d in bench.DATASETS if d.split}

    assert splits == {"sec-bench": "cve", "sec-bench-oss": "oss"}
    assert sum(d.total for d in bench.DATASETS if d.split) == 300


def test_an_unusable_disk_is_not_an_empty_benchmark(tmp_path, monkeypatch) -> None:
    from agent.bench.config import BenchConfig
    from api import bench

    blocked = tmp_path / "a-file" / "root"
    (tmp_path / "a-file").write_text("not a directory", encoding="utf-8")
    monkeypatch.setattr(bench, "_root_problem", bench._root_problem)
    monkeypatch.setenv("SECB_ROOT", str(blocked))

    assert BenchConfig().root == blocked
    problem = bench._root_problem()
    assert str(blocked) in problem and "디스크" in problem


def test_a_working_disk_reports_nothing(tmp_path, monkeypatch) -> None:
    from api import bench

    monkeypatch.setenv("SECB_ROOT", str(tmp_path / "root"))

    assert bench._root_problem() == ""
    assert list((tmp_path / "root").iterdir()) == []
