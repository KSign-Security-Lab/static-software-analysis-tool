"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import type { Checkpoint, GraphShape, RunSummary, Span, SpanSummary, Thread } from "@/lib/api/agent";
import { fetchCheckpoints, fetchGraph, fetchSpans, fetchThreads, listRuns } from "@/lib/api/agent";
import GraphView from "@/components/agent/GraphView";
import StepsView from "@/components/agent/StepsView";
import ThreadView from "@/components/agent/ThreadView";
import SectionHeader from "@/components/shell/SectionHeader";

/**
 * The debug view: what the agent is, what it said, where it went, what it did.
 *
 * This is the local equivalent of LangGraph Studio -- the graph, the thread and
 * the checkpoints -- because the hosted one is not an option here. It serves
 * `frame-ancestors 'self'` so it cannot be embedded, it needs a LangSmith
 * account, and pointing it at a local server would still mean shipping prompts
 * and source off the box. Everything below is recorded by the run itself, and
 * every view is scoped to one run.
 */

const EMPTY: SpanSummary = { spans: 0, llm_calls: 0, tool_calls: 0, errors: 0, running: 0, tokens: 0, total_ms: 0 };

//: A run in flight fills its history over minutes; watching it is the point.
const POLL_MS = 2000;

const VIEWS = [
  { key: "graph", label: "구조" },
  { key: "thread", label: "대화" },
  { key: "steps", label: "단계" },
  { key: "trace", label: "트레이스" },
] as const;

type View = (typeof VIEWS)[number]["key"];

function kindClass(kind: string): string {
  if (kind === "llm") return "k-llm";
  if (kind === "tool") return "k-tool";
  if (kind === "chain") return "k-chain";
  return "k-other";
}

function seconds(ms: number | null): string {
  if (ms === null) return "";
  return ms < 1000 ? `${ms}ms` : `${(ms / 1000).toFixed(2)}s`;
}

/** Depth per span, from parent links, so the tree can be indented. */
function depths(spans: Span[]): Map<string, number> {
  const byId = new Map(spans.map((s) => [s.id, s]));
  const out = new Map<string, number>();
  const depthOf = (span: Span): number => {
    const known = out.get(span.id);
    if (known !== undefined) return known;
    // Guard against a parent chain that never terminates: a truncated trace
    // can reference a parent whose start was never written.
    out.set(span.id, 0);
    const parent = span.parent_id ? byId.get(span.parent_id) : undefined;
    const d = parent ? depthOf(parent) + 1 : 0;
    out.set(span.id, d);
    return d;
  };
  spans.forEach(depthOf);
  return out;
}

function pretty(value: unknown): string {
  if (value === null || value === undefined) return "—";
  return typeof value === "string" ? value : JSON.stringify(value, null, 2);
}

/** ``?run=&view=`` so a view of a run can be linked to, not just reached. */
function fromUrl(key: string): string | null {
  if (typeof window === "undefined") return null;
  return new URLSearchParams(window.location.search).get(key);
}

function putUrl(run: string | null, view: View): void {
  const params = new URLSearchParams();
  if (run) params.set("run", run);
  params.set("view", view);
  window.history.replaceState(null, "", `?${params}`);
}

