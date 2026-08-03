import { apiBase } from "./api";
import type { Finding, FindingDiff, Report } from "./agent-schema";

/**
 * Client for the /agent/* routes.
 *
 * Separate from lib/api.ts because it is a separate analysis line: the CPG
 * service and the LLM agent share a host and nothing else.
 */

export interface UploadResult {
  run_id: string;
  uploaded: number;
  index: IndexStats;
  files: string[];
}

export interface IndexStats {
  files_indexed: number;
  files_skipped: number;
  chunks: number;
  links: number;
}

export interface FileContent {
  path: string;
  content: string;
  /** Monaco language id, decided server-side from the extension. */
  language: string;
}

export interface AgentHealth {
  configured: boolean;
  base_url: string;
  model: string | null;
  sandbox: string;
  runs_dir: string;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const base = apiBase();
  let res: Response;
  try {
    res = await fetch(`${base}${path}`, init);
  } catch (err) {
    throw new Error(
      `백엔드(${base})에 연결할 수 없습니다. 실행 중인지 확인하세요. [${String(err)}]`,
    );
  }
  const text = await res.text();
  let data: unknown;
  try {
    data = text ? JSON.parse(text) : undefined;
  } catch {
    /* non-JSON error body */
  }
  if (!res.ok) {
    const detail =
      (data as { detail?: string })?.detail ?? text ?? `${res.status} ${res.statusText}`;
    throw new Error(detail);
  }
  return data as T;
}

export function agentHealth(): Promise<AgentHealth> {
  return request<AgentHealth>("/agent/health");
}

/** Upload a zip or a set of loose files. The server indexes before replying. */
export function uploadSource(files: File[]): Promise<UploadResult> {
  const form = new FormData();
  for (const file of files) form.append("files", file, file.name);
  return request<UploadResult>("/agent/runs", { method: "POST", body: form });
}

export function fetchFile(runId: string, path: string): Promise<FileContent> {
  return request<FileContent>(
    `/agent/runs/${runId}/file?path=${encodeURIComponent(path)}`,
  );
}

export function startInspection(runId: string, force = false): Promise<{ run_id: string }> {
  return request(`/agent/runs/${runId}/inspect`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ force }),
  });
}

export function fetchFindings(runId: string): Promise<Report> {
  return request<Report>(`/agent/runs/${runId}/findings`);
}

export function diffRuns(runId: string, against: string): Promise<FindingDiff> {
  return request<FindingDiff>(`/agent/runs/${runId}/diff`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ against }),
  });
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
 * Subscribe to inspection progress.
 *
 * A chunk-by-chunk run takes minutes, so findings stream in as they are
 * confirmed rather than arriving in one lump at the end. Returns a function
 * that closes the stream.
 */
export function subscribeToRun(runId: string, handlers: InspectionHandlers): () => void {
  const source = new EventSource(`${apiBase()}/agent/runs/${runId}/events`);

  const on = <T>(name: string, handler?: (payload: T) => void) => {
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
