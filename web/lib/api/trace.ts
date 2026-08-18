import { get, post, seg, type RequestOptions } from "./client";
import type {
  InputResponse,
  Replay,
  SpansResponse,
  StateResponse,
  ThreadsResponse,
} from "./types";

/** What a run recorded: spans, the same calls as a conversation, and history. */

export function fetchSpans(runId: string, options?: RequestOptions): Promise<SpansResponse> {
  return get<SpansResponse>(`/agent/runs/${seg(runId)}/spans`, options);
}

export function fetchThreads(runId: string, options?: RequestOptions): Promise<ThreadsResponse> {
  return get<ThreadsResponse>(`/agent/runs/${seg(runId)}/thread`, options);
}

/**
 * `full` is not cosmetic: without it the server summarises the bulky channels
 * to a count, which is all a timeline needs and a fraction of the bytes. Only
 * a state editor wants the whole thing.
 */

export function fetchState(runId: string, checkpointId?: string, options?: RequestOptions): Promise<StateResponse> {
  const query = checkpointId ? `?checkpoint_id=${encodeURIComponent(checkpointId)}` : "";
  return get<StateResponse>(`/agent/runs/${seg(runId)}/state${query}`, options);
}

/** The starting state, readable before a run has ever been started. */
export function fetchInput(runId: string, options?: RequestOptions): Promise<InputResponse> {
  return get<InputResponse>(`/agent/runs/${seg(runId)}/input`, options);
}

export function writeState(
  runId: string,
  values: Record<string, unknown>,
  checkpointId?: string | null,
  asNode?: string | null,
): Promise<{ run_id: string; checkpoint_id: string | null }> {
  return post(`/agent/runs/${seg(runId)}/state`, { values, checkpoint_id: checkpointId, as_node: asNode });
}

/**
 * Run one recorded model call again, optionally with an edited prompt.
 *
 * Writes nothing -- not to the run, not to the trace, not to the report. That
 * is the pane's whole contract, and the reason it is safe to press repeatedly.
 * Passing null for either half reuses what the span recorded.
 */
export function replaySpan(
  runId: string,
  spanId: string,
  edit: { system?: string | null; user?: string | null } = {},
): Promise<Replay> {
  return post<Replay>(`/agent/runs/${seg(runId)}/spans/${seg(spanId)}/replay`, edit);
}
