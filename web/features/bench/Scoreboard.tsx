"use client";

import { CircleSlash, Info } from "lucide-react";

import { useDataset, useDatasetId } from "@/lib/bench/queries";
import Sweep from "@/features/bench/Sweep";
import {
  OUTCOME_DOT,
  OUTCOME_LABEL,
  isComplete,
  type Dataset,
  type DatasetView,
  type Outcome,
  type Score,
} from "@/lib/bench/types";
import { cn } from "@/lib/utils";

export default function Scoreboard() {
  const [datasetId] = useDatasetId();
  const view = useDataset(datasetId);

  if (!view.data) {
    return <div className="p-6 text-xs text-ink-faint">{view.isLoading ? "읽는 중…" : "데이터셋을 고르세요."}</div>;
  }

  const { dataset, score } = view.data;

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-6 overflow-auto p-6">
      <header className="flex items-start justify-between gap-6">
        <div className="min-w-0">
          <h1 className="text-sm font-medium text-ink-strong">{dataset.label}</h1>
          <p className="max-w-prose pt-1 text-xs leading-relaxed text-ink-muted">{dataset.note}</p>
          <p className="pt-2 text-2xs text-ink-faint">
            {dataset.kind === "held_out"
              ? "고정 대상입니다. 여기에 맞춰 조정하지 않습니다 — 조정하는 순간 이 숫자는 우리를 재는 것이 아니라 우리가 몇 번 들여다봤는지를 재게 됩니다."
              : "조정 대상입니다. 설정 제안은 적용되기 전에 전부 여기서 A/B로 채점됩니다."}
          </p>
        </div>
        <ScoreCard dataset={dataset} score={score} />
      </header>

      {view.data.problem && (
        <p className="rounded-md border border-warn/40 bg-warn-wash px-3 py-2 text-xs text-warn">{view.data.problem}</p>
      )}
      <Progress view={view.data} />
      {dataset.split && <Sweep dataset={dataset} instances={view.data.instances} />}
      <Breakdown view={view.data} />

      {dataset.excluded_tracks.length > 0 && (
        <section className="rounded-md border border-line bg-surface-2 p-3">
          <h2 className="text-2xs font-medium text-ink-muted">범위 밖 (선택해서 빼둔 것)</h2>
          {dataset.excluded_tracks.map((excluded) => (
            <p key={excluded.track} className="pt-1.5 text-xs leading-relaxed text-ink-faint">
              <span className="text-ink-muted">{excluded.track}</span> — {excluded.reason}
            </p>
          ))}
        </section>
      )}

      {dataset.baselines.length > 0 && <Baselines dataset={dataset} />}
    </div>
  );
}

function Progress({ view }: { view: DatasetView }) {
  const total = view.dataset.total || view.instances.length;
  const attempted = view.instances.filter((i) => i.outcome !== "not_run").length;
  if (!total || attempted >= total) return null;

  return (
    <section>
      <h2 className="text-2xs font-medium text-ink-muted">
        진행
        <span className="pl-1.5 font-normal text-ink-faint">
          — {total}건 중 {attempted}건 시도 · 남은 {total - attempted}건은 아직 돌리지 않았습니다
        </span>
      </h2>
      <span className="mt-2 block h-1 overflow-hidden rounded-sm bg-surface-2">
        <span className="block h-full rounded-sm bg-accent" style={{ width: `${(attempted / total) * 100}%` }} />
      </span>
    </section>
  );
}

