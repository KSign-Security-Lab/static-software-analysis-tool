import type {
  CheckpointEvent,
  ChunkStartedEvent,
  FailedEvent,
  FinishedEvent,
  InterruptEvent,
  NodeEvent,
  RefusedEvent,
  RunStartedEvent,
  WaveEvent,
} from "@/lib/api/events";

/**
 * Where a run is, right now.
 *
 * The old view polled every two seconds: too often for a finished run, and far
 * too slow to answer "which node is running". These come from the graph
 * itself, one event per node, so the canvas moves in step with the work rather
 * than catching up to it.
 *
 * A pure reducer, deliberately -- the store calls it and the tests call it
 * directly, so the semantics below stay covered without a browser.
 */

export type RunPhase = "idle" | "starting" | "running" | "paused" | "finished" | "failed";

export interface RunLive {
  /**
   * The nodes executing now. A list because they genuinely are several: a wave
   * of chunks screens in parallel, four specialists read one chunk at once,
   * and a handful of findings are refuted at the same time. One name here
   * would have shown whichever event arrived last and hidden the rest.
   */
  running: string[];
  /** Queued at the breakpoint the run is stopped at. */
  queued: string[];
  interrupted: boolean;
  /** Where it stopped, which is what a resume or an edit is addressed to. */
  checkpointId: string | null;
  /** Nodes this run has entered, for the "been here" state on the canvas. */
  visited: Set<string>;
  active: boolean;
  finished: boolean;
  error: string | null;
  /**
   * A refusal to apply a state edit. Kept until dismissed: the run is still
   * parked at the same checkpoint, so this is not transient information.
   */
  refusal: string | null;
  /** Chunk progress, which only the inspect view used to have. */
  chunk: { id: string; remaining: number; total: number } | null;
  wave: { chunks: string[]; remaining: number } | null;
  /** Whether an EventSource is currently open. */
  attached: boolean;
  /** Bumped whenever the stored history changed, so views can key off it. */
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
  refusal: null,
  chunk: null,
  wave: null,
  attached: false,
  revision: 0,
};

export type RunAction =
  | { type: "reset" }
  | { type: "attached"; open: boolean }
  | { type: "run_started"; event: RunStartedEvent }
  | { type: "wave_started"; event: WaveEvent }
  | { type: "chunk_started"; event: ChunkStartedEvent }
  | { type: "chunk_finished" }
  | { type: "node_started"; event: NodeEvent }
  | { type: "node_finished"; event: NodeEvent }
  | { type: "checkpoint"; event: CheckpointEvent }
  | { type: "interrupted"; event: InterruptEvent }
  | { type: "resumed" }
  | { type: "refused"; event: RefusedEvent }
  | { type: "dismiss_refusal" }
  | { type: "finished"; event: FinishedEvent }
  | { type: "failed"; event: FailedEvent };

export function reduceRun(state: RunLive, action: RunAction): RunLive {
  switch (action.type) {
    case "reset":
      return { ...IDLE, visited: new Set(), attached: state.attached };

    case "attached":
      return state.attached === action.open ? state : { ...state, attached: action.open };

    case "run_started":
      return { ...state, active: true, finished: false, error: null, refusal: null };

    case "wave_started":
      return { ...state, wave: { chunks: action.event.chunks, remaining: action.event.remaining }, active: true };

    case "chunk_started":
      return {
        ...state,
        chunk: { id: action.event.chunk_id, remaining: action.event.remaining, total: action.event.total },
        active: true,
      };

    case "chunk_finished":
      // The findings ride along on this event and are merged into the cache by
      // the bridge; nothing about *where the run is* changes here.
      return state;

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
      return { ...state, interrupted: false, active: true, refusal: null };

    case "refused":
      // The run did not move: the server emits this and goes straight back to
      // waiting at the same checkpoint. Nothing about position changes, and
      // nothing should be refetched -- doing so would suggest it had.
      return { ...state, refusal: action.event.error };

    case "dismiss_refusal":
      return state.refusal === null ? state : { ...state, refusal: null };

    case "finished":
      return {
        ...state,
        running: [],
        interrupted: false,
        queued: [],
        chunk: null,
        wave: null,
        active: false,
        finished: true,
        revision: state.revision + 1,
      };

    case "failed":
      return {
        ...state,
        running: [],
        interrupted: false,
        active: false,
        error: action.event.error,
        revision: state.revision + 1,
      };

    default:
      return state;
  }
}

/**
 * One word for the run's state, derived rather than stored.
 *
 * Callers used to recombine `active`/`finished`/`interrupted` by hand at each
 * site, and got the edge cases subtly different from one another.
 */
export function phaseOf(state: RunLive): RunPhase {
  if (state.error) return "failed";
  if (state.interrupted) return "paused";
  if (state.running.length > 0) return "running";
  if (state.active) return "starting";
  if (state.finished) return "finished";
  return "idle";
}
