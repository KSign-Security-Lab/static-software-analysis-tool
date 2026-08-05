"use client";

import type { RunSummary, SpanSummary } from "@/lib/api/studio";

/**
 * What this session is tracing, and the controls for it.
 *
 * One run, stated plainly at the top, because the trace view follows the code
 * you put in rather than offering a list of everyone else's runs. The numbers
 * are the ones you check before reading anything: did it finish, did it find
 * anything, how much did it cost.
 */

const STATUS: Record<string, string> = {
  done: "완료",
  failed: "실패",
  interrupted: "중단점에서 멈춤",
  inspecting: "검사 중",
  indexing: "색인 중",
  created: "준비됨",
};

export default function RunHeader({
  run,
  summary,
  steps,
  live,
  children,
}: {
  run: RunSummary | null;
  summary: SpanSummary;
  steps: number;
  live: { running: string[]; interrupted: boolean };
  children?: React.ReactNode;
}) {
  const status = run?.status ?? "";
  const files = run?.files ?? [];
  const extra = (run?.file_count ?? files.length) - files.length;

  return (
    <header className="rh">
      <div className="rh-what">
        <h2 className="rh-files">
          {files.length ? files.join(", ") : "실행 없음"}
          {extra > 0 && <span className="rh-extra">+{extra}</span>}
        </h2>

        <div className="rh-facts">
          <span className={`rh-status is-${status}`}>
            {live.running.length > 1
              ? `${[...new Set(live.running)].join(", ")} 동시 실행 중`
              : live.running.length === 1
                ? `${live.running[0]} 실행 중`
                : (STATUS[status] ?? status ?? "—")}
          </span>
          {run?.findings !== undefined && <span className="rh-fact">결과 {run.findings}건</span>}
          <span className="rh-fact">모델 호출 {summary.llm_calls}</span>
          <span className="rh-fact">도구 {summary.tool_calls}</span>
          <span className="rh-fact">단계 {steps}</span>
          {summary.tokens > 0 && <span className="rh-fact">{summary.tokens.toLocaleString()} tok</span>}
          {summary.errors > 0 && <span className="rh-fact is-bad">오류 {summary.errors}</span>}
        </div>
      </div>

      <div className="rh-actions">{children}</div>
    </header>
  );
}
