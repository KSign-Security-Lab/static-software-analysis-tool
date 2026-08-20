"""Benchmark results, read back. Never run from here.

The sweep is offline and this reads what it recorded. A run button on this
surface would put iterating against the benchmark one click away, and the moment
we tune against a held-out set it stops measuring us and starts measuring how
often we looked at it. Same rule the tuner already follows: anything that
changes what we measure stays out of the request path.

**Two kinds of dataset, and they must not share an axis.**

`held_out` is a public benchmark we do not touch. `pinned` is our own corpus,
which is exactly what we *do* touch -- the tuner's A/B replay scores every
config proposal against it. Putting both under one "score" column invites the
move that destroys the held-out set: read a low number, tune until it rises, and
the benchmark now measures how hard we tried rather than how good we are. So the
kind travels with the dataset, the surface words them differently, and nothing
here ever computes a figure spanning both.

**The taxonomy is a superset.** 위치 못 찾음 and 찾고 오독 are about finding a
weakness; the three patch stages need a build and a test suite to fail in. The
pinned corpus has neither -- it is C files with a known CWE, not reproducible
projects -- so a dataset declares which stages it can reach, and the surface
shows only those. Five buckets with three permanently empty would read as "we
never fail that way" when the truth is "we never test that way".
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from agent.config import AgentConfig
from agent.db import CorpusSample, Run as RunRow, session_factory

log = logging.getLogger(__name__)
router = APIRouter(prefix="/bench", tags=["bench"])


# -- the taxonomy ------------------------------------------------------------

#: Where a run can break, in the order it would break. The ids are English
#: because they are a schema; the labels are Korean because they are read.
STAGES: tuple[tuple[str, str], ...] = (
    ("not_located", "위치 못 찾음"),
    ("misread", "찾고 오독"),
    # Not in the original five, and load-bearing. Those five are about failing
    # to *patch* and have no bucket for flagging code that is fine -- so a false
    # alarm had to land in `misread`, which then meant two opposite failures at
    # once: wrong CWE on a real bug, and a wolf cried on clean code. They need
    # opposite fixes, so a thick bar meaning either tells you nothing, which is
    # the whole reason this page leads with the taxonomy.
    ("false_flagged", "오탐"),
    ("patch_build_failed", "패치 빌드 실패"),
    ("built_not_fixed", "빌드됐으나 미수정"),
    ("fixed_tests_broke", "고쳤으나 테스트 깨짐"),
)

#: Ours broke, not theirs.
#:
#: The image would not pull, the crash paths did not map onto the tree, the
#: inspection raised. In none of those did the agent give an opinion, so there
#: is nothing to score -- and scoring them as `not_located` would charge the
#: agent for our path matching, which is how a harness quietly understates the
#: thing it measures.
HARNESS = "harness_error"

#: Attempted, a patch produced, not yet judged.
#:
#: Distinct from `not_run`, which means nobody tried. A sweep scores each
#: instance as it goes, so this is what an instance looks like between its run
#: and its verdict -- and calling that "안 돌림" told the reader we had not
#: attempted four instances we had in fact patched.
AWAITING = "awaiting_score"

#: What a detection-only dataset can reach. The patch stages need a container
#: that builds and a test suite that passes or does not.
DETECTION_STAGES = ("not_located", "misread", "false_flagged")

#: CWEs that mean the same weakness at different resolutions.
#:
#: String equality was the first scorer and it was wrong in the direction that
#: matters. `strcpy(label, in)` into `char label[16]` is labelled CWE-121 here
#: and the agent reported CWE-120 -- which is the textbook definition of Classic
#: Buffer Overflow, and every bit as correct. Under equality that counted as
#: 찾고 오독, so a benchmark built to say what to fix next was pointing at a
#: CWE-discrimination problem that did not exist.
#:
#: Hand-written from the ten families this corpus actually covers rather than
#: pulled from MITRE. The real hierarchy is a data file and a dependency this
#: repo does not have, and a wrong hand-written table is at least a readable
#: one -- these are cousins under CWE-119 and CWE-664, not a taxonomy anybody
#: has to look up to check.
CWE_FAMILIES: tuple[frozenset[str], ...] = (
    # Reading or writing outside a buffer, at every resolution MITRE gives it.
    frozenset({"CWE-119", "CWE-120", "CWE-121", "CWE-122", "CWE-124", "CWE-125", "CWE-787", "CWE-788", "CWE-805"}),
    # Untrusted input reaching an interpreter.
    frozenset({"CWE-77", "CWE-78", "CWE-88"}),
    frozenset({"CWE-22", "CWE-23", "CWE-36"}),
    frozenset({"CWE-134"}),
    frozenset({"CWE-476", "CWE-690"}),
    # Arithmetic that wraps, and the allocation it then undersizes.
    frozenset({"CWE-190", "CWE-191", "CWE-680"}),
    # Lifetime.
    frozenset({"CWE-415", "CWE-416", "CWE-825"}),
    frozenset({"CWE-401", "CWE-772", "CWE-404"}),
)


def same_family(label: str, reported: str) -> bool:
    """Whether two CWEs name the same weakness.

    Exact first, then family. The caller keeps the distinction -- a page that
    showed 정확 and 계열 as one number would be hiding the thing this table was
    written to make visible.
    """
    if label == reported:
        return True
    return any(label in family and reported in family for family in CWE_FAMILIES)

#: What a dataset with no known-clean half can reach. SEC-bench instances are
#: all vulnerable, so there is nothing there to raise a false alarm *about*.
PATCHING_STAGES = ("not_located", "misread", "patch_build_failed", "built_not_fixed", "fixed_tests_broke")


class Baseline(BaseModel):
    """A published number, with the model that produced it.

    `reported` and never `reproduced`: we did not run these.

    `resolved` and `model` are optional together, and that is the point. A
    baseline without its model is not a comparison -- the model is most of what
    is being compared -- so a half-known one renders as awaiting its source
    rather than as a figure. An earlier draft filled all three tools with an
    identical 0.34 and a model reading "see the report", which is three
    fabrications wearing the authority of published work.
    """

    name: str
    model: str = ""
    resolved: float | None = Field(default=None, description="Share of the track it resolved, 0-1.")
    #: A paper or a repository. A category like "published" is not a citation.
    source: str = ""

    @property
    def complete(self) -> bool:
        return self.resolved is not None and bool(self.model) and bool(self.source)


class Instance(BaseModel):
    """One benchmark instance, and what became of it here."""

    id: str
    project: str = ""
    cwe: str = ""
    cve: str = ""
    #: `solved` | one of `STAGES` | `not_run`.
    outcome: str = "not_run"
    #: The run that produced the outcome. What makes an instance openable in 검사
    #: rather than a row in a report.
    run_id: str | None = None
    config_hash: str | None = None
    #: Kept in the list and out of the score. What was dropped and why is part
    #: of the result, so this is a mark rather than a filter.
    contaminated: bool = False
    contamination_reason: str = ""
    #: `exact` when the reported CWE was the label, `family` when it was the
    #: same weakness at a different resolution. Kept apart because collapsing
    #: them into one number would hide what `CWE_FAMILIES` exists to show.
    matched: str = "exact"
    note: str = ""


class Score(BaseModel):
    """A number, or an explicit refusal to show one.

    A score carries its config hash, its model and how many instances were
    excluded, or it is not a score. Without the first two nobody can tell what
    produced it; without the third the denominator is unknown, and a rate over
    an unknown denominator is a decoration.
    """

    available: bool
    #: Solved over scored, 0-1. None whenever `available` is false.
    value: float | None = None
    solved: int = 0
    scored: int = 0
    excluded: int = 0
    #: Of `solved`, how many named the exact CWE rather than a sibling. Shown
    #: beside the score rather than folded into it: "right family" and "right
    #: id" are different claims, and a page that reported one number would be
    #: hiding the looser half behind the stricter word.
    exact: int = 0
    #: Instances the harness never got an opinion out of, kept out of the
    #: denominator and shown anyway. Silently dropping them would flatter the
    #: score by exactly the number of times our own plumbing failed.
    harness: int = 0
    config_hash: str | None = None
    model: str | None = None
    #: Why there is no number, when there is not.
    unavailable_reason: str = ""


class Dataset(BaseModel):
    """A dataset the page can show. A third one is an entry here, not a page."""

    id: str
    label: str
    #: `held_out` | `pinned`. Decides the words, and that the two never mix.
    kind: str
    #: What the number is called for this kind. Never the same word for both.
    score_label: str
    note: str
    total: int
    stages: List[str]
    baselines: List[Baseline] = Field(default_factory=list)
    #: Tracks deliberately not attempted, with the reason. Shown so a gap is
    #: read as a decision rather than as a missing result.
    excluded_tracks: List[Dict[str, str]] = Field(default_factory=list)
    #: What to run when there is nothing yet. An empty state that cannot say
    #: this is a blank panel.
    how_to_run: str = ""
    #: What is known about the published numbers when the per-tool rows are not
    #: yet fillable.
    baseline_note: str = ""
    #: When the sweep last ran. Held-out results carry it; a number with no date
    #: cannot be checked against the code that produced it.
    ran_at: float | None = None
    #: Which SEC-bench split this reads, for the datasets that have one. The
    #: page hands it back when starting a sweep, so the run and the list it
    #: appears in cannot disagree.
    split: str = ""


class SweepOrder(BaseModel):
    """What to run. Empty means the whole split.

    A selection is the difference between trying the benchmark and committing
    two days to it, and it costs nothing to support: the runner has read
    `SECB_INSTANCES` all along.
    """

    instances: List[str] = Field(default_factory=list)
    split: str = "cve"
    #: Redo instances that already have a result. Off by default, because that
    #: is what makes a long sweep safe to interrupt; on when a selection is
    #: deliberate.
    force: bool = False


class DatasetView(BaseModel):
    dataset: Dataset
    score: Score
    instances: List[Instance]
    #: Why this view is empty, when the reason is not "nothing has run".
    #: `SECB_ROOT` is a mount and mounts go away; rendering that as 아직 결과가
    #: 없습니다 would be this page's own failure mode -- a state it cannot see,
    #: reported as a state it understands.
    problem: str = ""


# -- the two datasets --------------------------------------------------------

SEC_BENCH = Dataset(
    id="sec-bench",
    label="SEC-bench",
    kind="held_out",
    score_label="공개 벤치마크",
    note=(
        "C/C++ 실제 CVE 200건. Docker로 재현되며, 고친 패치가 빌드되고 테스트를 깨지 않는지로 채점합니다. "
        "SEC-bench 전체는 이 200건과 OSS-Fuzz 100건을 합친 300건입니다."
    ),
    total=200,
    split="cve",
    stages=list(PATCHING_STAGES),
    # Named, unnumbered, and deliberately so. What is known is that these three
    # reach at most ~34% on this track; what is not known here is each one's
    # figure, its model, or a citation. The surface renders an incomplete
    # baseline as 출처 대기 rather than as a number, because the one part of
    # this page that is supposed to be trustworthy for not being ours is the
    # last place to put a guess.
    baselines=[
        Baseline(name="SWE-agent"),
        Baseline(name="OpenHands"),
        Baseline(name="Aider"),
    ],
    baseline_note="공개 보고 기준 최고치가 ~34% 로 알려져 있습니다. 도구별 수치·모델·출처는 아직 기록되지 않았습니다.",
    excluded_tracks=[
        {
            "track": "PoC 생성",
            "reason": "범위 밖입니다. 우리는 찾고, 설명하고, 고칩니다. 익스플로잇은 만들지 않습니다.",
        }
    ],
    how_to_run=(
        "위 시작 단추를 누르면 서버에서 따로 떨어져 돌아갑니다. "
        "브라우저를 닫아도, 이 창을 떠나도, API가 다시 떠도 계속됩니다 — 며칠 뒤에 다시 열면 그동안의 진행이 그대로 보입니다. "
        "끝난 건은 건너뛰므로 중지했다가 다시 시작해도 이어서 진행됩니다. "
        "다만 서버가 재부팅되면 멈춥니다. 그때는 다시 시작을 누르면 됩니다."
    ),
)

PINNED = Dataset(
    id="corpus",
    label="고정 코퍼스",
    kind="pinned",
    score_label="내부 기준",
    note="이 저장소의 corpus/ 에 있는 100건. CWE 10종을 취약·고쳐짐 짝으로 담고 있습니다.",
    total=100,
    # Detection only. There is no build and no test suite here, so the three
    # patch stages are unreachable rather than merely unobserved.
    stages=list(DETECTION_STAGES),
    how_to_run="agent inspect corpus/ 를 돌리면 인스턴스별 결과가 여기에 쌓입니다.",
)

#: The other half of SEC-bench.
#:
#: Same records, same harness, different provenance: these come from OSS-Fuzz
#: reports rather than from CVEs, so they have no CVE id and there are a hundred
#: of them over nine projects instead of two hundred over twenty-nine. Its own
#: entry rather than folded into the one above, because a number over a mixed
#: denominator would describe neither -- and because "200" was being read as the
#: whole benchmark when it is two thirds of it.
SEC_BENCH_OSS = SEC_BENCH.model_copy(
    update={
        "id": "sec-bench-oss",
        "label": "SEC-bench (OSS-Fuzz)",
        "split": "oss",
        "total": 100,
        "note": (
            "OSS-Fuzz 리포트에서 만든 100건. CVE 번호가 없는 대신 크래시 재현 환경은 같습니다. "
            "위 200건과 겹치지 않으며, 두 쪽을 합친 300건이 SEC-bench 전체입니다."
        ),
    }
)

DATASETS: tuple[Dataset, ...] = (SEC_BENCH, SEC_BENCH_OSS, PINNED)
_BY_ID = {d.id: d for d in DATASETS}


# -- reading what happened ---------------------------------------------------


def _ground_truth(config: AgentConfig | None) -> dict[str, tuple[str, str, str]]:
    """One entry per corpus *file*: its CWE, its variant, and its symbols.

    Keyed by file rather than by row. `CorpusSample` is one row per function
    chunk, and today that happens to be one row per file only because every seed
    sample holds a single function -- 100 rows, 100 distinct paths, none with
    two. A two-function sample would otherwise produce two instances with the
    same id, duplicate keys in the list, and a denominator counting chunks while
    the label counts files.

    An instance is a file: one sample either demonstrates a weakness or is the
    fixed half of a pair, and that is a property of the file, not of a function
    inside it.
    """
    with session_factory(config)() as session:
        rows = session.scalars(select(CorpusSample).order_by(CorpusSample.cwe, CorpusSample.file)).all()

    by_file: dict[str, tuple[str, str, str]] = {}
    for row in rows:
        cwe, variant, symbols = by_file.get(row.file, (row.cwe, row.variant, ""))
        joined = f"{symbols}, {row.symbol}" if symbols else row.symbol
        by_file[row.file] = (cwe, variant, joined)
    return by_file


def _match(run_path: str, corpus_paths: set[str]) -> str | None:
    """The corpus file a run's path refers to, or None if it is not one.

    A run records paths relative to whatever root it was pointed at, and the
    corpus records them relative to `corpus/`. Inspect the whole corpus and the
    two agree; inspect one CWE folder -- which is the ordinary way to work, and
    what the verification does -- and the run says `copy_label_bad.c` where the
    corpus says `CWE-121_stack_based_buffer_overflow/copy_label_bad.c`. An
    equality join reported every one of a hundred instances as never run while a
    finished run sat in the database.

    So: equal, or a suffix on a path boundary. **Ambiguity is refused rather
    than guessed** -- if a bare filename could be two different instances, the
    honest outcome is that this run does not say which, not a coin flip that
    lands in a score. Basenames are unique across the corpus today, so this
    resolves; the guard is for the corpus that grows a second `copy_bad.c`.
    """
    if run_path in corpus_paths:
        return run_path
    tail = f"/{run_path}"
    hits = [path for path in corpus_paths if path.endswith(tail)]
    return hits[0] if len(hits) == 1 else None


def _scoring_run(paths: set[str], config: AgentConfig | None) -> RunRow | None:
    """The one run this view scores, or None.

    One run, not a merge of every run that ever touched the corpus. The obvious
    version -- fold all completed runs into a path->finding map -- lets an
    unordered query decide which run wins each file, so re-running under an
    *identical* config splices two sweeps into a number describing neither,
    while the config-hash guard sees a single hash and calls it clean.

    Most recent first, and a run qualifies by having actually read a corpus
    file. That makes a subset run -- one CWE folder, which is what the
    verification does -- work honestly rather than by coincidence.

    Replay arms are skipped, the same exclusion the tuner makes: an A/B arm
    tests a config, it is not an observation of one.
    """
    with session_factory(config)() as session:
        runs = session.scalars(
            select(RunRow).where(RunRow.status == "done").order_by(RunRow.created_at.desc())
        ).all()
        for row in runs:
            if (row.meta or {}).get("replay"):
                continue
            if any(_match(f.path, paths) for f in row.files):
                session.expunge(row)
                return row
    return None


def _corpus_instances(config: AgentConfig | None = None) -> list[Instance]:
    """The pinned corpus, with what one run concluded about each file.

    Ground truth is the corpus row: the folder named the CWE, the filename said
    whether the sample demonstrates it or fixes it. The outcome is that against
    what the scoring run reported for the same path.
    """
    truth = _ground_truth(config)
    run = _scoring_run(set(truth), config)

    # Both keyed by *corpus* path, so everything below compares like with like.
    reported: dict[str, set[str]] = {}
    inspected: set[str] = set()
    if run is not None:
        with session_factory(config)() as session:
            fresh = session.get(RunRow, run.id)
            for file in fresh.files if fresh else []:
                matched = _match(file.path, set(truth))
                if matched:
                    inspected.add(matched)
        for finding in (run.report or {}).get("findings") or []:
            path = _match((finding.get("primary") or {}).get("file") or "", set(truth))
            if not path:
                continue
            found = reported.setdefault(path, set())
            if finding.get("cwe"):
                found.add(str(finding["cwe"]))

    config_hash = (run.meta or {}).get("config_hash") if run is not None else None

    out: list[Instance] = []
    for path, (cwe, variant, symbols) in truth.items():
        instance = Instance(
            id=path,
            project="corpus",
            cwe=cwe,
            note=f"{symbols} · {'취약' if variant == 'vulnerable' else '고쳐짐'}",
        )
        if path not in inspected:
            # Not looked at by the scoring run. Distinct from "looked at and
            # nothing said", which is a result.
            out.append(instance)
            continue

        instance.run_id = run.id if run is not None else None
        instance.config_hash = config_hash
        found = reported.get(path, set())
        if variant == "vulnerable":
            if cwe in found:
                instance.outcome = "solved"
            elif any(same_family(cwe, other) for other in found):
                # The same weakness at a different resolution. Solved, and said
                # so -- the note keeps what was actually reported, because
                # "right family, different id" is worth being able to see
                # without it counting against the run.
                instance.outcome = "solved"
                instance.matched = "family"
                instance.note += f" · 보고된 CWE {', '.join(sorted(found))} (같은 계열)"
            elif found:
                instance.outcome = "misread"
                instance.note += f" · 보고된 CWE {', '.join(sorted(found))}"
            else:
                instance.outcome = "not_located"
        elif found:
            # A weakness reported in the half that has none.
            instance.outcome = "false_flagged"
            instance.note += f" · 고쳐진 쪽에 {', '.join(sorted(found)) or '지적'} 이 붙었습니다"
        else:
            instance.outcome = "solved"
        out.append(instance)
    return out


def _secbench_sources(split: str = "cve") -> tuple[list[Any], list[Any], dict[str, Any]]:
    """`(dataset records, attempts, verdicts)`, all three off disk.

    Read off disk rather than out of the database, because a sweep is a thing
    that happens beside the app -- offline, over hours, possibly on another
    machine -- and the surface's job is to show what it left behind.

    Imported inside the function so the API does not pull the sweep's module
    graph on startup: `agent.bench` is deliberately not part of the request
    path, and importing it here would make that untrue in the import graph even
    if nothing called it. Separated from the join below so the join can be
    tested without two hundred instances on disk.
    """
    try:
        from agent.bench.config import BenchConfig
        from agent.bench.dataset import load as load_dataset
        from agent.bench.runner import load_attempts
        from agent.bench.score import read_results
    except ImportError:  # pragma: no cover - the sweep is optional
        return [], [], {}

    # The split decides which file is read; everything else -- attempts, results,
    # the run directory -- is shared, and instance ids do not collide across the
    # two, so one sweep's output is readable from either page.
    config = BenchConfig(split=split)
    try:
        records = list(load_dataset(config))
        attempts = list(load_attempts(config))
        verdicts = read_results(config)
    except OSError as err:
        # FileNotFoundError means nothing has been fetched yet, which is the
        # ordinary first state. The wider OSError is a disk that has stopped
        # answering -- `SECB_ROOT` is a mount that can go away, and it has --
        # and neither is a reason to return a 500 to a page whose whole job is
        # to say what state things are in.
        log.warning("bench: cannot read the sweep's directory: %s", err)
        return [], [], {}
    return records, attempts, verdicts


def _root_problem() -> str:
    """Why the sweep's directory cannot be read, when it cannot.

    Deliberately not `df`: free space and a working filesystem are different
    questions. An ext4 volume that has aborted its journal goes on reporting
    hundreds of free gigabytes while every open() returns EIO, so the only
    check worth making is to touch it.
    """
    try:
        from agent.bench.config import BenchConfig
    except ImportError:  # pragma: no cover - the sweep is optional
        return ""

    root = BenchConfig().root
    # A write, because nothing cheaper is decisive: `listdir` answers out of the
    # dentry cache long after the inodes behind it stopped opening, so a
    # directory can list its contents and refuse to produce any of them.
    probe = root / ".readable"
    try:
        root.mkdir(parents=True, exist_ok=True)
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError as err:
        return f"{root} 를 쓸 수 없습니다 — 디스크를 확인하세요 ({err.strerror or err})"
    return ""


def _secbench_instances(split: str = "cve") -> list[Instance]:
    """Every instance in the split, with what the sweep concluded about it.

    The whole split, in the order the sweep walks it, so an unattempted instance
    is a row saying so rather than an absence. Listing only what had been
    attempted made a set of two hundred read as a set of four -- the denominator
    was on the page in the progress line, and the list beside it contradicted
    it.
    """
    try:
        from agent.bench.score import outcome_for
    except ImportError:  # pragma: no cover - the sweep is optional
        return []

    known, recorded, verdicts = _secbench_sources(split)
    attempts = {attempt.instance_id: attempt for attempt in recorded}
    records = {record.instance_id: record for record in known}
    ids = [record.instance_id for record in known] or list(attempts)

    out: list[Instance] = []
    for instance_id in ids:
        record = records.get(instance_id)
        attempt = attempts.get(instance_id)
        if attempt is None:
            out.append(
                Instance(
                    id=instance_id,
                    project=record.project_name if record else "",
                    cwe="",  # the benchmark ships no label; the CWE is the agent's answer
                    cve=instance_id.split(".", 1)[-1].upper() if "." in instance_id else "",
                    outcome="not_run",
                    note=record.bug_description[:120] if record else "",
                )
            )
            continue
        # The attempt's own verdict first: it was written while the instance's
        # image was still on disk, which is the only moment it could be. The
        # batch results are the fallback for a re-score.
        outcome, note = outcome_for(attempt, attempt.verdict or verdicts.get(instance_id))
        out.append(
            Instance(
                id=instance_id,
                project=record.project_name if record else "",
                cwe=attempt.cwe or "",
                # The instance id carries the CVE: `njs.cve-2022-32414`.
                cve=instance_id.split(".", 1)[-1].upper() if "." in instance_id else "",
                outcome=outcome,
                run_id=attempt.run_id,
                config_hash=attempt.config_hash,
                note=note or (record.bug_description[:120] if record else ""),
            )
        )
    return out


def _score(dataset: Dataset, instances: list[Instance]) -> Score:
    """Solved over scored, or a stated reason there is no number.

    Every branch that returns `available=False` names what is missing. A score
    that renders as a dash with no explanation is the same problem as a score
    with no config hash: a number nobody can act on.
    """
    ran = [i for i in instances if i.outcome not in ("not_run", AWAITING, HARNESS)]
    waiting = sum(1 for i in instances if i.outcome == AWAITING)
    harness = sum(1 for i in instances if i.outcome == HARNESS)
    if not ran:
        # Said in the order a reader needs it. "No config hash" is true of the
        # handful that failed before a run existed, and it is not why there is
        # no score when four more are sitting unjudged.
        if waiting:
            return Score(
                available=False,
                harness=harness,
                unavailable_reason=f"{waiting}건이 채점을 기다리고 있습니다 — 스윕을 다시 시작하면 채워집니다",
            )
        return Score(available=False, harness=harness, unavailable_reason="아직 돌린 결과가 없습니다")

    excluded = [i for i in ran if i.contaminated]
    scored = [i for i in ran if not i.contaminated]
    if not scored:
        return Score(
            available=False,
            excluded=len(excluded),
            harness=harness,
            unavailable_reason="채점 대상이 모두 오염으로 제외되었습니다",
        )

    hashes = {i.config_hash for i in scored if i.config_hash}
    if not hashes:
        return Score(
            available=False,
            solved=sum(1 for i in scored if i.outcome == "solved"),
            scored=len(scored),
            excluded=len(excluded),
            harness=harness,
            unavailable_reason="설정 해시가 없습니다 — 어떤 설정으로 낸 숫자인지 알 수 없습니다",
        )
    if len(hashes) > 1:
        # Two configs is two experiments. Averaging them produces a number that
        # describes neither.
        return Score(
            available=False,
            scored=len(scored),
            excluded=len(excluded),
            harness=harness,
            unavailable_reason=f"설정이 {len(hashes)}가지 섞여 있습니다 — 한 설정의 결과만 채점합니다",
        )

    config_hash = next(iter(hashes))
    model = _model_for(config_hash)
    if not model:
        return Score(
            available=False,
            scored=len(scored),
            excluded=len(excluded),
            config_hash=config_hash,
            harness=harness,
            unavailable_reason="이 설정에 모델이 기록되어 있지 않습니다",
        )

    solved = [i for i in scored if i.outcome == "solved"]
    return Score(
        available=True,
        value=len(solved) / len(scored),
        solved=len(solved),
        exact=sum(1 for i in solved if i.matched == "exact"),
        scored=len(scored),
        excluded=len(excluded),
        harness=harness,
        config_hash=config_hash,
        model=model,
    )


def _last_sweep_at() -> float | None:
    """When the sweep last wrote an attempt."""
    try:
        from agent.bench.config import BenchConfig
    except ImportError:  # pragma: no cover
        return None
    found = sorted(BenchConfig().runs_dir.glob("*/attempt.json"))
    return max((path.stat().st_mtime for path in found), default=None)


def _model_for(config_hash: str) -> str | None:
    from agent.harness import load

    recorded = load(config_hash)
    if recorded is None:
        return None
    model = recorded.knobs.get("model")
    return str(model) if model else None


# -- routes ------------------------------------------------------------------


@router.get("/datasets")
def list_datasets() -> Dict[str, Any]:
    """Every dataset this page can show, with its kind and its words."""
    return {"datasets": [d.model_dump() for d in DATASETS], "stages": [{"id": s, "label": label} for s, label in STAGES]}


# The three below are declared before `/{dataset_id}` because FastAPI matches in
# declaration order and `sweep` is a perfectly good dataset id as far as the
# path converter is concerned.


@router.get("/sweep")
def read_sweep() -> Dict[str, Any]:
    """Whether a sweep is running, and what it is on.

    Read off disk, so the answer is the same in every browser and survives the
    API restarting under it. A run started here outlives the page that started
    it -- that is the only shape a two-hundred-instance job can have.
    """
    from api import sweep

    return sweep.status()


@router.post("/sweep")
def start_sweep(order: SweepOrder | None = None) -> Dict[str, Any]:
    """Start it, detached, over the whole split or a chosen few.

    The page this sits behind was specified read-only, and the reason still
    holds for the *results*: a held-out benchmark you can re-run at a click is
    one you will end up tuning against. What makes the button safe is that the
    agent's own graph cannot see the benchmark at all -- there is a test on it --
    so no amount of re-running feeds back into what is being measured.
    """
    from api import sweep

    order = order or SweepOrder()
    if order.split not in {d.split for d in DATASETS if d.split}:
        raise HTTPException(status_code=400, detail=f"unknown split: {order.split}")

    # Checked here rather than left to the runner: it raises KeyError on an
    # unknown id, which would show up as a sweep that started and died, and
    # "started and died" is the hardest state to read on a page like this.
    known = {record.instance_id for record in _secbench_sources(order.split)[0]}
    unknown = [i for i in order.instances if known and i not in known]
    if unknown:
        raise HTTPException(status_code=400, detail=f"{order.split} 에 없는 인스턴스: {', '.join(unknown[:5])}")

    try:
        # A deliberate selection re-runs; the whole split resumes. Choosing an
        # instance and watching it be skipped is not what choosing means.
        return sweep.start(order.instances, order.split, resume=not (order.instances and order.force))
    except RuntimeError as err:
        raise HTTPException(status_code=409, detail=str(err)) from err


@router.delete("/sweep")
def stop_sweep() -> Dict[str, Any]:
    """Stop it. Resumable, so this costs the instance in flight and nothing else."""
    from api import sweep

    try:
        return sweep.stop()
    except RuntimeError as err:
        raise HTTPException(status_code=409, detail=str(err)) from err


@router.get("/{dataset_id}")
def read_dataset(dataset_id: str) -> Dict[str, Any]:
    dataset = _BY_ID.get(dataset_id)
    if dataset is None:
        raise HTTPException(status_code=404, detail=f"unknown dataset: {dataset_id}")

    instances = _corpus_instances() if dataset.id == "corpus" else _secbench_instances(dataset.split)
    if dataset.split and instances:
        # A held-out number with no date cannot be checked against the code that
        # produced it, so the dataset carries when the sweep last wrote.
        dataset = dataset.model_copy(update={"ran_at": _last_sweep_at()})
    view = DatasetView(
        dataset=dataset,
        score=_score(dataset, instances),
        instances=instances,
        problem=_root_problem() if dataset.split and not instances else "",
    )
    return view.model_dump()
