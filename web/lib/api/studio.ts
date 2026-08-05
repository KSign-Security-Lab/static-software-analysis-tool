/**
 * The studio's line to the backend: what the graph is, where a run got to, and
 * how to steer it.
 *
 * Separate from `lib/api/agent.ts`, which is the inspect page's line -- upload,
 * edit, findings. Everything here is about watching and driving a run rather
 * than producing one.
 */

import { del, get, post, put, streamUrl } from "@/lib/http";

/** The inspection graph. A property of the code, not of any run. */
export interface GraphShape {
  nodes: string[];
  edges: { source: string; target: string; conditional: boolean }[];
  mermaid: string;
  /** The real nodes, without LangGraph's markers -- what a breakpoint may name. */
  steppable: string[];
}

export function fetchGraph(): Promise<GraphShape> {
  return get<GraphShape>("/agent/graph");
}

/** One recorded call: a node, a model call, or a tool call under one. */
export interface Span {
  id: string;
  parent_id: string | null;
  seq: number;
  name: string;
  kind: "chain" | "llm" | "tool" | string;
  status: "running" | "ok" | "error";
  error: string | null;
  /** Unix seconds. What lets the trace be drawn against the wall clock. */
  started_at: number;
  latency_ms: number | null;
  tokens: number | null;
  meta: Record<string, unknown>;
  inputs: unknown;
  outputs: unknown;
}

export interface SpanSummary {
  spans: number;
  llm_calls: number;
  tool_calls: number;
  errors: number;
  running: number;
  tokens: number;
  total_ms: number;
}

export const EMPTY_SUMMARY: SpanSummary = {
  spans: 0,
  llm_calls: 0,
  tool_calls: 0,
  errors: 0,
  running: 0,
  tokens: 0,
  total_ms: 0,
};

export function fetchSpans(runId: string): Promise<{ run_id: string; spans: Span[]; summary: SpanSummary }> {
  return get(`/agent/runs/${runId}/spans`);
}

/** One model call as an exchange, for the conversation view. */
export interface Turn {
  id: string;
  step: string;
  name: string;
  messages: { role: string; content: string }[];
  reply: string | null;
  tool_calls: { name?: string; args?: unknown }[];
  tools: { name: string; inputs: unknown; outputs: unknown; error: string | null; latency_ms: number | null }[];
  latency_ms: number | null;
  tokens: number | null;
  error: string | null;
}

export interface Thread {
  id: string;
  symbol: string | null;
  file: string | null;
  turns: Turn[];
  tokens: number;
}

export function fetchThreads(runId: string): Promise<{ run_id: string; threads: Thread[] }> {
  return get(`/agent/runs/${runId}/thread`);
}

/**
 * The graph's state after one super-step.
 *
 * `parent_checkpoint_id` is what makes the history a tree: writing over an old
 * step branches there rather than overwriting it, and the pointer is the only
 * thing that relationship can be drawn from.
 */
export interface Checkpoint {
  checkpoint_id: string | null;
  parent_checkpoint_id: string | null;
  step: number | null;
  source: string | null;
  node: string | null;
  nodes: string[];
  next: string[];
  created_at: string | null;
  values: Record<string, unknown>;
}

export function fetchCheckpoints(
  runId: string,
  full = false,
): Promise<{ run_id: string; checkpoints: Checkpoint[]; count: number }> {
  return get(`/agent/runs/${runId}/checkpoints${full ? "?full=true" : ""}`);
}

/**
 * The state a fresh run would begin from.
 *
 * Shown as the run's input before there is a run, so it cannot come from a
 * checkpoint -- it is computed from the index.
 */
export function fetchInput(runId: string): Promise<{ run_id: string; values: Record<string, unknown> }> {
  return get(`/agent/runs/${runId}/input`);
}

/**
 * One checkpoint's state in full. The timeline gets summarised values, which is
 * right for reading and useless for editing -- a count cannot be edited back
 * into a list.
 */
export function fetchState(runId: string, checkpointId?: string | null): Promise<Checkpoint & { run_id: string }> {
  const query = checkpointId ? `?checkpoint_id=${encodeURIComponent(checkpointId)}` : "";
  return get(`/agent/runs/${runId}/state${query}`);
}

/** Write state over a checkpoint, branching the run there. */
export function writeState(
  runId: string,
  values: Record<string, unknown>,
  checkpointId?: string | null,
): Promise<{ run_id: string; checkpoint_id: string | null }> {
  return post(`/agent/runs/${runId}/state`, { values, checkpoint_id: checkpointId ?? null });
}

/** Where a run stops: before a node runs, or once it has written. */
export interface Breakpoints {
  before: string[];
  after: string[];
}

export const NO_BREAKPOINTS: Breakpoints = { before: [], after: [] };

export interface StartOptions {
  force?: boolean;
  breakpoints?: Breakpoints;
  /** Overrides on the starting state, merged over the computed one. */
  values?: Record<string, unknown> | null;
}

export function startRun(runId: string, options: StartOptions = {}): Promise<{ run_id: string; status: string }> {
  return post(`/agent/runs/${runId}/inspect`, {
    force: options.force ?? false,
    breakpoints: options.breakpoints?.before ?? [],
    breakpoints_after: options.breakpoints?.after ?? [],
    values: options.values ?? null,
  });
}

export interface ResumeOptions {
  action?: "resume" | "abort";
  values?: Record<string, unknown> | null;
  checkpointId?: string | null;
  breakpoints?: Breakpoints;
}

