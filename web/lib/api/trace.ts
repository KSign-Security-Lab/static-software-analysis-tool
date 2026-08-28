import { get, seg, type RequestOptions } from "./client";
import type { SpansResponse, ThreadsResponse } from "./types";

/**
 * What a run recorded: its call tree, and the same calls as conversations.
 *
 * Read-only. Editing a run's state mid-flight and replaying one recorded call
 * belonged to the studio; what remains is what a finding's 판단 과정 is drawn
 * from -- `lib/run/claim-trail.ts` joins these two onto one finding.
 */

export function fetchSpans(runId: string, options?: RequestOptions): Promise<SpansResponse> {
  return get<SpansResponse>(`/agent/runs/${seg(runId)}/spans`, options);
}

export function fetchThreads(runId: string, options?: RequestOptions): Promise<ThreadsResponse> {
  return get<ThreadsResponse>(`/agent/runs/${seg(runId)}/thread`, options);
}
