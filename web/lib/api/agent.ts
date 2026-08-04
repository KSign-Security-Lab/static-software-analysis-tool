import type { Finding, FindingDiff, Report } from "@/lib/agent-schema";
import { get, post, postForm, streamUrl } from "@/lib/http";

/** The LLM line: upload a tree, inspect it chunk by chunk, stream the results. */

export interface IndexStats {
  files_indexed: number;
  files_skipped: number;
  chunks: number;
  links: number;
}

export interface UploadResult {
  run_id: string;
  uploaded: number;
  index: IndexStats;
  files: string[];
}

export interface FileContent {
  path: string;
  content: string;
  language: string;
}

export interface TracingStatus {
  enabled: boolean;
  project: string;
  endpoint: string | null;
  api_key_set: boolean;
  detail: string | null;
}

export interface AgentHealth {
  configured: boolean;
  base_url: string;
  model: string | null;
  sandbox: string;
  tools_enabled: boolean;
  runs_dir: string;
  tracing: TracingStatus;
  reachable?: boolean;
  served_models?: string[];
  model_is_served?: boolean;
}

export function agentHealth(probe = false): Promise<AgentHealth> {
  return get<AgentHealth>(`/agent/health${probe ? "?probe=true" : ""}`);
}

export function uploadSource(files: File[]): Promise<UploadResult> {
  const form = new FormData();
  for (const file of files) form.append("files", file, file.name);
  return postForm<UploadResult>("/agent/runs", form);
}

export function fetchFile(runId: string, path: string): Promise<FileContent> {
  return get<FileContent>(`/agent/runs/${runId}/file?path=${encodeURIComponent(path)}`);
}

export function startInspection(runId: string, force = false): Promise<{ run_id: string }> {
  return post(`/agent/runs/${runId}/inspect`, { force });
}

export function fetchFindings(runId: string): Promise<Report> {
  return get<Report>(`/agent/runs/${runId}/findings`);
}

export function diffRuns(runId: string, against: string): Promise<FindingDiff> {
  return post<FindingDiff>(`/agent/runs/${runId}/diff`, { against });
}

export interface ChunkFinished {
  chunk_id: string;
  file: string;
  symbol: string;
  findings: Finding[];
  stats: Record<string, number>;
}

export interface InspectionHandlers {
  onChunkStarted?: (payload: { chunk_id: string; remaining: number; total: number }) => void;
  onChunkFinished?: (payload: ChunkFinished) => void;
  onFinished?: (payload: { findings: number }) => void;
  onFailed?: (payload: { error: string }) => void;
}

/**
 * Progress for a run. A chunk-by-chunk inspection takes minutes, so findings
 * arrive as they are confirmed rather than in one lump at the end.
 */
export function subscribeToRun(runId: string, handlers: InspectionHandlers): () => void {
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

  on("chunk_started", handlers.onChunkStarted);
  on("chunk_finished", handlers.onChunkFinished);
  on("run_finished", handlers.onFinished);
  on("run_failed", handlers.onFailed);
  source.addEventListener("stream_closed", () => source.close());

  return () => source.close();
}
