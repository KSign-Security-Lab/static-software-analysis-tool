"""The benchmark surface's data: what it refuses to show, mostly.

Most of these assert an absence. A page that reports a benchmark is one wrong
number away from being worse than no page, so the tests that matter are the ones
about when a number does *not* render and about the two datasets never touching.
"""

from __future__ import annotations

import pytest

from api import bench


def _instance(**over):
    base = {"id": "x.c", "outcome": "solved", "config_hash": "cfg", "run_id": "r1"}
    return bench.Instance(**{**base, **over})


# -- the two kinds -----------------------------------------------------------


def test_the_two_kinds_are_never_worded_the_same() -> None:
    """Different words for the number, because they are not the same number.

    One is what we tune against and the other is what we do not touch. Sharing a
    label invites reading them as one axis, which is the move that ends the
    held-out set.
    """
    labels = {d.kind: d.score_label for d in bench.DATASETS}
    assert labels["held_out"] != labels["pinned"]
    assert {d.kind for d in bench.DATASETS} == {"held_out", "pinned"}


def test_nothing_computes_across_datasets() -> None:
    """A score is a function of one dataset's instances and nothing else.

    Asserted on the signature rather than the output: `_score` cannot average
    two datasets because it is never handed two.
    """
    import inspect

    params = list(inspect.signature(bench._score).parameters)
    assert params == ["dataset", "instances"]


def test_a_dataset_declares_which_stages_it_can_reach() -> None:
    """The corpus has no build and no test suite, so the three patch stages are
    unreachable rather than merely unobserved. Showing them empty would read as
    'we never fail that way'."""
    corpus = bench._BY_ID["corpus"]
    assert "patch_build_failed" not in corpus.stages
    assert "false_flagged" in corpus.stages

    sec = bench._BY_ID["sec-bench"]
    assert "patch_build_failed" in sec.stages
    # No known-clean half, so there is nothing there to raise a false alarm about.
    assert "false_flagged" not in sec.stages


# -- when a score refuses ----------------------------------------------------


def test_a_score_without_a_config_hash_is_unavailable() -> None:
    """The one the definition of done names.

    A number nobody can attribute to a configuration is a number nobody can act
    on, so it renders as a stated absence rather than as a figure.
    """
    corpus = bench._BY_ID["corpus"]
    score = bench._score(corpus, [_instance(config_hash=None), _instance(id="y.c", config_hash=None)])

    assert score.available is False
    assert score.value is None
    assert "설정 해시" in score.unavailable_reason


def test_a_score_with_mixed_configs_is_unavailable() -> None:
    """Two configs is two experiments; an average describes neither."""
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
    """A model is most of what a score is about."""
    monkeypatch.setattr(bench, "_model_for", lambda _hash: None)
    corpus = bench._BY_ID["corpus"]
    score = bench._score(corpus, [_instance()])

    assert score.available is False
    assert "모델" in score.unavailable_reason


def test_every_refusal_says_why() -> None:
    """A dash and a zero look alike and mean opposite things."""
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


# -- contamination -----------------------------------------------------------


def test_contaminated_instances_leave_the_score_and_not_the_list(monkeypatch) -> None:
    """Marked and subtracted, never filtered. What was dropped and why is part
    of the result."""
    monkeypatch.setattr(bench, "_model_for", lambda _hash: "a-model")
    corpus = bench._BY_ID["corpus"]
    instances = [_instance(), _instance(id="y.c", contaminated=True, outcome="misread")]
    score = bench._score(corpus, instances)

    assert score.excluded == 1
    assert score.scored == 1
    assert score.value == 1.0
    assert len(instances) == 2, "the contaminated one is still in the list"


def test_everything_contaminated_is_unavailable_rather_than_perfect() -> None:
    """An empty denominator is not a 100%."""
    corpus = bench._BY_ID["corpus"]
    score = bench._score(corpus, [_instance(contaminated=True)])

    assert score.available is False
    assert score.excluded == 1


# -- the path join -----------------------------------------------------------


def test_a_subdirectory_run_still_matches_its_instances() -> None:
    """The bug a real run found.

    `agent inspect corpus/CWE-121_.../` records paths relative to *that*
    directory, so an equality join reported all hundred instances as never run
    while a finished run sat in the database.
    """
    corpus_paths = {"CWE-121_stack/copy_bad.c", "CWE-78_cmd/exec_bad.c"}
    assert bench._match("copy_bad.c", corpus_paths) == "CWE-121_stack/copy_bad.c"
    assert bench._match("CWE-78_cmd/exec_bad.c", corpus_paths) == "CWE-78_cmd/exec_bad.c"


