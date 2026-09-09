import { get, post, seg, type RequestOptions } from "./client";
import type { GraphShape } from "./types";

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

export interface StartResult {
  run_id: string;
  status: string;
  already_running: boolean;
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

export function isFanOut(parentNext: string[] | undefined): boolean {
  return (parentNext?.length ?? 0) > 1;
}

export function cancelRun(runId: string): Promise<{ run_id: string; cancelled: boolean }> {
  return post<{ run_id: string; cancelled: boolean }>(`/agent/runs/${seg(runId)}/cancel`);
}