/**
 * Let a run carry on.
 *
 * With `values` and a `checkpointId` this is Studio's Fork: the edit lands as a
 * child of that step and the run continues from there. With a `checkpointId`
 * alone it is "re-run from here", which changes nothing and takes the same road
 * again.
 */
export function resumeRun(runId: string, options: ResumeOptions = {}): Promise<{ run_id: string; worker: string }> {
  return post(`/agent/runs/${runId}/resume`, {
    action: options.action ?? "resume",
    values: options.values ?? null,
    checkpoint_id: options.checkpointId ?? null,
    breakpoints: options.breakpoints?.before ?? [],
    breakpoints_after: options.breakpoints?.after ?? [],
  });
}

/* -- tuning a prompt against a trace -------------------------------------- */

/**
 * Running one recorded model call again with the prompt changed.
 *
 * A side experiment: it writes nothing to the run, the trace or the report. The
 * point is to see what a different prompt would have produced for an input that
 * really occurred, and to try that ten times without turning the run you are
 * studying into a scratchpad.
 */
export interface Replay {
  run_id: string;
  span_id: string;
  step: string | null;
  schema: string | null;
  output: unknown;
  latency_ms: number;
  recorded: { system: string; user: string; output: unknown };
  edited: boolean;
}

export function replaySpan(
  runId: string,
  spanId: string,
  edits: { system?: string; user?: string } = {},
): Promise<Replay> {
  return post(`/agent/runs/${runId}/spans/${spanId}/replay`, {
    system: edits.system ?? null,
    user: edits.user ?? null,
  });
}

/** One of the agent's system prompts: what it ships as, and what it is now. */
export interface PromptRow {
  name: string;
  default: string;
  override: string | null;
  in_use: string;
}

export function fetchPrompts(): Promise<{ prompts: PromptRow[] }> {
  return get("/agent/prompts");
}

/** Adopt a tuned prompt. Every later run uses it until it is cleared. */
export function savePrompt(name: string, text: string): Promise<{ prompts: PromptRow[] }> {
  return put(`/agent/prompts/${name}`, { text });
}

export function resetPrompt(name: string): Promise<{ prompts: PromptRow[] }> {
  return del(`/agent/prompts/${name}`);
}

export interface AgentHealth {
  configured: boolean;
  base_url: string;
  model: string | null;
  sandbox: string;
  tools_enabled: boolean;
  runs_dir: string;
  reachable?: boolean;
  served_models?: string[];
  model_is_served?: boolean;
}

/** What Studio's Settings modal is for here: which model this graph runs on. */
export function fetchHealth(probe = false): Promise<AgentHealth> {
  return get<AgentHealth>(`/agent/health${probe ? "?probe=true" : ""}`);
}

export interface RunSummary {
  run_id: string;
  status?: string;
  findings?: number;
  error?: string;
  index?: { files_indexed: number; files_skipped: number; chunks: number; links: number };
  /** The first few file names in the run, and how many there are in total. */
  files?: string[];
  file_count?: number;
  updated_at?: number;
  /** Whether this run was ever inspected. One that was not has no trace. */
  started?: boolean;
}

export function listRuns(): Promise<{ runs: RunSummary[] }> {
  return get<{ runs: RunSummary[] }>("/agent/runs");
}

/** One run, for the heading: which files, what status, what it found. */
export function fetchRun(runId: string): Promise<RunSummary> {
  return get<RunSummary>(`/agent/runs/${runId}`);
}

/** Remove a run and everything in it. */
export function deleteRun(runId: string): Promise<{ deleted: string }> {
  return del(`/agent/runs/${runId}`);
}

/* -- the live stream ------------------------------------------------------ */

export interface NodeEvent {
  node: string | null;
  step: number | null;
  error?: string | null;
  updates?: Record<string, unknown>;
}

export interface CheckpointEvent {
  checkpoint_id: string | null;
  step: number | null;
  node: string | null;
  next: string[];
}

export interface InterruptEvent {
  run_id: string;
  next: string[];
  checkpoint_id: string | null;
}

export interface StudioHandlers {
  onNodeStarted?: (event: NodeEvent) => void;
  onNodeFinished?: (event: NodeEvent) => void;
  onCheckpoint?: (event: CheckpointEvent) => void;
  onInterrupted?: (event: InterruptEvent) => void;
  onResumed?: () => void;
  onFinished?: (event: { findings: number; aborted?: boolean }) => void;
  onFailed?: (event: { error: string }) => void;
  onClosed?: () => void;
}

/**
 * Watch a run as it executes.
 *
 * The old view polled every two seconds, which is both too often for a finished
 * run and far too slow to show which node is running. These events come from
 * the graph itself, one per node, so the canvas lights up in step with the work.
 */
export function watchRun(runId: string, handlers: StudioHandlers): () => void {
  const source = new EventSource(streamUrl(`/agent/runs/${runId}/events`));

  const on = <T,>(name: string, handler?: (payload: T) => void) => {
    if (!handler) return;
    source.addEventListener(name, (event) => {
      try {
        handler(JSON.parse((event as MessageEvent).data) as T);
      } catch {
        /* a malformed frame must not kill the stream */
      }
    });
  };

  on("node_started", handlers.onNodeStarted);
  on("node_finished", handlers.onNodeFinished);
  on("checkpoint", handlers.onCheckpoint);
  on("run_interrupted", handlers.onInterrupted);
  on("run_resumed", handlers.onResumed ? () => handlers.onResumed?.() : undefined);
  on("run_finished", handlers.onFinished);
  on("run_failed", handlers.onFailed);
  source.addEventListener("stream_closed", () => {
    source.close();
    handlers.onClosed?.();
  });

  return () => source.close();
}
