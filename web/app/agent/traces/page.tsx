"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import type { RunSummary, Span, SpanSummary } from "@/lib/api/agent";
import { fetchSpans, listRuns } from "@/lib/api/agent";
import SectionHeader from "@/components/shell/SectionHeader";

/**
 * The debug view: what the agent actually did, call by call.
 *
 * Read from this machine's own span store, not from LangSmith. The hosted view
 * serves `frame-ancestors 'self'` so it cannot be embedded, needs an account,
 * and would mean shipping prompts and source off the box -- none of which is
 * acceptable for a view a user is meant to open. Everything here is recorded
 * locally by the run that produced it.
 */

const EMPTY: SpanSummary = { spans: 0, llm_calls: 0, tool_calls: 0, errors: 0, running: 0, tokens: 0, total_ms: 0 };

//: A run in flight fills its trace over minutes; watching it is the point.
const POLL_MS = 2000;

type Kind = "all" | "llm" | "tool" | "chain";

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

/**
 * Tool calls the model asked for on this span.
 *
 * Requests live in the LLM span's output; the results are separate `tool` spans
 * underneath it. Showing both together is what makes a verify step readable.
 */
function requestedCalls(span: Span): { name: string; args: unknown }[] {
  const outputs = span.outputs as { tool_calls?: Record<string, unknown>[] } | null;
  if (!outputs?.tool_calls) return [];
  return outputs.tool_calls.map((call) => ({
    name: String(call.name ?? "tool"),
    args: call.args ?? call.arguments,
  }));
}

function pretty(value: unknown): string {
  if (value === null || value === undefined) return "—";
  return typeof value === "string" ? value : JSON.stringify(value, null, 2);
}

/** Chat messages render as a conversation; anything else as JSON. */
function messagesOf(span: Span): { role: string; content: string }[] | null {
  const inputs = span.inputs as { messages?: { role: string; content: string }[] } | null;
  return Array.isArray(inputs?.messages) ? inputs.messages : null;
}

function completionOf(span: Span): string | null {
  const outputs = span.outputs as { text?: string[] } | null;
  return outputs?.text?.length ? outputs.text.join("\n") : null;
}

/** ``?run=`` so a trace can be linked to, and so the inspect page can hand off. */
function requestedRun(): string | null {
  if (typeof window === "undefined") return null;
  return new URLSearchParams(window.location.search).get("run");
}

export default function TracesPage() {
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [runId, setRunId] = useState<string | null>(null);
  const [spans, setSpans] = useState<Span[]>([]);
  const [summary, setSummary] = useState<SpanSummary>(EMPTY);
  const [spanId, setSpanId] = useState<string | null>(null);
  const [kind, setKind] = useState<Kind>("all");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const live = useRef(false);

  const loadRuns = useCallback(() => {
    setLoading(true);
    listRuns()
      .then((d) => {
        setRuns(d.runs);
        setRunId((current) => current ?? requestedRun() ?? d.runs[0]?.run_id ?? null);
      })
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  }, []);

  useEffect(loadRuns, [loadRuns]);

  const loadSpans = useCallback((id: string) => {
    return fetchSpans(id)
      .then((d) => {
        setSpans(d.spans);
        setSummary(d.summary);
        setError(null);
        // Open on the first model call rather than the graph root: the root
        // carries no payload, so landing there looks like an empty trace.
        setSpanId((current) => current ?? d.spans.find((s) => s.kind === "llm")?.id ?? d.spans[0]?.id ?? null);
        return d.summary;
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
      void loadSpans(runId).then((s) => {
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
  }, [runId, loadSpans]);

  const indent = useMemo(() => depths(spans), [spans]);
  const shown = useMemo(() => (kind === "all" ? spans : spans.filter((s) => s.kind === kind)), [spans, kind]);
  const span = spans.find((s) => s.id === spanId) ?? null;
  const calls = span ? requestedCalls(span) : [];
  const children = span ? spans.filter((s) => s.parent_id === span.id && s.kind === "tool") : [];
  const messages = span ? messagesOf(span) : null;
  const completion = span ? completionOf(span) : null;

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
          {summary.spans}개 스팬 · LLM {summary.llm_calls} · 도구 {summary.tool_calls}
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
            {runs.map((run) => (
              <button
                key={run.run_id}
                type="button"
                className={`trace-run ${run.run_id === runId ? "is-selected" : ""} ${run.error ? "is-error" : ""}`}
                onClick={() => {
                  setRunId(run.run_id);
                  window.history.replaceState(null, "", `?run=${run.run_id}`);
                }}
              >
                <span className="trace-run-name">{run.run_id}</span>
                <span className="span-ms">{run.findings !== undefined ? `${run.findings}건` : ""}</span>
                <span className="trace-run-meta">
                  {run.status ?? "—"}
                  {run.index?.chunks ? ` · 청크 ${run.index.chunks}` : ""}
                </span>
              </button>
            ))}
          </div>
        </aside>

        {!runId ? (
          <div className="ws-empty ws-empty-lg">왼쪽에서 실행을 선택하세요.</div>
        ) : spans.length === 0 ? (
          <div className="ws-empty ws-empty-lg">
            <p>이 실행에는 기록된 스팬이 없습니다.</p>
            <p className="ws-empty-note">검사를 실행하면 모델 호출과 도구 호출이 여기에 쌓입니다.</p>
          </div>
        ) : (
          <div className="traces-detail">
            <div className="span-tree">
              <div className="ws-pane-title">
                <span>
                  실행 구조 · {shown.length} 스팬
                  {summary.running > 0 ? ` · 진행 중 ${summary.running}` : ""}
                </span>
                <span className="span-filters">
                  {(["all", "chain", "llm", "tool"] as Kind[]).map((k) => (
                    <button
                      key={k}
                      type="button"
                      className={`chip ${kind === k ? "is-on" : ""}`}
                      onClick={() => setKind(k)}
                    >
                      {k === "all" ? "전체" : k}
                    </button>
                  ))}
                </span>
              </div>
              {shown.map((s) => (
                <button
                  key={s.id}
                  type="button"
                  className={`span-row ${s.id === spanId ? "is-selected" : ""} ${s.status === "error" ? "is-error" : ""}`}
                  onClick={() => setSpanId(s.id)}
                >
                  <span className="span-name" style={{ paddingLeft: (kind === "all" ? indent.get(s.id) ?? 0 : 0) * 14 }}>
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

                  {calls.length > 0 && (
                    <>
                      <h3>요청한 도구 {calls.length}</h3>
                      {calls.map((call, i) => (
                        <div key={`${call.name}-${i}`} className="toolcall">
                          <div className="toolcall-name">{call.name}</div>
                          <pre className="toolcall-args">{pretty(call.args)}</pre>
                        </div>
                      ))}
                    </>
                  )}

                  {children.length > 0 && (
                    <>
                      <h3>도구 결과 {children.length}</h3>
                      {children.map((child) => (
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
        )}
      </div>
    </>
  );
}