def test_an_ambiguous_path_is_refused_rather_than_guessed() -> None:
    """A bare filename that could be two instances resolves to neither. A coin
    flip that lands in a score is worse than an instance reading not-run."""
    corpus_paths = {"CWE-121_stack/copy_bad.c", "CWE-122_heap/copy_bad.c"}
    assert bench._match("copy_bad.c", corpus_paths) is None


def test_a_path_that_is_not_corpus_matches_nothing() -> None:
    assert bench._match("src/main.c", {"CWE-121_stack/copy_bad.c"}) is None


# -- the labels ---------------------------------------------------------------


def _corpus_root():
    from pathlib import Path

    root = Path(__file__).resolve().parents[3] / "corpus"
    if not root.is_dir():
        pytest.skip("the seed corpus is not checked out")
    return root


def test_the_declared_total_matches_the_corpus_on_disk() -> None:
    """`total` is a hand-typed constant; this is what stops it drifting the
    first time somebody edits `corpus/`.

    Counted off disk rather than out of the database, because the corpus is
    committed and the database may not have ingested it -- a guard that skips is
    not a guard.
    """
    root = _corpus_root()
    files = [p for p in root.rglob("*.c") if "scraped" not in p.parts]
    assert len(files) == bench._BY_ID["corpus"].total


def test_an_instance_is_a_file_not_a_function() -> None:
    """One row per chunk in the corpus table, one instance per file here.

    They coincide today only because every seed sample holds a single function.
    A two-function sample would otherwise produce duplicate ids, duplicate list
    keys, and a denominator counting chunks while the label counts files -- so
    this asserts the grouping, using the same reader the ingest uses.
    """
    from agent.rag import corpus as corpus_module

    samples, _ = corpus_module.read(_corpus_root())
    by_file = {sample.file for sample in samples}

    # More chunks than files is allowed; more instances than files is not.
    assert len(by_file) == bench._BY_ID["corpus"].total
    assert len(samples) >= len(by_file)


def test_an_empty_dataset_says_what_to_run() -> None:
    """An empty state that cannot name the next action is a blank panel."""
    for dataset in bench.DATASETS:
        assert dataset.how_to_run, f"{dataset.id} has no instructions for when it is empty"


def test_the_excluded_track_is_shown_as_a_decision() -> None:
    """So nobody later reads the gap as a failure."""
    sec = bench._BY_ID["sec-bench"]
    assert sec.excluded_tracks
    assert "PoC" in sec.excluded_tracks[0]["track"]
    assert sec.excluded_tracks[0]["reason"]


def test_no_baseline_ships_as_a_number_without_its_model_and_source() -> None:
    """An earlier draft gave all three tools an identical 0.34 and a model
    reading 'see the report'. The one part of this page that is trustworthy for
    not being ours is the last place to put a guess."""
    for dataset in bench.DATASETS:
        for baseline in dataset.baselines:
            if baseline.resolved is not None:
                assert baseline.model and baseline.source, f"{baseline.name} has a figure but no provenance"


# -- what counts as the right answer -----------------------------------------


def test_a_sibling_cwe_is_the_same_weakness() -> None:
    """The scorer's first version was wrong in the direction that matters.

    `strcpy(label, in)` into `char label[16]` is labelled CWE-121 here, and the
    agent reported CWE-120 -- the textbook definition of Classic Buffer
    Overflow, and every bit as correct. String equality called that 찾고 오독,
    so a page built to say what to fix next was pointing at a CWE-discrimination
    problem that did not exist.
    """
    assert bench.same_family("CWE-121", "CWE-120")
    assert bench.same_family("CWE-121", "CWE-119")
    assert bench.same_family("CWE-787", "CWE-125")


def test_a_different_weakness_is_still_wrong() -> None:
    """The table is for resolutions of one weakness, not for charity."""
    assert not bench.same_family("CWE-121", "CWE-78")
    assert not bench.same_family("CWE-78", "CWE-22")
    assert not bench.same_family("CWE-416", "CWE-401")


def test_every_corpus_cwe_is_in_a_family() -> None:
    """A label with no family silently degrades to exact matching, which is the
    bug this table was written to fix -- so a new CWE folder must not be able to
    reintroduce it unnoticed."""
    covered = {cwe for family in bench.CWE_FAMILIES for cwe in family}
    root = _corpus_root()
    labels = {p.name.split("_")[0] for p in root.iterdir() if p.is_dir() and p.name.startswith("CWE-")}
    assert labels <= covered, f"no family for {sorted(labels - covered)}"


def test_exact_and_family_are_reported_apart(monkeypatch) -> None:
    """Right family and right id are different claims. One number would hide
    the looser half behind the stricter word."""
    monkeypatch.setattr(bench, "_model_for", lambda _hash: "a-model")
    corpus = bench._BY_ID["corpus"]
    score = bench._score(
        corpus,
        [_instance(matched="exact"), _instance(id="y.c", matched="family")],
    )
    assert score.solved == 2
    assert score.exact == 1


