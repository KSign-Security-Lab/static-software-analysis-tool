"use client";

import { useCallback, useEffect, useReducer, useRef } from "react";

import { watchRun, type CheckpointEvent, type InterruptEvent, type NodeEvent } from "@/lib/api/studio";

/**
 * Where a run is, right now.
 *
 * The old view polled every two seconds: too often for a finished run, and far
 * too slow to answer "which node is running". These come from the graph itself,
 * one event per node, so the canvas moves in step with the work rather than
 * catching up to it.
 */

export interface RunLive {
  /**
   * The nodes executing now. A list because they genuinely are several: a wave
   * of chunks screens in parallel, four specialists read one chunk at once, and
   * a handful of findings are refuted at the same time. One name here would
   * have shown whichever event arrived last and hidden the rest.
   */
  running: string[];
  /** Queued at the breakpoint the run is stopped at. */
  queued: string[];
  /** Set while the run is waiting for a person. */
  interrupted: boolean;
  /** Where it stopped, which is what a resume or an edit is addressed to. */
  checkpointId: string | null;
  /** Nodes this run has entered, for the "been here" state on the canvas. */
  visited: Set<string>;
  /** True between the first event and `run_finished`. */
  active: boolean;
  finished: boolean;
  error: string | null;
  /** Bumped whenever the stored history changed, so views refetch just then. */
  revision: number;
}

export const IDLE: RunLive = {
  running: [],
  queued: [],
  interrupted: false,
  checkpointId: null,
  visited: new Set(),
  active: false,
  finished: false,
  error: null,
  revision: 0,
};

export type RunAction =
  | { type: "reset" }
  | { type: "node_started"; event: NodeEvent }
  | { type: "node_finished"; event: NodeEvent }
  | { type: "checkpoint"; event: CheckpointEvent }
  | { type: "interrupted"; event: InterruptEvent }
  | { type: "resumed" }
  | { type: "finished" }
  | { type: "failed"; error: string };

export function reduceRun(state: RunLive, action: RunAction): RunLive {
  switch (action.type) {
    case "reset":
      return { ...IDLE, visited: new Set() };

    case "node_started": {
      const node = action.event.node;
      if (!node) return state;
      const visited = new Set(state.visited);
      visited.add(node);
      // Counted, not set: four `injection` tasks start and finish
      // independently, and the node stops running when the last one does.
      return {
        ...state,
        running: [...state.running, node],
        visited,
        active: true,
        finished: false,
        interrupted: false,
      };
    }

    case "node_finished": {
      // One instance removed, not every instance: the other three specialists
      // are still going.
      const at = state.running.indexOf(action.event.node ?? "");
      return {
        ...state,
        running: at < 0 ? state.running : [...state.running.slice(0, at), ...state.running.slice(at + 1)],
        error: action.event.error ?? state.error,
      };
    }

    case "checkpoint":
      // A new checkpoint means the stored history changed. Everything read
      // from disk -- the timeline, the state, the trace -- refetches on this
      // rather than on a timer.
      return {
        ...state,
        checkpointId: action.event.checkpoint_id ?? state.checkpointId,
        queued: action.event.next,
        revision: state.revision + 1,
      };

    case "interrupted":
      return {
        ...state,
        running: [],
        interrupted: true,
        active: true,
        queued: action.event.next,
        checkpointId: action.event.checkpoint_id ?? state.checkpointId,
        revision: state.revision + 1,
      };

    case "resumed":
      return { ...state, interrupted: false, active: true };

    case "finished":
      return { ...state, running: [], interrupted: false, queued: [], active: false, finished: true, revision: state.revision + 1 };

    case "failed":
      return { ...state, running: [], interrupted: false, active: false, error: action.error, revision: state.revision + 1 };

    default:
      return state;
  }
}

/**
 * Subscribe to one run.
 *
 * The stream is in-process on the server, so a page opened after a run started
 * has missed its earlier events. That is what `revision` is for: views load
 * their state once on mount and then follow it, instead of trying to rebuild
 * the past from events that are gone.
 *
 * `reconnect` exists because the server ends the stream when a run finishes.
 * Starting another one has to reattach first, or the second run would execute
 * with nobody listening.
 */
export function useRunStream(runId: string | null): RunLive & { reconnect: () => void } {
  const [state, dispatch] = useReducer(reduceRun, IDLE);
  const close = useRef<(() => void) | null>(null);
  const open = useRef(false);

  const subscribe = useCallback((id: string) => {
    close.current?.();
    open.current = true;
    close.current = watchRun(id, {
      onNodeStarted: (event) => dispatch({ type: "node_started", event }),
      onNodeFinished: (event) => dispatch({ type: "node_finished", event }),
      onCheckpoint: (event) => dispatch({ type: "checkpoint", event }),
      onInterrupted: (event) => dispatch({ type: "interrupted", event }),
      onResumed: () => dispatch({ type: "resumed" }),
      onFinished: () => dispatch({ type: "finished" }),
      onFailed: ({ error }) => dispatch({ type: "failed", error }),
      onClosed: () => {
        open.current = false;
      },
    });
  }, []);

  useEffect(() => {
    dispatch({ type: "reset" });
    close.current?.();
    close.current = null;
    open.current = false;
    if (!runId) return;

    subscribe(runId);
    return () => {
      close.current?.();
      close.current = null;
      open.current = false;
    };
  }, [runId, subscribe]);

  const reconnect = useCallback(() => {
    // Already attached is the common case -- reattaching would drop events
    // that are in flight for no reason.
    if (!runId || open.current) return;
    subscribe(runId);
  }, [runId, subscribe]);

  return { ...state, reconnect };
}
