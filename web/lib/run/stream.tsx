"use client";

import { useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useMemo, useReducer, useRef, type ReactNode } from "react";
import { toast } from "sonner";

import { watchRun } from "@/lib/api/events";
import type { Report } from "@/lib/api/types";
import { isScanning } from "@/lib/inspect/stage";
import { InvalidationQueue } from "@/lib/query/invalidation";
import { keys, recordedKeys } from "@/lib/query/keys";
import { useRun } from "./queries";
import { IDLE, phaseOf, reduceRun, type RunLive, type RunPhase } from "./reduce";

export interface RunStream {
  runId: string | null;
  live: RunLive;
  phase: RunPhase;
  ensureAttached: () => Promise<void>;
  dismissRefusal: () => void;
  markCancelling: () => void;
  clearCancelling: () => void;
}

const StreamContext = createContext<RunStream | null>(null);

const ATTACH_CEILING_MS = 2000;

const RECOVERY_POLL_MS = 2000;

const REATTACH_MIN_MS = 1000;
const REATTACH_MAX_MS = 15_000;

export function RunStreamProvider({ runId, children }: { runId: string | null; children: ReactNode }) {
  const client = useQueryClient();
  const [live, dispatch] = useReducer(reduceRun, IDLE);

  const close = useRef<(() => void) | null>(null);
  const opened = useRef(false);
  const dropped = useRef(false);
  const waiting = useRef<(() => void)[]>([]);

  const invalidations = useMemo(() => new InvalidationQueue(client), [client]);

  const resolveWaiters = useCallback(() => {
    const pending = waiting.current;
    waiting.current = [];
    for (const resolve of pending) resolve();
  }, []);

  const attach = useCallback(
    (id: string) => {
      close.current?.();
      opened.current = false;

      close.current = watchRun(id, {
        onOpen: () => {
          opened.current = true;
          dispatch({ type: "attached", open: true });
          resolveWaiters();
          if (dropped.current) {
            dropped.current = false;
            invalidations.add(keys.summary(id), ...recordedKeys(id));
            const row = client.getQueryData<{ status?: string }>(keys.summary(id));
            if (row?.status !== "inspecting") invalidations.add(keys.findings(id));
            invalidations.flush();
          }
        },

        onRunStarted: (event) => {
          dispatch({ type: "run_started", event });
          client.setQueryData(keys.summary(id), (previous: unknown) =>
            previous
              ? { ...previous, status: "inspecting", index: { ...event, run_id: undefined } }
              : previous,
          );
        },

        onChunkFinished: (event) => {
          dispatch({ type: "chunk_finished", event });
          client.setQueryData<Report | undefined>(keys.findings(id), (previous) => {
            const merged = new Map((previous?.findings ?? []).map((finding) => [finding.id, finding]));
            for (const finding of event.findings) merged.set(finding.id, finding);
            return {
              schema_version: "1",
              run_id: id,
              findings: [...merged.values()],
              stats: { ...(previous?.stats ?? {}), ...event.stats },
            };
          });
        },

        onWaveStarted: (event) => dispatch({ type: "wave_started", event }),
        onChunkStarted: (event) => dispatch({ type: "chunk_started", event }),
        onNodeStarted: (event) => dispatch({ type: "node_started", event }),

        onNodeFinished: (event) => {
          dispatch({ type: "node_finished", event });
          if (event.error) {
            toast.error(`${event.node ?? "노드"} 실패`, { description: event.error });
          }
        },

        onCheckpoint: (event) => {
          dispatch({ type: "checkpoint", event });
          invalidations.add(...recordedKeys(id));
        },

        onInterrupted: (event) => {
          dispatch({ type: "interrupted", event });
          invalidations.add(keys.summary(id), ...recordedKeys(id));
        },

        onResumed: () => {
          dispatch({ type: "resumed" });
          invalidations.add(keys.summary(id));
        },

        onResumeRefused: (event) => {
          dispatch({ type: "refused", event });
          toast.warning("상태 편집이 거부되었습니다", { description: event.error, duration: Infinity });
        },

        onFinished: (event) => {
          dispatch({ type: "finished", event });
          invalidations.add(keys.run(id), keys.runs());
          invalidations.flush();
          if (event.aborted) toast.info("실행이 중단되었습니다");
        },

        onFailed: (event) => {
          dispatch({ type: "failed", event });
          invalidations.add(keys.summary(id));
          invalidations.flush();
          toast.error("실행 실패", { description: event.error, duration: Infinity });
        },

        onClosed: () => {
          opened.current = false;
          dispatch({ type: "attached", open: false });
          invalidations.flush();
          resolveWaiters();
        },

        onDropped: () => {
          dropped.current = true;
          invalidations.add(keys.summary(id));
          invalidations.flush();
        },

        onRetrying: () => {
          opened.current = false;
          dropped.current = true;
          dispatch({ type: "attached", open: false });
        },
      });
    },
    [client, invalidations, resolveWaiters],
  );

  useEffect(() => {
    dispatch({ type: "reset" });
    close.current?.();
    close.current = null;
    opened.current = false;
    dropped.current = false;
    if (!runId) return;

    attach(runId);
    return () => {
      close.current?.();
      close.current = null;
      opened.current = false;
      invalidations.cancel();
    };
  }, [runId, attach, invalidations]);

  const record = useRun(runId, (row) => {
    if (live.cancelling) return 1000;
    return isScanning({ run: row, live }) && !live.attached ? RECOVERY_POLL_MS : false;
  }).data;
  const parked = record?.parked;
  const inFlight = useMemo(
    () => (record?.status === "inspecting" ? (record.progress?.next ?? []) : null),
    [record],
  );
  const heard = live.active || live.interrupted;

  const stalled = Boolean(runId) && isScanning({ run: record, live }) && !live.attached;

  useEffect(() => {
    if (!runId || !stalled) return;
    let stop = false;
    let tries = 0;
    let timer: ReturnType<typeof setTimeout>;
    const schedule = () => {
      timer = setTimeout(
        () => {
          if (stop) return;
          tries += 1;
          dropped.current = true;
          attach(runId);
          schedule();
        },
        Math.min(REATTACH_MIN_MS * 2 ** tries, REATTACH_MAX_MS),
      );
    };
    schedule();
    return () => {
      stop = true;
      clearTimeout(timer);
    };
  }, [runId, stalled, attach]);

  useEffect(() => {
    if (!runId || heard) return;
    if (parked) {
      dispatch({
        type: "interrupted",
        event: { run_id: runId, next: parked.next, checkpoint_id: parked.checkpoint_id },
      });
    } else if (inFlight) {
      dispatch({ type: "adopted", running: inFlight });
    }
  }, [runId, heard, parked, inFlight]);

  const ensureAttached = useCallback(async () => {
    if (!runId || opened.current) return;
    attach(runId);
    await new Promise<void>((resolve) => {
      const timer = setTimeout(() => {
        waiting.current = waiting.current.filter((each) => each !== waiter);
        resolve();
      }, ATTACH_CEILING_MS);
      const waiter = () => {
        clearTimeout(timer);
        resolve();
      };
      waiting.current.push(waiter);
    });
  }, [runId, attach]);

  const value = useMemo<RunStream>(
    () => ({
      runId,
      live,
      phase: phaseOf(live),
      ensureAttached,
      dismissRefusal: () => dispatch({ type: "dismiss_refusal" }),
      markCancelling: () => dispatch({ type: "cancelling" }),
      clearCancelling: () => dispatch({ type: "cancel_failed" }),
    }),
    [runId, live, ensureAttached],
  );

  return <StreamContext.Provider value={value}>{children}</StreamContext.Provider>;
}

export function useRunStream(): RunStream {
  const stream = useContext(StreamContext);
  if (!stream) throw new Error("useRunStream must be used inside <RunStreamProvider>");
  return stream;
}
