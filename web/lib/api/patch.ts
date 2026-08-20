import { post, postBlob, saveBlob, seg } from "./client";
import type { PatchPreview, PushResult } from "./types";

/**
 * Turning a bucket of findings into something that leaves the browser.
 *
 * Three outputs over two shapes of response. The preview and the push answer in
 * JSON, because what the reader needs first is *which* of their ticks made it
 * and why the rest did not. The archive answers in bytes, so it goes through
 * `postBlob`.
 *
 * The patch is never assembled here. The server splices, computes the diff and
 * reports the refusals; a client that built its own diff could build any diff
 * and it would still be labelled as the agent's fix.
 */

/**
 * What the selection amounts to, before anything is downloaded.
 *
 * An empty `patch` with a populated `skipped` is a normal answer, not an error:
 * a selection of advice-only findings has nothing to apply, and saying so is
 * the point of asking first.
 */
export function previewPatch(runId: string, findingIds: string[]): Promise<PatchPreview> {
  return post<PatchPreview>(`/agent/runs/${seg(runId)}/patch`, { finding_ids: findingIds });
}

/**
 * Save the preview's diff as a file.
 *
 * From text already in hand rather than a second request, so what is saved is
 * exactly the patch that was on screen -- and a re-scan between looking and
 * saving cannot quietly change it.
 */
export function savePatch(runId: string, patch: string): void {
  saveBlob(new Blob([patch], { type: "text/x-patch" }), `ssat-${runId}.patch`);
}

/** The whole tree with the fixes in it. Streamed, so this is a real request. */
export async function downloadArchive(runId: string, findingIds: string[]): Promise<void> {
  const { blob, filename } = await postBlob(`/agent/runs/${seg(runId)}/archive`, {
    finding_ids: findingIds,
  });
  saveBlob(blob, filename ?? `ssat-${runId}-fixed.zip`);
}

/**
 * Commit the fixes on a branch of the run's own remote.
 *
 * `token` is the caller's, for this one request. It is not stored here and not
 * stored server-side; see the note on `PushRequest` in `api/agent/patch.py` for
 * why a per-request credential is the only honest option in a service with no
 * login.
 */
export function pushBranch(
  runId: string,
  request: { findingIds: string[]; branch: string; token: string; openPullRequest: boolean },
): Promise<PushResult> {
  return post<PushResult>(`/agent/runs/${seg(runId)}/push`, {
    finding_ids: request.findingIds,
    branch: request.branch,
    token: request.token,
    open_pull_request: request.openPullRequest,
  });
}
