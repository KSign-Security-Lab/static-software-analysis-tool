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


STAGES: tuple[tuple[str, str], ...] = (
    ("not_located", "위치 못 찾음"),
    ("misread", "찾고 오독"),
    ("false_flagged", "오탐"),
    ("patch_build_failed", "패치 빌드 실패"),
    ("built_not_fixed", "빌드됐으나 미수정"),
    ("fixed_tests_broke", "고쳤으나 테스트 깨짐"),
)

HARNESS = "harness_error"
AWAITING = "awaiting_score"
DETECTION_STAGES = ("not_located", "misread", "false_flagged")
CWE_FAMILIES: tuple[frozenset[str], ...] = (
    frozenset({"CWE-119", "CWE-120", "CWE-121", "CWE-122", "CWE-124", "CWE-125", "CWE-787", "CWE-788", "CWE-805"}),
    frozenset({"CWE-77", "CWE-78", "CWE-88"}),
    frozenset({"CWE-22", "CWE-23", "CWE-36"}),
    frozenset({"CWE-134"}),
    frozenset({"CWE-476", "CWE-690"}),
    frozenset({"CWE-190", "CWE-191", "CWE-680"}),
    frozenset({"CWE-415", "CWE-416", "CWE-825"}),
    frozenset({"CWE-401", "CWE-772", "CWE-404"}),
)


def same_family(label: str, reported: str) -> bool:
    if label == reported:
        return True
    return any(label in family and reported in family for family in CWE_FAMILIES)

PATCHING_STAGES = ("not_located", "misread", "patch_build_failed", "built_not_fixed", "fixed_tests_broke")


class Baseline(BaseModel):
    name: str
    model: str = ""
    resolved: float | None = Field(default=None, description="Share of the track it resolved, 0-1.")
    source: str = ""

    @property
    def complete(self) -> bool:
        return self.resolved is not None and bool(self.model) and bool(self.source)


class Instance(BaseModel):
    id: str
    project: str = ""
    cwe: str = ""
    cve: str = ""
    outcome: str = "not_run"
    run_id: str | None = None
    config_hash: str | None = None
    contaminated: bool = False
    contamination_reason: str = ""
    matched: str = "exact"
    note: str = ""


class Score(BaseModel):
    available: bool
    value: float | None = None
    solved: int = 0
    scored: int = 0
    excluded: int = 0
    exact: int = 0
    harness: int = 0
    config_hash: str | None = None
    model: str | None = None
    unavailable_reason: str = ""


class Dataset(BaseModel):
    id: str
    label: str
    kind: str
    score_label: str
    note: str
    total: int
    stages: List[str]
    baselines: List[Baseline] = Field(default_factory=list)
    excluded_tracks: List[Dict[str, str]] = Field(default_factory=list)
    how_to_run: str = ""
    baseline_note: str = ""
    ran_at: float | None = None
    split: str = ""


class SweepOrder(BaseModel):
    instances: List[str] = Field(default_factory=list)
    split: str = "cve"
    force: bool = False


class DatasetView(BaseModel):
    dataset: Dataset
    score: Score
    instances: List[Instance]
    problem: str = ""


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
    stages=list(DETECTION_STAGES),
    how_to_run="agent inspect corpus/ 를 돌리면 인스턴스별 결과가 여기에 쌓입니다.",
)

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


def _ground_truth(config: AgentConfig | None) -> dict[str, tuple[str, str, str]]:
    with session_factory(config)() as session:
        rows = session.scalars(select(CorpusSample).order_by(CorpusSample.cwe, CorpusSample.file)).all()

    by_file: dict[str, tuple[str, str, str]] = {}
    for row in rows:
        cwe, variant, symbols = by_file.get(row.file, (row.cwe, row.variant, ""))
        joined = f"{symbols}, {row.symbol}" if symbols else row.symbol
        by_file[row.file] = (cwe, variant, joined)
    return by_file


def _match(run_path: str, corpus_paths: set[str]) -> str | None:
    if run_path in corpus_paths:
        return run_path
    tail = f"/{run_path}"
    hits = [path for path in corpus_paths if path.endswith(tail)]
    return hits[0] if len(hits) == 1 else None


