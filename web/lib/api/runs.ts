import { del, get, post, postForm, put, seg, type RequestOptions } from "./client";
import type {
  AgentHealth,
  FileContents,
  FileWriteResult,
  FindingDiff,
  Report,
  RunSummary,
  UploadResult,
} from "./types";

/**
 * Runs, their files, and their report.
 *
 * Split by resource rather than by page, which is why there is exactly one
 * `AgentHealth` now: the previous split gave the inspect view and the trace
 * view a client each, and the two declared the same type differently -- one
 * with `tracing`, one without.
 */

export function health(probe = false, options?: RequestOptions): Promise<AgentHealth> {
  return get<AgentHealth>(`/agent/health${probe ? "?probe=true" : ""}`, options);
}

export function listRuns(options?: RequestOptions): Promise<{ runs: RunSummary[] }> {
  return get<{ runs: RunSummary[] }>("/agent/runs", options);
}

export function fetchRun(runId: string, options?: RequestOptions): Promise<RunSummary> {
  return get<RunSummary>(`/agent/runs/${seg(runId)}`, options);
}

export function createEmptyRun(): Promise<UploadResult> {
  return post<UploadResult>("/agent/runs/new");
}

export function uploadSource(files: File[]): Promise<UploadResult> {
  const form = new FormData();
  // `webkitRelativePath` is what a directory upload carries; without it every
  // file in a tree arrives as a bare basename and the paths collide.
  for (const file of files) form.append("files", file, file.webkitRelativePath || file.name);
  return postForm<UploadResult>("/agent/runs", form);
}

export function deleteRun(runId: string): Promise<{ deleted: string }> {
  return del<{ deleted: string }>(`/agent/runs/${seg(runId)}`);
}

/**
 * Every file in the run.
 *
 * `RunSummary.files` is at most two names -- a label, not a tree -- so this is
 * the only way to populate an explorer for a run this tab did not just upload.
 */
export function fetchFiles(runId: string, options?: RequestOptions): Promise<{ run_id: string; files: string[] }> {
  return get<{ run_id: string; files: string[] }>(`/agent/runs/${seg(runId)}/files`, options);
}

export function fetchFile(runId: string, path: string, options?: RequestOptions): Promise<FileContents> {
  return get<FileContents>(`/agent/runs/${seg(runId)}/file?path=${encodeURIComponent(path)}`, options);
}

export function writeFile(runId: string, path: string, content: string): Promise<FileWriteResult> {
  return put<FileWriteResult>(`/agent/runs/${seg(runId)}/file`, { path, content });
}

export function deleteFile(runId: string, path: string): Promise<FileWriteResult & { deleted: string }> {
  return del<FileWriteResult & { deleted: string }>(
    `/agent/runs/${seg(runId)}/file?path=${encodeURIComponent(path)}`,
  );
}

export function fetchFindings(runId: string, options?: RequestOptions): Promise<Report> {
  return get<Report>(`/agent/runs/${seg(runId)}/findings`, options);
}

export function diffRuns(runId: string, against: string): Promise<FindingDiff> {
  return post<FindingDiff>(`/agent/runs/${seg(runId)}/diff`, { against });
}
