import type {
  CheckpointEvent,
  ChunkFinishedEvent,
  ChunkStartedEvent,
  RunProgressEvent,
  FailedEvent,
  FinishedEvent,
  InterruptEvent,
  NodeEvent,
  RefusedEvent,
  RunStartedEvent,
  WaveEvent,
} from "@/lib/api/events";
import type { RunStatus } from "@/lib/api/types";

export type RunPhase = "idle" | "starting" | "running" | "paused" | "finished" | "failed";

export interface RunLive {
  running: string[];
  queued: string[];
  interrupted: boolean;
  checkpointId: string | null;
  visited: Set<string>;
  active: boolean;
  finished: boolean;
  error: string | null;
  refusal: string | null;
  chunk: { id: string; remaining: number; total: number } | null;
  wave: { chunks: string[]; remaining: number } | null;
  inflight: Map<string, string>;
  scanned: Set<string>;
  done: Set<string>;
  cancelling: boolean;
  attached: boolean;
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
  done: new Set(),
  cancelling: false,
  attached: false,
  revision: 0,
};

export type RunAction =
  | { type: "reset" }
  | { type: "attached"; open: boolean }
  | { type: "run_started"; event: RunStartedEvent }
  | { type: "wave_started"; event: WaveEvent }
  | { type: "progress"; event: RunProgressEvent }
  | { type: "chunk_started"; event: ChunkStartedEvent }
  | { type: "chunk_finished"; event: ChunkFinishedEvent }
  | { type: "node_started"; event: NodeEvent }
  | { type: "node_finished"; event: NodeEvent }
  | { type: "checkpoint"; event: CheckpointEvent }
  | { type: "interrupted"; event: InterruptEvent }
  | { type: "adopted"; running: string[] }
  | { type: "resumed" }
  | { type: "cancelling" }
  | { type: "cancel_failed" }
  | { type: "refused"; event: RefusedEvent }
  | { type: "dismiss_refusal" }
  | { type: "finished"; event: FinishedEvent }
  | { type: "failed"; event: FailedEvent };

export function reduceRun(state: RunLive, action: RunAction): RunLive {
  switch (action.type) {
    case "reset":
      return { ...IDLE, visited: new Set(), inflight: new Map(), scanned: new Set(), done: new Set(), attached: state.attached };

    case "attached":
      return state.attached === action.open ? state : { ...state, attached: action.open };

    case "cancelling":
      return state.cancelling ? state : { ...state, cancelling: true };

    case "cancel_failed":
      return state.cancelling ? { ...state, cancelling: false } : state;

    case "run_started":
      return {
        ...IDLE,
        visited: new Set(),
        inflight: new Map(),
        scanned: new Set(),
        done: new Set(),
        attached: state.attached,
        active: true,
        revision: state.revision + 1,
      };

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

    case "progress": {
      const { remaining, total } = action.event;
      // Only seeds an empty bar. A live chunk event always knows better.
      if (total <= 0 || state.chunk) return state;
      return { ...state, chunk: { id: "", remaining, total } };
    }

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
      const { chunk_id, file } = action.event;
      const inflight = new Map(state.inflight);
      inflight.delete(chunk_id);
      return {
        ...state,
        inflight,
        scanned: file ? new Set(state.scanned).add(file) : state.scanned,
        done: new Set(state.done).add(chunk_id),
      };
    }

    case "node_started": {
      const node = action.event.node;
      if (!node) return state;
      const visited = new Set(state.visited);
      visited.add(node);
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
      const at = state.running.indexOf(action.event.node ?? "");
      return {
        ...state,
        running: at < 0 ? state.running : [...state.running.slice(0, at), ...state.running.slice(at + 1)],
        error: action.event.error ?? state.error,
      };
    }

    case "checkpoint":
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
        inflight: new Map(),
        active: false,
        finished: true,
        cancelling: false,
        revision: state.revision + 1,
      };

    case "failed":
      return {
        ...state,
        running: [],
        interrupted: false,
        inflight: new Map(),
        active: false,
        cancelling: false,
        error: action.event.error,
        revision: state.revision + 1,
      };

    default:
      return state;
  }
}

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

export function phaseFor(live: RunPhase, status: RunStatus | undefined): RunPhase {
  if (live !== "idle" || !status) return live;
  switch (status) {
    case "inspecting":
      return "running";
    case "interrupted":
      return "paused";
    case "done":
      return "finished";
    case "failed":
      return "failed";
    default:
      return "idle";
  }
}
