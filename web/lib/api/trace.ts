import { get, seg, type RequestOptions } from "./client";
import type { SpansResponse, ThreadsResponse } from "./types";

export function fetchSpans(runId: string, options?: RequestOptions): Promise<SpansResponse> {
  return get<SpansResponse>(`/agent/runs/${seg(runId)}/spans`, options);
}

export function fetchThreads(runId: string, options?: RequestOptions): Promise<ThreadsResponse> {
  return get<ThreadsResponse>(`/agent/runs/${seg(runId)}/thread`, options);
}
