"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import Collapsible from "@/components/studio/Collapsible";
import ConversationView from "@/components/studio/ConversationView";
import RunHeader from "@/components/studio/RunHeader";
import RunSettingsBar from "@/components/studio/RunSettingsBar";
import SettingsModal from "@/components/studio/SettingsModal";
import SpanDetail from "@/components/studio/SpanDetail";
import Splitter from "@/components/studio/Splitter";
import type { Format, Granularity } from "@/components/studio/StepCard";
import ThreadPanel from "@/components/studio/ThreadPanel";
import TraceTree from "@/components/studio/TraceTree";
import SectionHeader from "@/components/shell/SectionHeader";
import {
  EMPTY_SUMMARY,
  NO_BREAKPOINTS,
  fetchCheckpoints,
  fetchGraph,
  fetchPrompts,
  fetchRun,
  fetchSpans,
  fetchState,
  fetchThreads,
  resumeRun,
  startRun,
  type Breakpoints,
  type Checkpoint,
  type GraphShape,
  type PromptRow,
  type RunSummary,
  type Span,
  type SpanSummary,
  type Thread,
} from "@/lib/api/studio";
import { MAX_GRAPH, MIN_GRAPH, usePanes } from "@/lib/studio/panes";
import { currentRun } from "@/lib/studio/session";
import { useRunStream } from "@/lib/studio/useRunStream";

/**
 * The trace: how the agent got to its answer, and how to make it answer better.
 *
 * One run -- the one this browser session put in. The runs directory is shared
 * by everyone using the server, so listing all of it would show other people's
 * work and bury yours; the run is carried over from the 검사 tab instead.
 *
 * The agent's structure sits above the trace and stays there: a trace is a long
 * list of calls, and knowing which of five nodes each came from is what makes it
 * readable. Clicking a node narrows the trace to it. Selecting a model call
 * opens it on the right, where the prompt can be changed and run again.
 */

// React Flow measures the DOM on mount, so it cannot be server-rendered.
const GraphCanvas = dynamic(() => import("@/components/studio/GraphCanvas"), {
  ssr: false,
  loading: () => <p className="sx-muted sx-pad">구조를 준비하는 중…</p>,
});

const ReactFlowProvider = dynamic(() => import("@xyflow/react").then((m) => m.ReactFlowProvider), { ssr: false });

const VIEWS = [
  { key: "tree", label: "호출 순서" },
  { key: "chat", label: "대화로 보기" },
] as const;

type View = (typeof VIEWS)[number]["key"];