export default function TracesPage() {
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [runId, setRunId] = useState<string | null>(null);
  const [view, setView] = useState<View>("graph");

  // Read once on mount: the URL seeds the view, the chips own it after that.
  useEffect(() => {
    const wanted = fromUrl("view");
    if (VIEWS.some((v) => v.key === wanted)) setView(wanted as View);
  }, []);

  const [shape, setShape] = useState<GraphShape | null>(null);
  const [spans, setSpans] = useState<Span[]>([]);
  const [summary, setSummary] = useState<SpanSummary>(EMPTY);
  const [threads, setThreads] = useState<Thread[]>([]);
  const [checkpoints, setCheckpoints] = useState<Checkpoint[]>([]);

  const [spanId, setSpanId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const live = useRef(false);

  const loadRuns = useCallback(() => {
    setLoading(true);
    listRuns()
      .then((d) => {
        setRuns(d.runs);
        setRunId((current) => current ?? fromUrl("run") ?? d.runs[0]?.run_id ?? null);
      })
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  }, []);

  useEffect(loadRuns, [loadRuns]);

  // The graph is a property of the code, so it is fetched once and survives
  // switching runs -- it is also the one view that works with no run at all.
  useEffect(() => {
    fetchGraph()
      .then(setShape)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)));
  }, []);

  const loadRun = useCallback((id: string) => {
    return Promise.all([fetchSpans(id), fetchThreads(id), fetchCheckpoints(id)])
      .then(([s, t, c]) => {
        setSpans(s.spans);
        setSummary(s.summary);
        setThreads(t.threads);
        setCheckpoints(c.checkpoints);
        setError(null);
        setSpanId((current) => current ?? s.spans.find((x) => x.kind === "llm")?.id ?? s.spans[0]?.id ?? null);
        return s.summary;
      })
      .catch((e: unknown) => {
        setError(e instanceof Error ? e.message : String(e));
        return null;
      });
  }, []);

  useEffect(() => {
    if (!runId) return;
    setSpanId(null);
    let cancelled = false;

    const tick = () => {
      void loadRun(runId).then((s) => {
        // Keep polling only while something is still open, so a finished run
        // costs one request rather than one every two seconds forever.
        live.current = !cancelled && !!s && s.running > 0;
      });
    };

    tick();
    const timer = window.setInterval(() => live.current && tick(), POLL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [runId, loadRun]);

  const indent = useMemo(() => depths(spans), [spans]);
  const span = spans.find((s) => s.id === spanId) ?? null;
  const toolChildren = span ? spans.filter((s) => s.parent_id === span.id && s.kind === "tool") : [];
  const run = runs.find((r) => r.run_id === runId) ?? null;

  const messages = (span?.inputs as { messages?: { role: string; content: string }[] } | null)?.messages ?? null;
  const completion = (span?.outputs as { text?: string[] } | null)?.text?.join("\n") ?? null;
  const requested = (span?.outputs as { tool_calls?: { name?: string; args?: unknown }[] } | null)?.tool_calls ?? [];

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
          {summary.spans}개 스팬 · LLM {summary.llm_calls} · 도구 {summary.tool_calls} · 단계 {checkpoints.length}
          {summary.tokens > 0 ? ` · ${summary.tokens.toLocaleString()} tok` : ""}
          {summary.errors > 0 ? ` · 오류 ${summary.errors}` : ""}
        </span>
        <button type="button" className="btn" onClick={loadRuns} disabled={loading}>
          {loading ? "불러오는 중…" : "새로고침"}
        </button>
        <span className="target-hint">로컬 기록 · 외부 전송 없음</span>
      </SectionHeader>

      {error && <div className="ws-error">{error}</div>}

      <div className="traces">
        <aside className="traces-runs">
          <div className="ws-pane-title">실행 {runs.length}</div>
          <div className="traces-list">
            {runs.length === 0 && <p className="ws-empty">아직 실행이 없습니다. 먼저 소스를 검사하세요.</p>}
            {runs.map((r) => (
              <button
                key={r.run_id}
                type="button"
                className={`trace-run ${r.run_id === runId ? "is-selected" : ""} ${r.error ? "is-error" : ""}`}
                onClick={() => {
                  setRunId(r.run_id);
                  putUrl(r.run_id, view);
                }}
              >
                <span className="trace-run-name">{r.run_id}</span>
                <span className="span-ms">{r.findings !== undefined ? `${r.findings}건` : ""}</span>
                <span className="trace-run-meta">
                  {r.status ?? "—"}
                  {r.index?.chunks ? ` · 청크 ${r.index.chunks}` : ""}
                </span>
              </button>
            ))}
          </div>
        </aside>

        <div className="traces-detail-wrap">
          {/* The run this whole panel is about, stated once. Every view below
              reads that run's own files and nothing else. */}
          <div className="run-bar">
            <span className="run-bar-id">{runId ?? "—"}</span>
            {run?.status && <span className="chip">{run.status}</span>}
            {run?.findings !== undefined && <span className="chip">결과 {run.findings}건</span>}
            {summary.running > 0 && <span className="chip is-on">진행 중 {summary.running}</span>}
            <span className="span-filters">
              {VIEWS.map((v) => (
                <button
                  key={v.key}
                  type="button"
                  className={`chip ${view === v.key ? "is-on" : ""}`}
                  onClick={() => {
                    setView(v.key);
                    putUrl(runId, v.key);
                  }}
                >
                  {v.label}
                </button>
              ))}
            </span>
          </div>

          {view === "graph" &&
            (shape ? <GraphView shape={shape} spans={spans} /> : <p className="ws-empty">그래프를 불러오는 중…</p>)}

          {view === "thread" && <ThreadView threads={threads} />}

          {view === "steps" && <StepsView checkpoints={checkpoints} />}

          {view === "trace" &&
            (spans.length === 0 ? (
              <div className="ws-empty ws-empty-lg">
                <p>이 실행에는 기록된 스팬이 없습니다.</p>
                <p className="ws-empty-note">검사를 실행하면 모델 호출과 도구 호출이 여기에 쌓입니다.</p>
              </div>
            ) : (
              <div className="traces-detail">
                <div className="span-tree">
                  {spans.map((s) => (
                    <button
                      key={s.id}
                      type="button"
                      className={`span-row ${s.id === spanId ? "is-selected" : ""} ${s.status === "error" ? "is-error" : ""}`}
                      onClick={() => setSpanId(s.id)}
                    >
                      <span className="span-name" style={{ paddingLeft: (indent.get(s.id) ?? 0) * 14 }}>
                        <span className={`span-kind ${kindClass(s.kind)}`}>{s.kind}</span>
                        {s.name}
                      </span>
                      <span className="span-tok">{s.tokens ? `${s.tokens} tok` : ""}</span>
                      <span className="span-ms">{s.status === "running" ? "진행 중" : seconds(s.latency_ms)}</span>
                    </button>
                  ))}
                </div>

                <div className="span-detail">
                  {!span ? (
                    <p className="ws-empty">스팬을 선택하세요.</p>
                  ) : (
                    <>
                      <div className="span-meta">
                        <span>{span.kind}</span>
                        <span>{span.status === "running" ? "진행 중" : seconds(span.latency_ms) || "—"}</span>
                        {span.tokens ? <span>{span.tokens} tok</span> : null}
                        {Object.entries(span.meta ?? {})
                          .filter(([, v]) => typeof v === "string" || typeof v === "number")
                          .slice(0, 5)
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

                      {requested.length > 0 && (
                        <>
                          <h3>요청한 도구 {requested.length}</h3>
                          {requested.map((call, i) => (
                            <div key={`${call.name}-${i}`} className="toolcall">
                              <div className="toolcall-name">{call.name}</div>
                              <pre className="toolcall-args">{pretty(call.args)}</pre>
                            </div>
                          ))}
                        </>
                      )}

                      {toolChildren.length > 0 && (
                        <>
                          <h3>도구 결과 {toolChildren.length}</h3>
                          {toolChildren.map((child) => (
                            <div key={child.id} className="toolcall">
                              <div className="toolcall-name">
                                {child.name}
                                <span className="span-ms"> {seconds(child.latency_ms)}</span>
                              </div>
                              <pre className="toolcall-args">{pretty(child.outputs ?? child.error)}</pre>
                            </div>
                          ))}
                        </>
                      )}

                      {messages ? (
                        <>
                          <h3>프롬프트 {messages.length}</h3>
                          {messages.map((message, i) => (
                            <div key={i} className="msg">
                              <div className="msg-role">{message.role}</div>
                              <pre className="span-io">{message.content}</pre>
                            </div>
                          ))}
                        </>
                      ) : (
                        <>
                          <h3>입력</h3>
                          <pre className="span-io">{pretty(span.inputs)}</pre>
                        </>
                      )}

                      <h3>출력</h3>
                      <pre className="span-io">{completion ?? pretty(span.outputs)}</pre>
                    </>
                  )}
                </div>
              </div>
            ))}
        </div>
      </div>
    </>
  );
}
