"use client";

import { useState } from "react";

import type { Checkpoint } from "@/lib/api/agent";

/**
 * Every super-step of the run, as LangGraph checkpointed it.
 *
 * The trace says what was called; this says what the graph knew. Selecting a
 * step shows the state at that moment -- what was still queued, which chunk was
 * current, what the tallies were -- which is the thing to read when a run took
 * a branch you did not expect.
 */

function count(value: unknown): string {
  if (value && typeof value === "object" && "count" in value) return String((value as { count: number }).count);
  if (value && typeof value === "object" && "remaining" in value) {
    return String((value as { remaining: number }).remaining);
  }
  return "—";
}

export default function StepsView({ checkpoints }: { checkpoints: Checkpoint[] }) {
  // Null rather than an index: the component mounts before the fetch lands, so
  // any index chosen now is against an empty list. Null means "the last one",
  // which also keeps a live run pinned to its newest step.
  const [picked, setPicked] = useState<number | null>(null);
  const last = checkpoints.length - 1;
  const at = picked === null ? last : Math.min(picked, last);
  const step = checkpoints[at] ?? null;

  if (!step) return <p className="ws-empty">체크포인트가 없습니다. 검사를 실행하면 단계별 상태가 쌓입니다.</p>;

  const values = step.values ?? {};
  const stats = (values.stats ?? {}) as Record<string, number>;

  return (
    <div className="steps">
      <div className="steps-rail">
        <div className="ws-pane-title">
          <span>단계 {checkpoints.length}</span>
          <span className="span-tok">
            {step.step} / {(checkpoints[last]?.step ?? 0) as number}
          </span>
        </div>
        {/* A slider, not a list: stepping through is the point, and 200 rows of
            plan/context/analyse is not something anyone scrolls. */}
        <input
          type="range"
          className="steps-slider"
          min={0}
          max={last}
          value={at}
          onChange={(e) => setPicked(Number(e.target.value))}
        />
        <div className="steps-track">
          {checkpoints.map((cp, i) => (
            <button
              key={cp.checkpoint_id ?? i}
              type="button"
              title={`${cp.step}: ${cp.node ?? "start"}`}
              className={`steps-tick ${i === at ? "is-selected" : ""} ${cp.node ? `n-${cp.node}` : ""}`}
              onClick={() => setPicked(i)}
            >
              <span className="steps-tick-label">{cp.node ?? "시작"}</span>
            </button>
          ))}
        </div>
      </div>

      <div className="span-detail">
        <div className="span-meta">
          <span>단계 {step.step}</span>
          <span>노드 {step.node ?? "—"}</span>
          <span>다음 {step.next.length ? step.next.join(", ") : "종료"}</span>
          {step.created_at && <span>{new Date(step.created_at).toLocaleTimeString()}</span>}
        </div>

        <h3>이 시점의 상태</h3>
        <dl className="state-grid">
          <div>
            <dt>남은 청크</dt>
            <dd>{count(values.pending)}</dd>
          </div>
          <div>
            <dt>현재 청크</dt>
            <dd className="mono">{(values.current as string) ?? "—"}</dd>
          </div>
          <div>
            <dt>후보</dt>
            <dd>{count(values.candidates)}</dd>
          </div>
          <div>
            <dt>위치 확정</dt>
            <dd>{count(values.located)}</dd>
          </div>
          <div>
            <dt>검증 통과</dt>
            <dd>{count(values.confirmed)}</dd>
          </div>
          <div>
            <dt>반박됨</dt>
            <dd>{stats.refuted ?? 0}</dd>
          </div>
          <div>
            <dt>앵커 실패</dt>
            <dd>{stats.dropped_unlocatable ?? 0}</dd>
          </div>
          <div>
            <dt>검사한 청크</dt>
            <dd>
              {stats.chunks_inspected ?? 0} / {stats.chunks_total ?? 0}
            </dd>
          </div>
        </dl>

        <h3>다음 실행 대기</h3>
        <pre className="span-io">
          {JSON.stringify((values.pending as { next?: string[] })?.next ?? [], null, 2)}
        </pre>
      </div>
    </div>
  );
}
