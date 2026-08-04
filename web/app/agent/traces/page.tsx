"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import type { TracingStatus } from "@/lib/api/agent";
import SectionHeader from "@/components/shell/SectionHeader";
import { get } from "@/lib/http";

/**
 * Agent traces: the run list, the span tree, and what each span sent and got
 * back -- rendered here rather than linked out to.
 *
 * LangSmith cannot be embedded (it serves `frame-ancestors 'self'`), and a
 * redirect is not a view. Its API returns every span of a trace with
 * `parent_run_id` and `dotted_order`, which is enough to rebuild the tree, so
 * the structure and the tool calls are shown in place. The row still links out
 * for the full payload.
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
}

interface Span {
  id: string;
  parent_id: string | null;
  name: string;
  run_type: string;
  status: string;
  error: string | null;
  latency_ms: number | null;
  tokens: number | null;
  metadata: Record<string, unknown>;
  inputs: unknown;
  outputs: unknown;
  url: string | null;
}

const EMBED = process.env.NEXT_PUBLIC_LANGSMITH_URL;

function kindClass(runType: string): string {
  if (runType === "llm" || runType === "chat_model") return "k-llm";
  if (runType === "tool") return "k-tool";
  if (runType === "chain") return "k-chain";
  return "k-other";
}

/** Depth per span, from parent links, so the tree can be indented. */
function depths(spans: Span[]): Map<string, number> {
  const byId = new Map(spans.map((s) => [s.id, s]));
  const out = new Map<string, number>();
  const depthOf = (span: Span): number => {
    if (out.has(span.id)) return out.get(span.id)!;
    const parent = span.parent_id ? byId.get(span.parent_id) : undefined;
    const d = parent ? depthOf(parent) + 1 : 0;
    out.set(span.id, d);
    return d;
  };
  spans.forEach(depthOf);
  return out;
}

/**
 * Tool calls the model asked for on this span.
 *
 * They live in the LLM span's output as `tool_calls`, not as children, so the
 * tree alone does not show what was requested -- only what ran.
 */
function toolCalls(span: Span): { name: string; args: unknown }[] {
  const seen: { name: string; args: unknown }[] = [];
  const walk = (value: unknown, depth = 0) => {
    if (depth > 6 || !value || typeof value !== "object") return;
    if (Array.isArray(value)) {
      value.forEach((v) => walk(v, depth + 1));
      return;
    }
    const obj = value as Record<string, unknown>;
    if (Array.isArray(obj.tool_calls)) {
      for (const call of obj.tool_calls as Record<string, unknown>[]) {
        const name = (call.name ?? (call.function as Record<string, unknown>)?.name) as string | undefined;
        if (name) seen.push({ name, args: call.args ?? (call.function as Record<string, unknown>)?.arguments });
      }
    }
    Object.values(obj).forEach((v) => walk(v, depth + 1));
  };
  walk(span.outputs);
  return seen;
}

function pretty(value: unknown): string {
  if (value === null || value === undefined) return "—";
  return typeof value === "string" ? value : JSON.stringify(value, null, 2);
}

