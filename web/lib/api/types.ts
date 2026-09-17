import type { Finding, Report, RunStats, Span as WireSpan } from "@/lib/agent-schema";

export type { Evidence, Finding, Remediation, Report, RunStats } from "@/lib/agent-schema";

export type SourceSpan = WireSpan;

export type RunStatus =
  | "created"
  | "indexing"
  | "indexed"
  | "inspecting"
  | "interrupted"
  | "cancelled"
  | "done"
  | "failed";

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
  files: string[];
  file_count: number;
  updated_at: number;
  origin?: Origin;
  intake?: Intake;
  started: boolean;
  parked?: { next: string[]; checkpoint_id: string | null } | null;
  progress?: { next: string[]; step: number | null } | null;
}

export interface ProposeResult {
  run_id: string;
  finding_id: string;
  remediation: { summary: string; detail: string; diff: string | null; replacement: string | null };
}

export interface FileContents {
  path: string;
  content: string;
  language: string;
}

export interface GraphShape {
  nodes: string[];
  edges: { source: string; target: string; conditional: boolean }[];
  mermaid: string;
  steppable: string[];
  steps: AgentStep[];
  node_notes: NodeNote[];
}

export interface NodeNote {
  node: string;
  agent: boolean;
  steps: string[];
  calls: number;
  tools: number;
  does: string | null;
  reads: string[];
  writes: string[];
  router: string | null;
  rule: string | null;
  routes: string[];
}

export interface ToolSpec {
  name: string;
  summary: string;
  parameters: string[];
}

export interface AgentStep {
  step: string;
  node: string;
  prompt: string;
  schema: string | null;
  schema_fields: string[];
  tools: ToolSpec[];
  tools_enabled: boolean;
  max_tool_calls: number;
  enabled: boolean;
}

export type SpanKind = "chain" | "llm" | "tool";
export type SpanStatus = "running" | "ok" | "error";

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
  node: string | null;
  raised_by: string | null;
  messages: { role: string; content: string }[];
  reply: string | null;
  tool_calls: { name?: string; args?: Record<string, unknown> }[];
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

export interface PromptRow {
  name: string;
  default: string;
  override: string | null;
  in_use: boolean;
}

export interface AgentHealth {
  configured: boolean;
  base_url: string;
  model: string | null;
  sandbox: string;
  tools_enabled: boolean;
  database: string;
  tracing: {
    enabled: boolean;
    project: string;
    endpoint: string | null;
    api_key_set: boolean;
    detail: string | null;
  };
  reachable?: boolean;
  served_models?: string[];
  model_is_served?: boolean;
}

export interface KnowledgeNode {
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

export interface SpansResponse {
  run_id: string;
  spans: TraceSpan[];
  summary: SpanSummary;
}
export interface ThreadsResponse {
  run_id: string;
  threads: Thread[];
}

export interface Origin {
  kind: "upload" | "zip" | "git";
  label: string;
  url: string | null;
  ref: string | null;
  commit: string | null;
}

export interface CloneRequest {
  url: string;
  ref?: string | null;
}

export interface IntakeSkip {
  path: string;
  size: number;
  reason: "too_large" | "binary";
}

export interface Intake {
  kept: number;
  seen: number;
  skipped: IntakeSkip[];
}

export interface UploadResult {
  run_id: string;
  uploaded: number;
  index: IndexStats;
  files: string[];
  origin: Origin;
  intake: Intake;
  matches: RunSummary[];
}

export type SkipReason = "no_replacement" | "overlap" | "stale" | "unreadable";

export interface PatchSkip {
  finding_id: string;
  reason: SkipReason;
  detail: string;
}

export interface PatchPreview {
  run_id: string;
  patch: string;
  applied: string[];
  skipped: PatchSkip[];
  files: string[];
}

export interface PushResult {
  run_id: string;
  branch: string;
  commit: string;
  applied: string[];
  skipped: PatchSkip[];
  compare_url: string | null;
  pr_url: string | null;
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
