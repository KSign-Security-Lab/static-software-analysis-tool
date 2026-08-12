import type {
  CheckpointEvent,
  ChunkFinishedEvent,
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
   * of chunks screens in parallel, the specialists read one chunk at once,
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
  /**
   * The chunks started and not yet finished, by the file each is in.
   *
   * Keyed by chunk rather than collected into a set of files, because a wave is
   * several chunks at once and two of them are often two functions of the same
   * file: a set could only be added to, and the file would still read as being
   * read long after it was done.
   */
  inflight: Map<string, string>;
  /**
   * Files at least one chunk of which has come back.
   *
   * Progress, not completeness. Nothing on the wire says how many chunks a file
   * has, so this cannot mean "finished" -- it means the agent has been here.
   */
  scanned: Set<string>;
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
  inflight: new Map(),
  scanned: new Set(),
  attached: false,
  revision: 0,
};

export type RunAction =
  | { type: "reset" }
  | { type: "attached"; open: boolean }
  | { type: "run_started"; event: RunStartedEvent }
  | { type: "wave_started"; event: WaveEvent }
  | { type: "chunk_started"; event: ChunkStartedEvent }
  | { type: "chunk_finished"; event: ChunkFinishedEvent }
  | { type: "node_started"; event: NodeEvent }
  | { type: "node_finished"; event: NodeEvent }
  | { type: "checkpoint"; event: CheckpointEvent }
  | { type: "interrupted"; event: InterruptEvent }
  /** Where the run already was when this tab arrived. See `adopted`, below. */
  | { type: "adopted"; running: string[] }
  | { type: "resumed" }
  | { type: "refused"; event: RefusedEvent }
  | { type: "dismiss_refusal" }
  | { type: "finished"; event: FinishedEvent }
  | { type: "failed"; event: FailedEvent };

export function reduceRun(state: RunLive, action: RunAction): RunLive {
  switch (action.type) {
    // Fresh collections each time: IDLE's would be shared by every run that reset.
    case "reset":
      return { ...IDLE, visited: new Set(), inflight: new Map(), scanned: new Set(), attached: state.attached };

    case "attached":
      return state.attached === action.open ? state : { ...state, attached: action.open };

    case "run_started":
      return {
        ...state,
        active: true,
        finished: false,
        error: null,
        refusal: null,
        inflight: new Map(),
        scanned: new Set(),
      };

    /**
     * A run that was already going when this tab opened.
     *
     * The stream is in-process and never replayed, so arriving late means
     * having missed `run_started` and every `node_started`: the phase reads
     * idle, the canvas paints nothing in flight, and 검사 실행 offers to start
     * a run that is already running. This is the run record saying otherwise.
     *
     * `running` comes from the last checkpoint's `next` -- the tasks queued
     * for the step now executing. Marked visited too, since reaching them
     * means the graph came through them.
     */
    case "adopted":
      return {
        ...state,
        active: true,
        finished: false,
        error: null,
        running: action.running,
        visited: new Set([...state.visited, ...action.running]),
      };

    case "wave_started":
      return { ...state, wave: { chunks: action.event.chunks, remaining: action.event.remaining }, active: true };

    case "chunk_started": {
      const { chunk_id, file, remaining, total } = action.event;
      const inflight = new Map(state.inflight);
      if (file) inflight.set(chunk_id, file);
      return {
        ...state,
        chunk: { id: chunk_id, remaining, total },
        inflight,
        active: true,
      };
    }

    case "chunk_finished": {
      // The findings ride along on this event and are merged into the cache by
      // the bridge. What changes here is only where the work is.
      const { chunk_id, file } = action.event;
      const inflight = new Map(state.inflight);
      inflight.delete(chunk_id);
      return {
        ...state,
        inflight,
        scanned: file ? new Set(state.scanned).add(file) : state.scanned,
      };
    }

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
        // Nothing is being read any more. `scanned` stays: it is what the run
        // got through, and an aborted run is exactly when that is worth seeing.
        inflight: new Map(),
        active: false,
        finished: true,
        revision: state.revision + 1,
      };

    case "failed":
      return {
        ...state,
        running: [],
        interrupted: false,
        inflight: new Map(),
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
/**
 * The files being read right now.
 *
 * Derived rather than stored, for the same reason `phaseOf` is: two chunks of
 * one file are two entries in `inflight` and one entry here, and keeping both
 * in the state means keeping them agreeing.
 */
export function scanningFiles(state: RunLive): Set<string> {
  return new Set(state.inflight.values());
}

export function phaseOf(state: RunLive): RunPhase {
  if (state.error) return "failed";
  if (state.interrupted) return "paused";
  if (state.running.length > 0) return "running";
  if (state.active) return "starting";
  if (state.finished) return "finished";
  return "idle";
}
