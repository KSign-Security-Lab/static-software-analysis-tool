import { post, postBlob, saveBlob, seg } from "./client";
import type { PatchPreview, PushResult } from "./types";

const SLOW_MS = 180_000;

export function previewPatch(runId: string, findingIds: string[]): Promise<PatchPreview> {
  return post<PatchPreview>(`/agent/runs/${seg(runId)}/patch`, { finding_ids: findingIds }, { timeoutMs: SLOW_MS });
}

export function savePatch(runId: string, patch: string): void {
  saveBlob(new Blob([patch], { type: "text/x-patch" }), `ssat-${runId}.patch`);
}

export async function downloadArchive(runId: string, findingIds: string[]): Promise<void> {
  const { blob, filename } = await postBlob(
    `/agent/runs/${seg(runId)}/archive`,
    { finding_ids: findingIds },
    { timeoutMs: SLOW_MS },
  );
  saveBlob(blob, filename ?? `ssat-${runId}-fixed.zip`);
}

export function pushBranch(
  runId: string,
  request: { findingIds: string[]; branch: string; token: string; openPullRequest: boolean },
): Promise<PushResult> {
  return post<PushResult>(
    `/agent/runs/${seg(runId)}/push`,
    {
      finding_ids: request.findingIds,
      branch: request.branch,
      token: request.token,
      open_pull_request: request.openPullRequest,
    },
    { timeoutMs: 320_000 },
  );
}
