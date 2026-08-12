import { del, get, post, postForm, put, seg, type RequestOptions } from "./client";
import type {
  AgentHealth,
  FileContents,
  FileWriteResult,
  ApplyResult,
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

/**
 * Upload a tree.
 *
 * Takes either bare files or files with the path each had, because the two ways
 * of choosing a folder report it differently: `<input webkitdirectory>` sets
 * `webkitRelativePath` on every File, and a drag-and-drop does not -- the path
 * only exists in the entries walk that produced it (lib/run/drop.ts). Without a
 * path per file every file in a tree arrives as a bare basename and two
 * `main.c` in two directories collide into one.
 */
export function uploadSource(files: (File | { file: File; path: string })[]): Promise<UploadResult> {
  const form = new FormData();
  for (const each of files) {
    const file = each instanceof File ? each : each.file;
    const path = each instanceof File ? file.webkitRelativePath || file.name : each.path;
    form.append("files", file, path);
  }
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

/**
 * Splice a finding's proposed fix over the lines it is anchored to.
 *
 * The arithmetic is the server's, deliberately: the span is 1-based and
 * inclusive, and an off-by-one here would corrupt somebody's source rather than
 * fail. It refuses -- 409 -- when the file has changed since the run, because
 * the span would then point at code nobody analysed.
 */
export function applyFix(runId: string, findingId: string): Promise<ApplyResult> {
  return post<ApplyResult>(`/agent/runs/${seg(runId)}/apply`, { finding_id: findingId });
}

export function diffRuns(runId: string, against: string): Promise<FindingDiff> {
  return post<FindingDiff>(`/agent/runs/${seg(runId)}/diff`, { against });
}
