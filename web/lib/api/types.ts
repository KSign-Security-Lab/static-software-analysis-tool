import type { Finding, Report, RunStats, Span as WireSpan } from "@/lib/agent-schema";

/**
 * Hand-written mirrors of the agent API's non-generated shapes.
 *
 * The wire models under `Report` are generated from pydantic and drift-tested
 * (see lib/agent-schema.ts). Everything here is assembled by the route
 * handlers out of the trace store and LangGraph, so there is no pydantic model
 * to generate from -- these are written by hand and kept honest by reading
 * api/agent_routes.py.
 */

export type { Evidence, Finding, FindingDiff, Remediation, Report, RunStats } from "@/lib/agent-schema";

/**
 * A region of source code.
 *
 * The generated name for this is `Span`, which collides with the trace span
 * below -- two unrelated things, one word, and components kept importing the
 * wrong one. Renamed here; `Span` itself may only be imported by this module
 * and lib/model.
 */
export type SourceSpan = WireSpan;

export type RunStatus = "created" | "indexing" | "indexed" | "inspecting" | "interrupted" | "done" | "failed";

export interface IndexStats {
  files_indexed: number;
  files_skipped: number;
  chunks: number;
  links: number;
}

export interface RunSummary {
  run_id: string;
  status: RunStatus;
  index?: IndexStats;
  uploaded?: number;
  findings?: number;
  error?: string;
  /**
   * At most two names -- the server sends them for labelling, not for a tree
   * (`LABEL_FILES` in agent/runs.py). `file_count` is the real total.
   */
  files: string[];
  file_count: number;
  updated_at: number;
  /** A trace database exists, so this run was inspected at least once. */
  started: boolean;
}

export interface FileContents {
  path: string;
  content: string;
  /** A Monaco language id, chosen server-side from the extension. */
  language: string;
}

export interface FileWriteResult {
  path: string;
  index: IndexStats;
  files: string[];
}

/* -- the agent's own graph --------------------------------------------------- */

export interface GraphShape {
  nodes: string[];
  edges: { source: string; target: string; conditional: boolean }[];
  mermaid: string;
  /** The only legal breakpoint names; anything else is a 400. */
  steppable: string[];
}

/* -- trace ------------------------------------------------------------------- */

export type SpanKind = "chain" | "llm" | "tool";
export type SpanStatus = "running" | "ok" | "error";

/**
 * One recorded call.
 *
 * Readable mid-run -- the store is SQLite in WAL mode -- so an unfinished span
 * comes back `running` with a null latency rather than not at all.
 */
export interface TraceSpan {
  id: string;
  parent_id: string | null;
  seq: number;
  name: string;
  kind: SpanKind;
  status: SpanStatus;
  error: string | null;
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

/** What the store writes instead of a payload it had to cut short. */
export interface TruncatedPayload {
  _truncated: true;
  _chars: number;
  preview: string;
}

export function isTruncated(value: unknown): value is TruncatedPayload {
  return typeof value === "object" && value !== null && (value as TruncatedPayload)._truncated === true;
}

export interface ToolCall {
  name: string;
  inputs: unknown;
  outputs: unknown;
  error: string | null;
  latency_ms: number | null;
}

export interface Turn {
  id: string;
  step: string;
  name: string;
  messages: { role: string; content: string }[];
  reply: string | null;
  tool_calls: unknown[];
  tools: ToolCall[];
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

/**
 * A point in the run's history.
 *
 * `parent_checkpoint_id` makes this a tree rather than a list: a second child
 * of the same step is a fork, and that is the only thing that makes one
 * visible.
 */
export interface Checkpoint {
  checkpoint_id: string | null;
  parent_checkpoint_id: string | null;
  step: number | null;
  source: string | null;
  node: string | null;
  nodes: string[];
  /** Queued next; a name repeats once per parallel task. */
  next: string[];
  created_at: string | null;
  values: Record<string, unknown>;
}

/** The graph's channels. These are the exact keys a state edit may write. */
export interface InspectionState {
  pending: string[];
  wave: string[];
  current: string | null;
  packs: Record<string, string>;
  triaged: Record<string, unknown>;
  candidates: unknown[];
  located: unknown[];
  verdicts: unknown[];
  confirmed: unknown[];
  stats: Record<string, number>;
}

/* -- prompts and replay ------------------------------------------------------ */

export interface PromptRow {
  name: string;
  default: string;
  override: string | null;
  in_use: boolean;
}

export interface Replay {
  run_id: string;
  span_id: string;
  step: string | null;
  schema: "Triage" | "Verdict" | "ChunkAnalysis" | null;
  output: unknown;
  latency_ms: number;
  recorded: { system: string; user: string; output: unknown };
  edited: boolean;
}

/* -- health ------------------------------------------------------------------ */

export interface AgentHealth {
  configured: boolean;
  base_url: string;
  model: string | null;
  sandbox: string;
  tools_enabled: boolean;
  runs_dir: string;
  tracing: {
    enabled: boolean;
    project: string;
    endpoint: string | null;
    api_key_set: boolean;
    detail: string | null;
  };
  /** Only present with `?probe=true`, which makes a real request. */
  reachable?: boolean;
  served_models?: string[];
  model_is_served?: boolean;
}

/* -- knowledge graph --------------------------------------------------------- */

export interface KnowledgeNode {
  /** A chunk id, so it joins to Finding.chunk_id, Thread.id and pending[]. */
  id: string;
  kind: "file" | "unit";
  label: string;
  file: string;
  attrs?: { start_line: number; end_line: number };
  community: number | null;
}

export interface KnowledgeEdge {
  src: string;
  dst: string;
  kind: "calls" | "uses_type" | "file_depends";
  /**
   * An edge the parser resolved and one guessed from a README are not the same
   * claim, and the drawing must not flatten them.
   */
  provenance: "extracted" | "inferred";
}

export interface Community {
  id: number;
  label: string;
  members: string[];
  files: string[];
}

export interface KnowledgeGraph {
  run_id: string;
  nodes: KnowledgeNode[];
  edges: KnowledgeEdge[];
  communities: Community[];
  counts: { nodes: number; edges: number; communities: number; inferred: number };
}

/* -- responses --------------------------------------------------------------- */

export interface SpansResponse {
  run_id: string;
  spans: TraceSpan[];
  summary: SpanSummary;
}
export interface ThreadsResponse {
  run_id: string;
  threads: Thread[];
}
export interface CheckpointsResponse {
  run_id: string;
  checkpoints: Checkpoint[];
  count: number;
}
export interface InputResponse {
  run_id: string;
  values: InspectionState;
}
export type StateResponse = Checkpoint & { run_id: string };
export interface UploadResult {
  run_id: string;
  uploaded: number;
  index: IndexStats;
  files: string[];
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

export const EMPTY_STATS: RunStats = {
  files_indexed: 0,
  files_skipped: 0,
  chunks_total: 0,
  chunks_inspected: 0,
  chunks_cached: 0,
  triaged_out: 0,
  candidates: 0,
  dropped_unlocatable: 0,
  refuted: 0,
};

export type { Finding as AgentFinding, Report as AgentReport };
