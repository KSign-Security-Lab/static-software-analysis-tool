import type { Finding, Report, RunStats, Span as WireSpan } from "@/lib/agent-schema";

/**
 * Hand-written mirrors of the agent API's non-generated shapes.
 *
 * The wire models under `Report` are generated from pydantic and drift-tested
 * (see lib/agent-schema.ts). Everything here is assembled by the route
 * handlers out of the trace store and LangGraph, so there is no pydantic model
 * to generate from -- these are written by hand and kept honest by reading
 * the route handlers under api/agent/.
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
  /**
   * Where a stopped run is waiting, when `status` is `interrupted`.
   *
   * The event stream cannot be replayed, so a tab opened -- or reloaded --
   * while a run sits at a breakpoint never hears `run_interrupted` and would
   * offer to start it over. This is the same fact, read rather than heard.
   */
  parked?: { next: string[]; checkpoint_id: string | null } | null;
  /**
   * How far a run in flight has got, when `status` is `inspecting`.
   *
   * Same reason as `parked`: the stream cannot be replayed, so a tab that
   * arrives mid-run has no other way to know anything is happening. `next` is
   * the last checkpoint's queued tasks -- what is executing now.
   */
  progress?: { next: string[]; step: number | null } | null;
}

/** What applying a proposed fix changed. */
/** What `/propose` wrote into the report: the same shape a run would have made. */
export interface ProposeResult {
  run_id: string;
  finding_id: string;
  remediation: { summary: string; detail: string; diff: string | null; replacement: string | null };
}

export interface ApplyResult {
  run_id: string;
  finding_id: string;
  path: string;
  /** The 1-based inclusive span that was replaced. */
  lines: [number, number];
  index: IndexStats;
  /** The finding cannot survive its own fix: its id is derived from the anchor. */
  reinspect: boolean;
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
  /** What each kind of model call is: its prompt, its answer shape, its tools. */
  steps: AgentStep[];
  /** What each *node* is. Five of them call no model at all. */
  node_notes: NodeNote[];
}

/**
 * One node of the graph, and what kind of thing it is.
 *
 * Five of the twelve never call a model -- they take work off a queue, build the
 * text a specialist reads, resolve what one quoted back to a real span, and write
 * down what survived. Nothing of them appears in any trace, which left half the
 * drawing looking like it did nothing.
 */
export interface NodeNote {
  node: string;
  /** True because a step names this node, not because anything declares it twice. */
  agent: boolean;
  steps: string[];
  calls: number;
  tools: number;
  /** What it does. Only the deterministic ones need it; an agent has a prompt. */
  does: string | null;
  /** State channels it reads and writes. */
  reads: string[];
  writes: string[];
  /** The router function that decides where it goes, and the rule it applies. */
  router: string | null;
  rule: string | null;
  /** Where it can go. Read off the compiled graph, so it cannot drift from it. */
  routes: string[];
}

/** One tool the agent may reach for, as the MCP server describes it. */
export interface ToolSpec {
  name: string;
  /** First line of the tool's own documentation. */
  summary: string;
  parameters: string[];
}

/**
 * One kind of model call the agent makes.
 *
 * A property of the code, so it is known before a run and still known after one
 * -- which is the point. A trace can only show the tools that were *called*;
 * "it was offered nine and used two" is a different account of a verification
 * from "it used two", and only this can tell them apart.
 */
export interface AgentStep {
  /** The key its spans carry in `meta.step`, and its prompt's name. */
  step: string;
  /** The graph node it runs in. Not its own name: `lens:memory` runs in `memory`. */
  node: string;
  prompt: string;
  /** What guided decoding constrained the reply to; null for a tool loop. */
  schema: string | null;
  schema_fields: string[];
  tools: ToolSpec[];
  /** Tools exist for this step *and* this endpoint can call them. */
  tools_enabled: boolean;
  max_tool_calls: number;
  /** Whether this configuration runs it at all: AGENT_LENSES, AGENT_TRIAGE. */
  enabled: boolean;
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
  /** The span id, so a turn can be handed to the replay endpoint. */
  id: string;
  step: string;
  name: string;
  /** The graph node that made the call, for narrowing the record to one node. */
  node: string | null;
  /**
   * Which specialist raised the claim this call is about.
   *
   * `gather` and `verify` only. It is the hand-off from analysis to verification,
   * and until the agent recorded it the two read as unrelated calls that happened
   * to mention the same CWE.
   */
  raised_by: string | null;
  messages: { role: string; content: string }[];
  reply: string | null;
  /** What the model asked to run, with its arguments. */
  tool_calls: { name?: string; args?: Record<string, unknown> }[];
  /** What running those returned. Empty when the step has no tools. */
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
