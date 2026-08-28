import { seg, streamUrl } from "./client";
import type { Finding, IndexStats } from "./types";

/**
 * The run's event stream.
 *
 * Server-sent events, one channel per run, in-process on the server and *not*
 * replayable: a page opened mid-run has missed everything before it attached.
 * So REST stays the source of truth and this is only a signal to re-read.
 *
 * Two things about the server that shape every caller:
 *
 *  - It ends the stream when a run finishes. Starting another run has to
 *    reattach first, or the second run executes with nobody listening.
 *  - Every listener now gets its own queue server-side, so a second tab no
 *    longer takes frames away from the first. One EventSource per tab is still
 *    the rule -- two streams in one tab would double every patch this module
 *    applies to the cache -- which is why it is only used by the run provider.
 */

export interface RunStartedEvent extends IndexStats {
  run_id: string;
}
export interface WaveEvent {
  chunks: string[];
  remaining: number;
}
export interface ChunkStartedEvent {
  chunk_id: string;
  /** Null for a chunk the index no longer has, which is not worth crashing over. */
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

/** Every event the backend emits. Thirteen; the old clients handled 7 and 4. */
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
  /** A state edit at a fan-out step. Handled nowhere before this rewrite. */
  onResumeRefused?: (event: RefusedEvent) => void;
  onFinished?: (event: FinishedEvent) => void;
  onFailed?: (event: FailedEvent) => void;
  onClosed?: () => void;
  /** The socket dropped rather than the server closing it. */
  onDropped?: () => void;
  /**
   * The connection failed and the browser is retrying by itself.
   *
   * Reported rather than left to EventSource, because the retry is invisible:
   * the last events received stay on screen and a run whose server has gone
   * away reads as still running, for as long as anyone watches it.
   */
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
        /* a malformed frame must not take the stream down with it */
      }
    });
  }

  source.addEventListener("stream_closed", () => {
    // The server ends the response normally when a run finishes. Left alone,
    // EventSource would treat that as a drop and reconnect -- and any GET
    // creates a channel, so the reconnect would sit there holding an idle one.
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
    // CONNECTING: the browser retries on its own, so there is nothing to do
    // about the socket -- but somebody has to say so, or the view keeps
    // showing the last frame it got as though it were current.
    handlers.onRetrying?.();
  };

  return () => {
    closedByServer = true;
    source.close();
  };
}