export default function StudioPage() {
  const [runId, setRunId] = useState<string | null>(null);
  const [run, setRun] = useState<RunSummary | null>(null);
  const [shape, setShape] = useState<GraphShape | null>(null);
  const [prompts, setPrompts] = useState<PromptRow[]>([]);

  const [spans, setSpans] = useState<Span[]>([]);
  const [summary, setSummary] = useState<SpanSummary>(EMPTY_SUMMARY);
  const [threads, setThreads] = useState<Thread[]>([]);
  const [checkpoints, setCheckpoints] = useState<Checkpoint[]>([]);

  const [view, setView] = useState<View>("tree");
  const [spanId, setSpanId] = useState<string | null>(null);
  const [node, setNode] = useState<string | null>(null);
  const [step, setStep] = useState<string | null>(null);

  const [granularity, setGranularity] = useState<Granularity>(1);
  const [format, setFormat] = useState<Format>("pretty");
  const [breakpoints, setBreakpoints] = useState<Breakpoints>(NO_BREAKPOINTS);

  const [settings, setSettings] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [panes, setPanes] = usePanes();

  const live = useRunStream(runId);
  const fail = useCallback((err: unknown) => setError(err instanceof Error ? err.message : String(err)), []);

  /* -- this session's run -------------------------------------------------- */

  // Read on mount rather than during render: sessionStorage does not exist on
  // the server, and reading it in render would make the two disagree.
  useEffect(() => setRunId(currentRun()), []);

  useEffect(() => {
    fetchGraph().then(setShape).catch(fail);
    fetchPrompts()
      .then((d) => setPrompts(d.prompts))
      .catch(fail);
  }, [fail]);

  /* -- the run's own record ----------------------------------------------- */

  // Read once per run, then followed by `revision`, which the stream bumps when
  // a checkpoint lands. A page opened mid-run has missed the earlier events, so
  // the first read is what makes it correct and the stream is what keeps it so.
  useEffect(() => {
    if (!runId) return;
    let cancelled = false;

    Promise.all([
      fetchRun(runId),
      fetchSpans(runId),
      fetchThreads(runId),
      fetchCheckpoints(runId, granularity === 2),
    ])
      .then(([r, s, t, c]) => {
        if (cancelled) return;
        setRun(r);
        setSpans(s.spans);
        setSummary(s.summary);
        setThreads(t.threads);
        setCheckpoints(c.checkpoints);
        setError(null);
        // Land on the first model call: it is what someone opening a run wants
        // to read, and the only kind of span that can be tuned.
        setSpanId((current) => current ?? s.spans.find((x) => x.kind === "llm")?.id ?? null);
      })
      .catch((err: unknown) => !cancelled && fail(err));

    return () => {
      cancelled = true;
    };
  }, [runId, live.revision, granularity, fail]);

  /* -- driving the run ----------------------------------------------------- */

  const guard = useCallback(
    async (work: () => Promise<unknown>) => {
      setBusy(true);
      setError(null);
      try {
        await work();
      } catch (err) {
        fail(err);
      } finally {
        setBusy(false);
      }
    },
    [fail],
  );

  const submit = (force: boolean) => {
    if (!runId) return;
    void guard(async () => {
      // Attach before starting: the server ends the stream when a run finishes,
      // so a second run would otherwise execute with nobody watching.
      live.reconnect();
      await startRun(runId, { force, breakpoints });
      setStep(null);
    });
  };

  const carryOn = () => {
    if (!runId) return;
    void guard(async () => {
      live.reconnect();
      await resumeRun(runId, {});
    });
  };

  const cancel = () => {
    if (!runId) return;
    void guard(() => resumeRun(runId, { action: "abort" }));
  };

  const fork = (checkpointId: string, values: Record<string, unknown>) => {
    if (!runId) return;
    void guard(async () => {
      live.reconnect();
      await resumeRun(runId, { values, checkpointId, breakpoints });
      setStep(null);
    });
  };

  const rerun = (checkpointId: string) => {
    if (!runId) return;
    void guard(async () => {
      live.reconnect();
      await resumeRun(runId, { checkpointId, breakpoints });
      setStep(null);
    });
  };

  const loadFull = useCallback(
    async (checkpointId: string) => {
      if (!runId) return {};
      const state = await fetchState(runId, checkpointId);
      return state.values ?? {};
    },
    [runId],
  );

  const toggleBreakpoint = useCallback((name: string, when: "before" | "after") => {
    setBreakpoints((current) => {
      const list = current[when];
      const next = list.includes(name) ? list.filter((n) => n !== name) : [...list, name];
      return { ...current, [when]: next };
    });
  }, []);

  /* -- render -------------------------------------------------------------- */

  const span = spans.find((s) => s.id === spanId) ?? null;
  const head = checkpoints[checkpoints.length - 1]?.checkpoint_id ?? null;
  const current = step ?? head;
  const selectedStep = checkpoints.find((c) => c.checkpoint_id === current) ?? null;
  const queued = useMemo(
    () => (live.active ? live.queued : (selectedStep?.next ?? [])),
    [live.active, live.queued, selectedStep],
  );
  // A share of the centre column rather than a pixel height, so the graph keeps
  // its proportion of a tall screen and of a short one.
  const structureStyle = useMemo(
    () => (panes.graphOpen ? { flexBasis: `${panes.graph * 100}%` } : undefined),
    [panes.graphOpen, panes.graph],
  );

  if (!runId) {
    return (
      <>
        <SectionHeader
          title="에이전트"
          note="청크 단위 LLM 검사"
          views={[
            { href: "/agent", label: "검사" },
            { href: "/agent/studio", label: "트레이스" },
          ]}
        />
        <div className="tx-blank">
          <h2>추적할 실행이 없습니다</h2>
          <p>
            트레이스는 이 세션에서 검사한 코드만 보여줍니다. 서버에 남아 있는 다른 사람의 실행은 여기 나오지
            않습니다.
          </p>
          <Link className="sx-submit tx-blank-cta" href="/agent">
            검사 탭에서 코드 올리기
          </Link>
        </div>
      </>
    );
  }

  return (
    <>
      <SectionHeader
        title="에이전트"
        note="청크 단위 LLM 검사"
        views={[
          { href: "/agent", label: "검사" },
          { href: "/agent/studio", label: "트레이스" },
        ]}
      >
        <span className="target-hint">이 세션의 실행만 · 로컬 기록 · 외부 전송 없음</span>
      </SectionHeader>

      <RunHeader run={run} summary={summary} steps={checkpoints.length} live={live}>
        <RunSettingsBar
          steppable={shape?.steppable ?? []}
          breakpoints={breakpoints}
          onToggleBreakpoint={toggleBreakpoint}
          onClearBreakpoints={() => setBreakpoints(NO_BREAKPOINTS)}
          onSubmit={submit}
          onResume={carryOn}
          onAbort={cancel}
          onOpenSettings={() => setSettings(true)}
          running={live.active && !live.interrupted}
          interrupted={live.interrupted}
          busy={busy}
          disabled={!runId}
        />
      </RunHeader>

      {error && <div className="ws-error">{error}</div>}

      <div className={`tx ${panes.detailOpen ? "" : "is-narrow"}`}>
        <section className="tx-centre">
          <section className={`tx-structure ${panes.graphOpen ? "is-open" : ""}`} style={structureStyle}>
            <header className="tx-structure-head">
              <button
                type="button"
                className="tx-fold-caret-btn"
                aria-expanded={panes.graphOpen}
                onClick={() => setPanes({ graphOpen: !panes.graphOpen })}
              >
                <span className="tx-fold-caret">{panes.graphOpen ? "▾" : "▸"}</span>
                <span className="sx-pane-title">에이전트 구조</span>
              </button>
              {panes.graphOpen && (
                <span className="sx-muted">노드를 누르면 그 노드의 호출만 남습니다 · + 로 중단점</span>
              )}
              {live.running.length > 1 && <span className="tx-parallel">{live.running.length}개 동시 실행</span>}
            </header>
            {panes.graphOpen && (
              <div className="tx-graph">
                {shape ? (
                  <ReactFlowProvider>
                    <GraphCanvas
                      shape={shape}
                      spans={spans}
                      running={live.running}
                      queued={queued}
                      breakpoints={breakpoints}
                      selected={node}
                      onSelect={setNode}
                      onInterrupt={toggleBreakpoint}
                      direction="LR"
                    />
                  </ReactFlowProvider>
                ) : (
                  <p className="sx-muted sx-pad">구조를 불러오는 중…</p>
                )}
              </div>
            )}
          </section>

          {panes.graphOpen && (
            <Splitter
              value={panes.graph}
              onChange={(share) => setPanes({ graph: share })}
              min={MIN_GRAPH}
              max={MAX_GRAPH}
              label="구조와 호출 기록의 높이 비율"
            />
          )}

          <div className="tx-trace">
            <div className="tx-trace-head">
              <span className="sx-pane-title">호출 기록</span>
              <div className="sx-seg">
                {VIEWS.map((v) => (
                  <button
                    key={v.key}
                    type="button"
                    className={`sx-seg-btn ${view === v.key ? "is-on" : ""}`}
                    onClick={() => setView(v.key)}
                  >
                    {v.label}
                  </button>
                ))}
              </div>
              {node && (
                <button type="button" className="sx-scope" onClick={() => setNode(null)}>
                  {node} 만 보는 중 ✕
                </button>
              )}
            </div>

            <div className="tx-trace-body">
              {view === "tree" ? (
                <TraceTree spans={spans} selected={spanId} onSelect={setSpanId} node={node} />
              ) : (
                <ConversationView threads={threads} node={node} />
              )}
            </div>
          </div>

          <Collapsible
            title="상태 단계"
            note={checkpoints.length ? `${checkpoints.length}` : undefined}
            open={panes.stepsOpen}
            onToggle={(open) => setPanes({ stepsOpen: open })}
          >
            <div className="tx-steps">
              <ThreadPanel
                checkpoints={checkpoints}
                selected={current}
                onSelectStep={setStep}
                granularity={granularity}
                onGranularity={setGranularity}
                format={format}
                onFormat={setFormat}
                onFork={fork}
                onRerun={rerun}
                loadFull={loadFull}
                busy={busy}
                interrupted={live.interrupted}
              />
            </div>
          </Collapsible>
        </section>

        <aside className={`tx-detail-pane ${panes.detailOpen ? "" : "is-closed"}`}>
          <button
            type="button"
            className="tx-detail-toggle"
            aria-expanded={panes.detailOpen}
            title={panes.detailOpen ? "선택한 호출 접기" : "선택한 호출 펼치기"}
            onClick={() => setPanes({ detailOpen: !panes.detailOpen })}
          >
            {panes.detailOpen ? "›" : "‹"}
          </button>
          {panes.detailOpen && <SpanDetail runId={runId} span={span} prompts={prompts} onPrompts={setPrompts} />}
        </aside>
      </div>

      {settings && <SettingsModal onClose={() => setSettings(false)} />}
    </>
  );
}
