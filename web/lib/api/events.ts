import { seg, streamUrl } from "./client";
import type { Finding, IndexStats } from "./types";

export interface RunStartedEvent extends IndexStats {
  run_id: string;
}
export interface WaveEvent {
  chunks: string[];
  remaining: number;
}
export interface ChunkStartedEvent {
  chunk_id: string;
  file: string | null;
  symbol: string | null;
  remaining: number;
  total: number;
}
export interface ChunkFinishedEvent {
  chunk_id: string;
  file: string;
  symbol: string;
  findings: Finding[];
  stats: Record<string, number>;
}
export interface NodeEvent {
  node: string | null;
  step: number | null;
  error?: string | null;
  updates?: Record<string, unknown>;
}
export interface CheckpointEvent {
  checkpoint_id: string | null;
  step: number | null;
  node: string | null;
  next: string[];
}
export interface InterruptEvent {
  run_id: string;
  next: string[];
  checkpoint_id: string | null;
}
export interface RefusedEvent {
  run_id: string;
  error: string;
}
export interface FinishedEvent {
  run_id: string;
  findings: number;
  aborted: boolean;
}
export interface FailedEvent {
  error: string;
}

export interface RunHandlers {
  onOpen?: () => void;
  onRunStarted?: (event: RunStartedEvent) => void;
  onWaveStarted?: (event: WaveEvent) => void;
  onChunkStarted?: (event: ChunkStartedEvent) => void;
  onChunkFinished?: (event: ChunkFinishedEvent) => void;
  onNodeStarted?: (event: NodeEvent) => void;
  onNodeFinished?: (event: NodeEvent) => void;
  onCheckpoint?: (event: CheckpointEvent) => void;
  onInterrupted?: (event: InterruptEvent) => void;
  onResumed?: () => void;
  onResumeRefused?: (event: RefusedEvent) => void;
  onFinished?: (event: FinishedEvent) => void;
  onFailed?: (event: FailedEvent) => void;
  onClosed?: () => void;
  onDropped?: () => void;
  onRetrying?: () => void;
}

const NAMES = [
  ["run_started", "onRunStarted"],
  ["wave_started", "onWaveStarted"],
  ["chunk_started", "onChunkStarted"],
  ["chunk_finished", "onChunkFinished"],
  ["node_started", "onNodeStarted"],
  ["node_finished", "onNodeFinished"],
  ["checkpoint", "onCheckpoint"],
  ["run_interrupted", "onInterrupted"],
  ["run_resumed", "onResumed"],
  ["resume_refused", "onResumeRefused"],
  ["run_finished", "onFinished"],
  ["run_failed", "onFailed"],
] as const;

export function watchRun(runId: string, handlers: RunHandlers): () => void {
  const source = new EventSource(streamUrl(`/agent/runs/${seg(runId)}/events`));
  let closedByServer = false;

  source.addEventListener("open", () => handlers.onOpen?.());

  for (const [event, handler] of NAMES) {
    source.addEventListener(event, (message) => {
      const callback = handlers[handler] as ((payload: unknown) => void) | undefined;
      if (!callback) return;
      try {
        callback(JSON.parse((message as MessageEvent<string>).data));
      } catch {
      }
    });
  }

  source.addEventListener("stream_closed", () => {
    closedByServer = true;
    source.close();
    handlers.onClosed?.();
  });

  source.onerror = () => {
    if (closedByServer) return;
    if (source.readyState === EventSource.CLOSED) {
      handlers.onClosed?.();
      handlers.onDropped?.();
      return;
    }
    handlers.onRetrying?.();
  };

  return () => {
    closedByServer = true;
    source.close();
  };
}