function Breakdown({ view }: { view: DatasetView }) {
  const stages: Outcome[] = [...view.dataset.stages, "solved"];
  const counted = view.instances.filter((i) => !["not_run", "awaiting_score", "harness_error"].includes(i.outcome));
  if (counted.length === 0) return null;

  const rows = stages
    .map((outcome) => ({ outcome, n: counted.filter((i) => i.outcome === outcome).length }))
    .filter((row) => row.n > 0);

  return (
    <section>
      <h2 className="text-2xs font-medium text-ink-muted">
        어디서 깨졌는가
        <span className="pl-1.5 font-normal text-ink-faint">
          — {counted.length}건 중 · 나머지 {view.instances.length - counted.length}건은 채점 전입니다
        </span>
      </h2>
      <ul className="flex flex-col gap-1.5 pt-2">
        {rows.map((row) => (
          <li key={row.outcome} className="flex items-center gap-2">
            <span className="w-24 shrink-0 text-2xs text-ink-muted">{OUTCOME_LABEL[row.outcome]}</span>
            <span className="h-2 min-w-0 flex-1 overflow-hidden rounded-sm bg-surface-2">
              <span
                className={cn("block h-full rounded-sm", OUTCOME_DOT[row.outcome])}
                style={{ width: `${(row.n / counted.length) * 100}%` }}
              />
            </span>
            <span className="w-8 shrink-0 text-right font-mono text-2xs text-ink-muted">{row.n}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}

function ScoreCard({ dataset, score }: { dataset: Dataset; score: Score }) {
  if (!score.available) {
    return (
      <div className="w-56 shrink-0 rounded-md border border-line bg-surface-2 p-3">
        <p className="text-2xs text-ink-faint">{dataset.score_label}</p>
        <p className="flex items-center gap-1.5 pt-1 text-sm text-ink-muted">
          <CircleSlash className="size-3.5 shrink-0" />
          점수 없음
        </p>
        <p className="pt-1.5 text-2xs leading-relaxed text-ink-faint">{score.unavailable_reason}</p>
        {typeof score.excluded === "number" && score.excluded > 0 && (
          <p className="pt-1 text-2xs text-warn">오염 제외 {score.excluded}건</p>
        )}
        {score.harness > 0 && <p className="pt-1 text-2xs text-ink-faint">실행 실패 {score.harness}건 (채점 대상 아님)</p>}
      </div>
    );
  }

  return (
    <div className="w-56 shrink-0 rounded-md border border-line bg-surface-2 p-3">
      <p className="text-2xs text-ink-faint">{dataset.score_label}</p>
      <p className="pt-0.5 font-mono text-2xl text-ink-strong">{Math.round(score.value * 100)}%</p>
      <dl className="grid grid-cols-[auto_1fr] gap-x-2 gap-y-0.5 pt-2 text-2xs">
        <dt className="text-ink-faint">통과</dt>
        <dd className="font-mono text-ink-muted">
          {score.solved} / {score.scored}
        </dd>
        <dt className="text-ink-faint">정확</dt>
        <dd className="font-mono text-ink-muted">
          {score.exact}
          {score.solved > score.exact && (
            <span className="pl-1 text-ink-faint">· 계열 {score.solved - score.exact}</span>
          )}
        </dd>
        <dt className="text-ink-faint">모델</dt>
        <dd className="truncate font-mono text-ink-muted">{score.model}</dd>
        <dt className="text-ink-faint">설정</dt>
        <dd className="truncate font-mono text-ink-muted">{score.config_hash}</dd>
        <dt className="text-ink-faint">제외</dt>
        <dd className="font-mono text-ink-muted">{score.excluded}</dd>
        <dt className="text-ink-faint">실행 실패</dt>
        <dd className="font-mono text-ink-muted">{score.harness}</dd>
      </dl>
      {dataset.ran_at && (
        <p className="pt-1.5 text-2xs text-ink-faint">
          {new Date(dataset.ran_at * 1000).toLocaleDateString("ko-KR")} 실행
        </p>
      )}
    </div>
  );
}

function Baselines({ dataset }: { dataset: Dataset }) {
  return (
    <section>
      <h2 className="flex items-center gap-1.5 text-2xs font-medium text-ink-muted">
        공개 수치
        <span className="font-normal text-ink-faint">— 보고된 값이며 우리가 재현한 것이 아닙니다</span>
      </h2>
      <ul className="pt-2">
        {dataset.baselines.map((baseline) => (
          <li
            key={baseline.name}
            className="flex items-baseline justify-between gap-4 border-b border-line py-1.5 last:border-b-0"
          >
            <span className="text-xs text-ink">{baseline.name}</span>
            {isComplete(baseline) ? (
              <span className="flex items-baseline gap-2">
                <span className="font-mono text-xs text-ink-muted">{baseline.model}</span>
                <span className="font-mono text-sm text-ink-strong">
                  {Math.round((baseline.resolved ?? 0) * 100)}%
                </span>
              </span>
            ) : (
              <span className="text-2xs text-ink-faint">출처 대기</span>
            )}
          </li>
        ))}
      </ul>
      {dataset.baseline_note && (
        <p className="flex items-start gap-1.5 pt-2 text-2xs leading-relaxed text-ink-faint">
          <Info className="mt-0.5 size-3 shrink-0" />
          {dataset.baseline_note}
        </p>
      )}
    </section>
  );
}