def _scoring_run(paths: set[str], config: AgentConfig | None) -> RunRow | None:
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
    truth = _ground_truth(config)
    run = _scoring_run(set(truth), config)
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
            out.append(instance)
            continue

        instance.run_id = run.id if run is not None else None
        instance.config_hash = config_hash
        found = reported.get(path, set())
        if variant == "vulnerable":
            if cwe in found:
                instance.outcome = "solved"
            elif any(same_family(cwe, other) for other in found):
                instance.outcome = "solved"
                instance.matched = "family"
                instance.note += f" · 보고된 CWE {', '.join(sorted(found))} (같은 계열)"
            elif found:
                instance.outcome = "misread"
                instance.note += f" · 보고된 CWE {', '.join(sorted(found))}"
            else:
                instance.outcome = "not_located"
        elif found:
            instance.outcome = "false_flagged"
            instance.note += f" · 고쳐진 쪽에 {', '.join(sorted(found)) or '지적'} 이 붙었습니다"
        else:
            instance.outcome = "solved"
        out.append(instance)
    return out


def _secbench_sources(split: str = "cve") -> tuple[list[Any], list[Any], dict[str, Any]]:
    try:
        from agent.bench.config import BenchConfig
        from agent.bench.dataset import load as load_dataset
        from agent.bench.runner import load_attempts
        from agent.bench.score import read_results
    except ImportError:  # pragma: no cover - the sweep is optional
        return [], [], {}

    config = BenchConfig(split=split)
    try:
        records = list(load_dataset(config))
        attempts = list(load_attempts(config))
        verdicts = read_results(config)
    except FileNotFoundError:
        return [], [], {}
    except OSError as err:
        log.warning("bench: cannot read the sweep's directory: %s", err)
        return [], [], {}
    return records, attempts, verdicts


def _root_problem() -> str:
    try:
        from agent.bench.config import BenchConfig
    except ImportError:  # pragma: no cover - the sweep is optional
        return ""

    root = BenchConfig().root
    probe = root / ".readable"
    try:
        root.mkdir(parents=True, exist_ok=True)
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError as err:
        return f"{root} 를 쓸 수 없습니다 — 디스크를 확인하세요 ({err.strerror or err})"
    return ""


def _secbench_instances(split: str = "cve") -> list[Instance]:
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
                    cwe="",
                    cve=instance_id.split(".", 1)[-1].upper() if "." in instance_id else "",
                    outcome="not_run",
                    note=record.bug_description[:120] if record else "",
                )
            )
            continue
        outcome, note = outcome_for(attempt, attempt.verdict or verdicts.get(instance_id))
        out.append(
            Instance(
                id=instance_id,
                project=record.project_name if record else "",
                cwe=attempt.cwe or "",
                cve=instance_id.split(".", 1)[-1].upper() if "." in instance_id else "",
                outcome=outcome,
                run_id=attempt.run_id,
                config_hash=attempt.config_hash,
                note=note or (record.bug_description[:120] if record else ""),
            )
        )
    return out


def _score(dataset: Dataset, instances: list[Instance]) -> Score:
    ran = [i for i in instances if i.outcome not in ("not_run", AWAITING, HARNESS)]
    waiting = sum(1 for i in instances if i.outcome == AWAITING)
    harness = sum(1 for i in instances if i.outcome == HARNESS)
    if not ran:
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


@router.get("/datasets")
def list_datasets() -> Dict[str, Any]:
    return {"datasets": [d.model_dump() for d in DATASETS], "stages": [{"id": s, "label": label} for s, label in STAGES]}


@router.get("/sweep")
def read_sweep() -> Dict[str, Any]:
    from api import sweep

    return sweep.status()


@router.post("/sweep")
def start_sweep(order: SweepOrder | None = None) -> Dict[str, Any]:
    from api import sweep

    order = order or SweepOrder()
    if order.split not in {d.split for d in DATASETS if d.split}:
        raise HTTPException(status_code=400, detail=f"unknown split: {order.split}")

    known = {record.instance_id for record in _secbench_sources(order.split)[0]}
    unknown = [i for i in order.instances if known and i not in known]
    if unknown:
        raise HTTPException(status_code=400, detail=f"{order.split} 에 없는 인스턴스: {', '.join(unknown[:5])}")

    try:
        return sweep.start(order.instances, order.split, resume=not (order.instances and order.force))
    except RuntimeError as err:
        raise HTTPException(status_code=409, detail=str(err)) from err


@router.delete("/sweep")
def stop_sweep() -> Dict[str, Any]:
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
        dataset = dataset.model_copy(update={"ran_at": _last_sweep_at()})
    view = DatasetView(
        dataset=dataset,
        score=_score(dataset, instances),
        instances=instances,
        problem=_root_problem() if dataset.split and not instances else "",
    )
    return view.model_dump()