# -- the sweep, started from the surface -------------------------------------
#
# A two-day job behind a button is only honest if the run outlives the page, so
# these are about detachment and about the log the page reads back.


def test_the_run_is_detached_from_the_api_that_started_it(tmp_path, monkeypatch) -> None:
    """The load-bearing argument.

    Without its own session the sweep is a child of a uvicorn worker, and
    uvicorn's reloader kills its children on every file save. A two-day run that
    ended because somebody fixed a typo would be worse than no button.
    """
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
    """The script's own `tee` writes the log *and* passes through to whatever it
    inherited, so pointing the child's stdout at the same file doubled every
    line -- which read as a stutter in the panel and as a corrupted log on disk.
    """
    import subprocess as sp

    from api import sweep

    monkeypatch.setattr(sweep, "_paths", lambda: (tmp_path / "p", tmp_path / "l", tmp_path / "b"))
    seen: dict = {}

    class Fake:
        pid = 4243

    monkeypatch.setattr(sweep.subprocess, "Popen", lambda argv, **kw: (seen.update(kw), Fake())[1])
    sweep.start()

    assert seen["stdout"] is sp.DEVNULL
    # stderr still goes somewhere: it is the only place a failure before the
    # script starts logging could be reported.
    assert seen["stderr"] is not sp.DEVNULL


def test_a_stale_pidfile_does_not_report_a_running_sweep(tmp_path, monkeypatch) -> None:
    """Pidfiles outlive their processes and pids get reused. Signal 0 says
    something is there; only the cmdline says it is ours."""
    from api import sweep

    monkeypatch.setattr(sweep, "_paths", lambda: (tmp_path / "p", tmp_path / "l", tmp_path / "b"))
    # This process is certainly alive and is certainly not the sweep.
    (tmp_path / "p").write_text('{"pid": %d, "started_at": 1}' % __import__("os").getpid())

    assert sweep.status()["running"] is False


def test_the_panel_shows_the_sweep_and_not_the_agent_talking_to_itself(tmp_path, monkeypatch) -> None:
    """The MCP server logs a request per tool call. At three thousand tool calls
    an hour that is the entire tail, and the progress line -- the one thing
    somebody checking on a long run wants -- is never on screen."""
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
    """The script takes over its own logging a few lines in. Anything that goes
    wrong before then -- an unreadable `.env`, a missing bash -- would otherwise
    leave the panel showing the previous run and no reason at all."""
    from api import sweep

    (tmp_path / "b").write_text("bash: .env: Permission denied\n", encoding="utf-8")
    monkeypatch.setattr(sweep, "_paths", lambda: (tmp_path / "p", tmp_path / "l", tmp_path / "b"))

    assert any("Permission denied" in line for line in sweep.status()["log"])


def test_the_list_is_the_whole_split_not_only_what_ran(tmp_path, monkeypatch) -> None:
    """Two hundred instances of which four have been attempted is a set of two
    hundred, and the list has to say so.

    Showing only the attempted ones read as "there are four test cases" -- the
    denominator was on the page in the progress line and the list beside it
    contradicted it. The corpus has always listed its unrun files; this is the
    same rule.
    """
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
    """Selection is what turns a two-day job into a twenty-minute one.

    The runner has read `SECB_INSTANCES` all along; it had no way to be told.
    Everything the page can order is an environment variable, so an order is
    three of them rather than a second way to configure the sweep.
    """
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
    """The default has to stay the safe one: a sweep of two hundred that started
    over after every interruption would never finish."""
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
    """SEC-bench is three hundred instances in two files, and showing one of
    them was being read as showing all of it.

    Separate entries rather than one merged list: the two have different
    provenance -- CVEs against OSS-Fuzz reports -- and a rate over a mixed
    denominator would describe neither.
    """
    from api import bench

    splits = {d.id: d.split for d in bench.DATASETS if d.split}

    assert splits == {"sec-bench": "cve", "sec-bench-oss": "oss"}
    assert sum(d.total for d in bench.DATASETS if d.split) == 300


def test_an_unusable_disk_is_not_an_empty_benchmark(tmp_path, monkeypatch) -> None:
    """The two look identical from the page and mean opposite things.

    `SECB_ROOT` is a mount and mounts go away -- this one aborted its ext4
    journal mid-project, after which every open() returned EIO while `df` went
    on reporting 207G free. Rendering that as 아직 결과가 없습니다 would be the
    page's own failure mode: a state it cannot see, reported as one it
    understands.
    """
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
    """And it leaves nothing behind: the probe is a write, so it has to clean up
    after itself or it is litter in the directory it is checking."""
    from api import bench

    monkeypatch.setenv("SECB_ROOT", str(tmp_path / "root"))

    assert bench._root_problem() == ""
    assert list((tmp_path / "root").iterdir()) == []