export default function TracesPage() {
  const [tracing, setTracing] = useState<TracingStatus | null>(null);
  const [runs, setRuns] = useState<TraceRun[]>([]);
  const [listError, setListError] = useState<string | null>(null);
  const [traceId, setTraceId] = useState<string | null>(null);
  const [spans, setSpans] = useState<Span[]>([]);
  const [spanId, setSpanId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(() => {
    setLoading(true);
    get<{ tracing: TracingStatus; runs: TraceRun[]; error: string | null }>("/agent/traces?limit=50")
      .then((d) => {
        setTracing(d.tracing);
        setRuns(d.runs);
        setListError(d.error);
      })
      .catch((e: unknown) => setListError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  }, []);

  useEffect(load, [load]);

  const openTrace = useCallback((id: string) => {
    setTraceId(id);
    setSpans([]);
    setSpanId(null);
    get<{ spans: Span[] }>(`/agent/traces/${id}`)
      .then((d) => {
        setSpans(d.spans);
        setSpanId(d.spans[0]?.id ?? null);
      })
      .catch((e: unknown) => setListError(e instanceof Error ? e.message : String(e)));
  }, []);

  const indent = useMemo(() => depths(spans), [spans]);
  const span = spans.find((s) => s.id === spanId) ?? null;
  const calls = span ? toolCalls(span) : [];

  if (EMBED) return <iframe className="traces-embed" src={EMBED} title="LangSmith" />;

  return (
    <>
      <SectionHeader
        title="에이전트"
        note="청크 단위 LLM 검사"
        views={[
          { href: "/agent", label: "검사" },
          { href: "/agent/traces", label: "실행 기록" },
        ]}
      >
        <span className="target-stats">
          {tracing?.enabled ? `추적 켜짐 · ${tracing.project}` : "추적 꺼짐"}
        </span>
        <button type="button" className="btn" onClick={load} disabled={loading}>
          {loading ? "불러오는 중…" : "새로고침"}
        </button>
        {span?.url && (
          <a className="btn btn-ghost" href={span.url} target="_blank" rel="noreferrer">
            LangSmith에서 열기 ↗
          </a>
        )}
        <span className="target-hint">실행 구조와 도구 호출</span>
      </SectionHeader>

      {tracing?.detail && <div className="ws-error ws-error-soft">{tracing.detail}</div>}
      {listError && <div className="ws-error">{listError}</div>}

      {!tracing?.enabled ? (
        <div className="ws-empty ws-empty-lg">
          <p>추적이 꺼져 있습니다.</p>
          <pre className="span-io" style={{ maxWidth: 520 }}>
            {`export LANGSMITH_TRACING=true
export LANGSMITH_API_KEY=ls-...

프로세스를 시작하기 전에 설정하세요.
langsmith가 환경변수를 한 번만 읽습니다.`}
          </pre>
        </div>
      ) : (
        <div className="traces">
          <aside className="traces-runs">
            <div className="ws-pane-title">실행 {runs.length}</div>
            <div className="traces-list">
              {runs.length === 0 && <p className="ws-empty">아직 기록된 실행이 없습니다.</p>}
              {runs.map((run) => (
                <button
                  key={run.id}
                  type="button"
                  className={`trace-run ${run.id === traceId ? "is-selected" : ""} ${run.error ? "is-error" : ""}`}
                  onClick={() => openTrace(run.id)}
                >
                  <span className="trace-run-name">{run.name}</span>
                  <span className="span-ms">
                    {run.latency_ms !== null ? `${(run.latency_ms / 1000).toFixed(1)}s` : "—"}
                  </span>
                  <span className="trace-run-meta">
                    {run.start_time ? new Date(run.start_time).toLocaleTimeString() : "—"}
                    {run.tokens ? ` · ${run.tokens} tok` : ""}
                    {run.error ? " · 실패" : ""}
                  </span>
                </button>
              ))}
            </div>
          </aside>

          {!traceId ? (
            <div className="ws-empty ws-empty-lg">왼쪽에서 실행을 선택하세요.</div>
          ) : (
            <div className="traces-detail">
              <div className="span-tree">
                <div className="ws-pane-title">실행 구조 · {spans.length} 스팬</div>
                {spans.map((s) => (
                  <button
                    key={s.id}
                    type="button"
                    className={`span-row ${s.id === spanId ? "is-selected" : ""} ${s.error ? "is-error" : ""}`}
                    onClick={() => setSpanId(s.id)}
                  >
                    <span className="span-name" style={{ paddingLeft: (indent.get(s.id) ?? 0) * 14 }}>
                      <span className={`span-kind ${kindClass(s.run_type)}`}>{s.run_type}</span>
                      {s.name}
                    </span>
                    <span className="span-tok">{s.tokens ? `${s.tokens} tok` : ""}</span>
                    <span className="span-ms">
                      {s.latency_ms !== null ? `${(s.latency_ms / 1000).toFixed(2)}s` : ""}
                    </span>
                  </button>
                ))}
              </div>

              <div className="span-detail">
                {!span ? (
                  <p className="ws-empty">스팬을 선택하세요.</p>
                ) : (
                  <>
                    <div className="span-meta">
                      <span>{span.run_type}</span>
                      <span>{span.latency_ms !== null ? `${(span.latency_ms / 1000).toFixed(2)}s` : "—"}</span>
                      <span>{span.tokens ? `${span.tokens} tok` : ""}</span>
                      {Object.entries(span.metadata ?? {})
                        .filter(([, v]) => typeof v === "string" || typeof v === "number")
                        .slice(0, 4)
                        .map(([k, v]) => (
                          <span key={k}>
                            {k}={String(v)}
                          </span>
                        ))}
                    </div>

                    {span.error && (
                      <>
                        <h3>오류</h3>
                        <pre className="span-io">{span.error}</pre>
                      </>
                    )}

                    {calls.length > 0 && (
                      <>
                        <h3>도구 호출 {calls.length}</h3>
                        {calls.map((call, i) => (
                          <div key={`${call.name}-${i}`} className="toolcall">
                            <div className="toolcall-name">{call.name}</div>
                            <pre className="toolcall-args">{pretty(call.args)}</pre>
                          </div>
                        ))}
                      </>
                    )}

                    <h3>입력</h3>
                    <pre className="span-io">{pretty(span.inputs)}</pre>
                    <h3>출력</h3>
                    <pre className="span-io">{pretty(span.outputs)}</pre>
                  </>
                )}
              </div>
            </div>
          )}
        </div>
      )}
    </>
  );
}
