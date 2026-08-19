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

#: What a detection-only dataset can reach. The patch stages need a container
#: that builds and a test suite that passes or does not.
DETECTION_STAGES = ("not_located", "misread", "false_flagged")

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


class DatasetView(BaseModel):
    dataset: Dataset
    score: Score
    instances: List[Instance]


# -- the two datasets --------------------------------------------------------

SEC_BENCH = Dataset(
    id="sec-bench",
    label="SEC-bench",
    kind="held_out",
    score_label="공개 벤치마크",
    note="C/C++ 실제 CVE 200건. Docker로 재현되며, 고친 패치가 빌드되고 테스트를 깨지 않는지로 채점합니다.",
    total=200,
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
    how_to_run="SEC-bench 패치 트랙 스윕은 아직 이 저장소에 없습니다. 스윕이 인스턴스별 결과를 기록하면 여기에 그대로 나옵니다.",
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

DATASETS: tuple[Dataset, ...] = (SEC_BENCH, PINNED)
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


def _score(dataset: Dataset, instances: list[Instance]) -> Score:
    """Solved over scored, or a stated reason there is no number.

    Every branch that returns `available=False` names what is missing. A score
    that renders as a dash with no explanation is the same problem as a score
    with no config hash: a number nobody can act on.
    """
    ran = [i for i in instances if i.outcome != "not_run"]
    if not ran:
        return Score(available=False, unavailable_reason="아직 돌린 결과가 없습니다")

    excluded = [i for i in ran if i.contaminated]
    scored = [i for i in ran if not i.contaminated]
    if not scored:
        return Score(
            available=False,
            excluded=len(excluded),
            unavailable_reason="채점 대상이 모두 오염으로 제외되었습니다",
        )

    hashes = {i.config_hash for i in scored if i.config_hash}
    if not hashes:
        return Score(
            available=False,
            solved=sum(1 for i in scored if i.outcome == "solved"),
            scored=len(scored),
            excluded=len(excluded),
            unavailable_reason="설정 해시가 없습니다 — 어떤 설정으로 낸 숫자인지 알 수 없습니다",
        )
    if len(hashes) > 1:
        # Two configs is two experiments. Averaging them produces a number that
        # describes neither.
        return Score(
            available=False,
            scored=len(scored),
            excluded=len(excluded),
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
            unavailable_reason="이 설정에 모델이 기록되어 있지 않습니다",
        )

    solved = sum(1 for i in scored if i.outcome == "solved")
    return Score(
        available=True,
        value=solved / len(scored),
        solved=solved,
        scored=len(scored),
        excluded=len(excluded),
        config_hash=config_hash,
        model=model,
    )


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


@router.get("/{dataset_id}")
def read_dataset(dataset_id: str) -> Dict[str, Any]:
    dataset = _BY_ID.get(dataset_id)
    if dataset is None:
        raise HTTPException(status_code=404, detail=f"unknown dataset: {dataset_id}")

    instances = _corpus_instances() if dataset.id == "corpus" else []
    view = DatasetView(dataset=dataset, score=_score(dataset, instances), instances=instances)
    return view.model_dump()
