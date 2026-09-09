import { del, get, post, postForm, seg, type RequestOptions } from "./client";

const SLOW_MS = 180_000;
import type {
  AgentHealth,
  CloneRequest,
  FileContents,
  ProposeResult,
  Report,
  RunSummary,
  UploadResult,
} from "./types";

export function health(probe = false, options?: RequestOptions): Promise<AgentHealth> {
  return get<AgentHealth>(`/agent/health${probe ? "?probe=true" : ""}`, options);
}

export function listRuns(options?: RequestOptions): Promise<{ runs: RunSummary[] }> {
  return get<{ runs: RunSummary[] }>("/agent/runs", options);
}

export function fetchRun(runId: string, options?: RequestOptions): Promise<RunSummary> {
  return get<RunSummary>(`/agent/runs/${seg(runId)}`, options);
}

export function uploadSource(files: (File | { file: File; path: string })[]): Promise<UploadResult> {
  const form = new FormData();
  for (const each of files) {
    const file = each instanceof File ? each : each.file;
    const path = each instanceof File ? file.webkitRelativePath || file.name : each.path;
    form.append("files", file, path);
  }
  return postForm<UploadResult>("/agent/runs", form, { timeoutMs: SLOW_MS });
}

export function uploadArchive(file: File): Promise<UploadResult> {
  const form = new FormData();
  form.append("files", file, file.name.toLowerCase().endsWith(".zip") ? file.name : `${file.name}.zip`);
  return postForm<UploadResult>("/agent/runs", form, { timeoutMs: SLOW_MS });
}

export function cloneRepo(request: CloneRequest): Promise<UploadResult> {
  return post<UploadResult>("/agent/runs/git", request, { timeoutMs: 320_000 });
}

export function deleteRun(runId: string): Promise<{ deleted: string }> {
  return del<{ deleted: string }>(`/agent/runs/${seg(runId)}`);
}

export function fetchFiles(runId: string, options?: RequestOptions): Promise<{ run_id: string; files: string[] }> {
  return get<{ run_id: string; files: string[] }>(`/agent/runs/${seg(runId)}/files`, options);
}

export function fetchFile(runId: string, path: string, options?: RequestOptions): Promise<FileContents> {
  return get<FileContents>(`/agent/runs/${seg(runId)}/file?path=${encodeURIComponent(path)}`, options);
}

export function fetchFindings(runId: string, options?: RequestOptions): Promise<Report> {
  return get<Report>(`/agent/runs/${seg(runId)}/findings`, options);
}

export function proposeFix(runId: string, findingId: string): Promise<ProposeResult> {
  return post<ProposeResult>(`/agent/runs/${seg(runId)}/propose`, { finding_id: findingId }, { timeoutMs: SLOW_MS });
}
