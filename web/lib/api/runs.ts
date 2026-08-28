import { del, get, post, postForm, seg, type RequestOptions } from "./client";

/**
 * For the calls that are honestly slow rather than stuck.
 *
 * An upload of a real tree, a clone, an LLM asked for a fix: the default
 * deadline exists to turn a dead backend into an error, and applying it to these
 * would turn working requests into errors instead.
 */
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

/**
 * Runs, their files, and their report.
 *
 * Split by resource rather than by page, which is why there is exactly one
 * `AgentHealth` now: the previous split gave the inspect view and the trace
 * view a client each, and the two declared the same type differently -- one
 * with `tracing`, one without.
 *
 * Read-only over the tree. Nothing here writes a file: the tree a report was
 * made from stays as it was analysed, and a fix leaves as a patch -- see
 * `lib/api/patch.ts`.
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
  // A real tree is tens of megabytes over the wire and then indexed
  // synchronously before the response. The default deadline would cancel it.
  return postForm<UploadResult>("/agent/runs", form, { timeoutMs: SLOW_MS });
}

/**
 * Upload a zip.
 *
 * The same endpoint and the same field: the server decides by the filename that
 * a single `.zip` is an archive to expand rather than a file to store. It has
 * always accepted this; a separate function exists because the two intake
 * buttons mean different things to the reader and one of them had no name.
 */
export function uploadArchive(file: File): Promise<UploadResult> {
  const form = new FormData();
  form.append("files", file, file.name.toLowerCase().endsWith(".zip") ? file.name : `${file.name}.zip`);
  return postForm<UploadResult>("/agent/runs", form, { timeoutMs: SLOW_MS });
}

/**
 * Clone a repository and index it.
 *
 * Slower than an upload -- the server is fetching a remote -- but the same
 * shape comes back, so the intake screen does not branch on which button was
 * pressed. A refused URL is a 400 with the reason; an unreachable remote is a
 * 502, which is the remote's answer and not ours.
 */
export function cloneRepo(request: CloneRequest): Promise<UploadResult> {
  // The server gives git 300s of its own; outliving that by a margin means a
  // hung clone is reported by the side that actually knows why.
  return post<UploadResult>("/agent/runs/git", request, { timeoutMs: 320_000 });
}

export function deleteRun(runId: string): Promise<{ deleted: string }> {
  return del<{ deleted: string }>(`/agent/runs/${seg(runId)}`);
}

/**
 * Every file in the run.
 *
 * `RunSummary.files` is at most two names -- a label, not a tree -- so this is
 * the only way to know what a run actually covered when the tab did not upload
 * it.
 */
export function fetchFiles(runId: string, options?: RequestOptions): Promise<{ run_id: string; files: string[] }> {
  return get<{ run_id: string; files: string[] }>(`/agent/runs/${seg(runId)}/files`, options);
}

export function fetchFile(runId: string, path: string, options?: RequestOptions): Promise<FileContents> {
  return get<FileContents>(`/agent/runs/${seg(runId)}/file?path=${encodeURIComponent(path)}`, options);
}

export function fetchFindings(runId: string, options?: RequestOptions): Promise<Report> {
  return get<Report>(`/agent/runs/${seg(runId)}/findings`, options);
}

/**
 * Ask for code to fix a finding that arrived with advice and none.
 *
 * What makes such a finding patchable at all: a specialist proposes a fix only
 * when it happens to fit the lines the anchor resolved to, and often it does
 * not. Writes the proposal into the report and stops -- the patch is still built
 * from the report when the bucket is exported, so this changes what a fix *is*
 * rather than applying one.
 */
export function proposeFix(runId: string, findingId: string): Promise<ProposeResult> {
  // One model call, and a loaded endpoint can take minutes over it.
  return post<ProposeResult>(`/agent/runs/${seg(runId)}/propose`, { finding_id: findingId }, { timeoutMs: SLOW_MS });
}
