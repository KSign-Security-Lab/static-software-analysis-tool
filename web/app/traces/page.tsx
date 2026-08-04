"use client";

import { useCallback, useEffect, useState } from "react";

import { get } from "@/lib/http";
import type { TracingStatus } from "@/lib/api/agent";

/**
 * LangSmith traces.
 *
 * Not an iframe: LangSmith serves `frame-ancestors 'self'` and
 * `X-Frame-Options: SAMEORIGIN`, so embedding the hosted app renders a blank
 * box. The runs are listed from its API instead -- server-side, because the key
 * belongs there -- and each row deep links out to the full trace.
 *
 * A self-hosted instance on this origin *can* be framed, so NEXT_PUBLIC_LANGSMITH_URL
 * switches to an embed when it is set.
 */

interface TraceRun {
  id: string;
  name: string;
  status: string;
  start_time: string | null;
  latency_ms: number | null;
  tokens: number | null;
  error: string | null;
  url: string | null;
  tags: string[];
}

interface TracesResponse {
  tracing: TracingStatus;
  runs: TraceRun[];
  error: string | null;
}

const EMBED = process.env.NEXT_PUBLIC_LANGSMITH_URL;

export default function TracesPage() {
  const [data, setData] = useState<TracesResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(() => {
    setLoading(true);
    get<TracesResponse>("/agent/traces?limit=50")
      .then(setData)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  }, []);

  useEffect(load, [load]);

  if (EMBED) {
    return <iframe className="traces-embed" src={EMBED} title="LangSmith" />;
  }

  const tracing = data?.tracing;

  return (
    <main className="traces">
      <div className="target">
        <span className="target-stats">
          {tracing?.enabled ? `추적 켜짐 · ${tracing.project}` : "추적 꺼짐"}
        </span>
        <button type="button" className="btn" onClick={load} disabled={loading}>
          {loading ? "불러오는 중…" : "새로고침"}
        </button>
        <a
          className="btn"
          href={`https://smith.langchain.com/o/-/projects/p/${encodeURIComponent(tracing?.project ?? "")}`}
          target="_blank"
          rel="noreferrer"
        >
          LangSmith 열기 ↗
        </a>
        <span className="target-hint">
          LangSmith는 iframe 삽입을 막습니다(frame-ancestors self). 목록은 API로 가져옵니다.
        </span>
      </div>

      {tracing?.detail && <div className="ws-error ws-error-soft">{tracing.detail}</div>}
      {error && <div className="ws-error">{error}</div>}
      {data?.error && <div className="ws-error">LangSmith: {data.error}</div>}

      <div className="traces-body">
        {!tracing?.enabled ? (
          <div className="ws-empty ws-empty-lg">
            <p>추적이 꺼져 있습니다.</p>
            <pre className="traces-hint">
              {`export LANGSMITH_TRACING=true
export LANGSMITH_API_KEY=ls-...
# 프로세스를 시작하기 전에 설정해야 합니다 (langsmith가 환경변수를 캐시합니다)`}
            </pre>
          </div>
        ) : data && data.runs.length === 0 ? (
          <div className="ws-empty ws-empty-lg">아직 기록된 실행이 없습니다. 검사를 한 번 실행해 보세요.</div>
        ) : (
          <table className="traces-table">
            <thead>
              <tr>
                <th>이름</th>
                <th>상태</th>
                <th>지연</th>
                <th>토큰</th>
                <th>시작</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {(data?.runs ?? []).map((run) => (
                <tr key={run.id} className={run.error ? "is-error" : ""}>
                  <td className="mono">{run.name}</td>
                  <td>{run.error ? "실패" : run.status}</td>
                  <td className="num">{run.latency_ms !== null ? `${(run.latency_ms / 1000).toFixed(1)}s` : "—"}</td>
                  <td className="num">{run.tokens ?? "—"}</td>
                  <td className="mono small">
                    {run.start_time ? new Date(run.start_time).toLocaleString() : "—"}
                  </td>
                  <td>
                    {run.url && (
                      <a href={run.url} target="_blank" rel="noreferrer" className="traces-link">
                        열기 ↗
                      </a>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </main>
  );
}
