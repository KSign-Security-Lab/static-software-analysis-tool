import { get, post, seg, type RequestOptions } from "./client";
import type { GraphShape } from "./types";

/** Starting, pausing and steering a run. */

export interface Breakpoints {
  before: string[];
  after: string[];
}

export const NO_BREAKPOINTS: Breakpoints = { before: [], after: [] };

export function fetchGraph(options?: RequestOptions): Promise<GraphShape> {
  return get<GraphShape>("/agent/graph", options);
}

export interface StartOptions {
  force?: boolean;
  breakpoints?: Breakpoints;
  values?: Record<string, unknown> | null;
}

/**
 * 200 here means *accepted*, never *succeeded*.
 *
 * The route spawns a worker and returns immediately; a failure arrives later
 * as `run_failed` on the event stream and as `status: "failed"` on the run
 * record. Anything reading this as "it worked" will be wrong for the length of
 * a model call.
 */
export interface StartResult {
  run_id: string;
  status: string;
  already_running: boolean;
  /**
   * The server declined: every chunk already has a result, so this run would
   * have called no model and reset the previous run's trace to prove it. Ask
   * again with `force` to do the work anyway.
   */
  nothing_to_do?: boolean;
}

export function startRun(runId: string, { force = false, breakpoints = NO_BREAKPOINTS, values }: StartOptions = {}) {
  return post<StartResult>(`/agent/runs/${seg(runId)}/inspect`, {
    force,
    breakpoints: breakpoints.before,
    breakpoints_after: breakpoints.after,
    values: values ?? null,
  });
}

export interface ResumeOptions {
  action?: "resume" | "abort";
  values?: Record<string, unknown> | null;
  checkpointId?: string | null;
  breakpoints?: Breakpoints;
}

export function resumeRun(
  runId: string,
  { action = "resume", values, checkpointId, breakpoints = NO_BREAKPOINTS }: ResumeOptions = {},
) {
  return post<{ run_id: string; resumed: boolean; worker: "existing" | "new" }>(`/agent/runs/${seg(runId)}/resume`, {
    action,
    values: values ?? null,
    checkpoint_id: checkpointId ?? null,
    breakpoints: breakpoints.before,
    breakpoints_after: breakpoints.after,
  });
}

/**
 * Whether editing state at this step will be refused.
 *
 * The server raises `ParallelStep` when the checkpoint being resumed from had
 * more than one task queued -- the triage fan-out, the four lenses, the verify
 * pass -- because there is no single node to attribute the write to. The
 * client can see that coming from the parent's queue, which is worth doing:
 * otherwise you type an edit, press fork, get a 200, and nothing happens.
 */
export function isFanOut(parentNext: string[] | undefined): boolean {
  return (parentNext?.length ?? 0) > 1;
}

/**
 * Stop a running scan, keeping what it has already found.
 *
 * Not `resumeRun({action: "abort"})`, which steers a worker *waiting* at a
 * breakpoint by handing it an answer -- nothing reads that queue unless the
 * graph has parked, and this surface sets no breakpoints, so 중단 was refused on
 * every scan it was pressed on. This sets a flag the graph loop checks instead.
 *
 * The run ends as `cancelled` rather than `done`, because stopping is neither
 * finishing nor failing.
 */
export function cancelRun(runId: string): Promise<{ run_id: string; cancelled: boolean }> {
  return post<{ run_id: string; cancelled: boolean }>(`/agent/runs/${seg(runId)}/cancel`);
}
