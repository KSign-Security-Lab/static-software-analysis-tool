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

/**
 * One EventSource per tab, owned by the shell.
 *
 * Not a nicety. The server's channel used to be one `queue.Queue` whose reader
 * pops, so two subscribers on one run *split* its events -- each frame reaching
 * exactly one of them. The previous app had the inspect page and the trace page
 * each open their own, and navigated from one to the other while both were
 * attached. `RunChannel` fans out per listener now, but this still mounts once
 * above the routes: two streams in one tab would apply every cache patch below
 * twice.
 *
 * The stream is a signal, not a source of truth: it is in-process and cannot
 * be replayed, so a page opened mid-run has missed everything before it. REST
 * answers "what is true", this answers "something changed, go and look".
 */

export interface RunStream {
  runId: string | null;
  live: RunLive;
  phase: RunPhase;
  /**
   * Resolve once the server is actually reading the channel.
   *
   * Must be awaited before starting or resuming a run: the server ends the
   * stream when a run finishes, so a second run would otherwise execute with
   * nobody listening. Resolving on `open` rather than on construction closes
   * the (small, real) race where the worker is spawned before FastAPI has
   * begun pulling the queue.
   */
  ensureAttached: () => Promise<void>;
  dismissRefusal: () => void;
  /**
   * Say that 중단 has been accepted, so the surface stops claiming the scan is
   * simply carrying on.
   *
   * Here rather than derived from the run row, because the row still says
   * `inspecting` -- correctly: the wave in flight is still finishing. This is
   * the one fact only the tab that pressed the button knows.
   */
  markCancelling: () => void;
  /**
   * Take that claim back, because the server did not accept the stop.
   *
   * A 409 is easy to get: press 중단 in the window between the worker's last
   * frame and its `finally`. Nothing cleared the flag afterwards, so 중단 was
   * disabled for the rest of the run and a 1s poll sat behind it.
   */
  clearCancelling: () => void;
}

const StreamContext = createContext<RunStream | null>(null);

const ATTACH_CEILING_MS = 2000;

/** How often the row is asked while the surface believes a scan it cannot see. */
const RECOVERY_POLL_MS = 2000;

/** The re-attach backoff: the usual reason for not being attached is a dead server. */
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
    // Swapped before calling: a waiter that removes itself must not race this.
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
          // Everything that happened while the socket was down is gone -- the
          // stream is in-process and does not replay -- so the only way back
          // to the truth is to read it.
          if (dropped.current) {
            dropped.current = false;
            // The row always; the report only once the run is over. `keys.run`
            // is a prefix of `keys.findings`, and re-reading the report mid-scan
            // is the one thing `onChunkFinished` below says never to do.
            invalidations.add(keys.summary(id), ...recordedKeys(id));
            const row = client.getQueryData<{ status?: string }>(keys.summary(id));
            if (row?.status !== "inspecting") invalidations.add(keys.findings(id));
            invalidations.flush();
          }
        },

        /* -- patched straight into the cache: the payload IS the delta ------ */

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
          // Never refetch /findings here. Mid-run it reads the whole store and
          // revalidates every row, at exactly the moment the server is busiest
          // -- and this event already carries the new findings.
          client.setQueryData<Report | undefined>(keys.findings(id), (previous) => {
            const merged = new Map((previous?.findings ?? []).map((finding) => [finding.id, finding]));
            // Ids are content-derived, so a re-inspected chunk re-emits the
            // same id and must replace rather than duplicate.
            for (const finding of event.findings) merged.set(finding.id, finding);
            return {
              schema_version: "1",
              run_id: id,
              findings: [...merged.values()],
              stats: { ...(previous?.stats ?? {}), ...event.stats },
            };
          });
        },

        /* -- signals: something on disk moved, go and re-read -------------- */

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
          // Deliberately no invalidation. The run is still parked at the same
          // checkpoint; re-reading would imply it had moved.
          dispatch({ type: "refused", event });
          toast.warning("상태 편집이 거부되었습니다", { description: event.error, duration: Infinity });
        },

        onFinished: (event) => {
          dispatch({ type: "finished", event });
          // The one place a full re-read is right: the report is on disk now
          // and supersedes everything that was streamed in piecemeal.
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
          // Anything still queued belongs to a run that has stopped; read it
          // now rather than leaving the view a window behind.
          invalidations.flush();
          resolveWaiters();
        },

        onDropped: () => {
          // A laptop that slept, or a restarted API. The events in the gap are
          // gone for good, but the server rebuilds from disk -- so re-reading
          // is what makes this recoverable at all. Re-attaching is the effect
          // below: a clean close never reconnects on its own.
          dropped.current = true;
          invalidations.add(keys.summary(id));
          invalidations.flush();
        },

        onRetrying: () => {
          // Not attached, and not finished either: the phase stands, and the
          // status bar says the picture is stale rather than pretending a run
          // with no server behind it is still moving.
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

  // What the run record says, for the one fact the stream cannot tell a tab
  // that arrived late. Only ever read when nothing has been heard: once an
  // event lands, the stream is ahead of anything REST would say.
  //
  // Polled in exactly two states, and the row decides both: a stop that has been
  // accepted but not yet finished, and a scan this tab is not attached to.
  // `attached` is a claim this tab makes; the row is the truth, and every race
  // in this file ends with the two disagreeing.
  const record = useRun(runId, (row) => {
    if (live.cancelling) return 1000;
    return isScanning({ run: row, live }) && !live.attached ? RECOVERY_POLL_MS : false;
  }).data;
  const parked = record?.parked;
  // Memoised: `?? []` is a fresh array every render, which would re-run the
  // effect below forever.
  const inFlight = useMemo(
    () => (record?.status === "inspecting" ? (record.progress?.next ?? []) : null),
    [record],
  );
  // Whether anything has been heard about the run that is live *now*. It used
  // to include `revision` and `finished`, which are facts about the last run on
  // this id -- so a second run whose stream was lost could never be adopted, and
  // the surface sat on the previous run's ending while the new one worked.
  const heard = live.active || live.interrupted;

  // Attached is a claim this tab makes; the row is the truth. This is where
  // every race in this file ends up, so it re-reads and re-attaches on its own.
  const stalled = Boolean(runId) && isScanning({ run: record, live }) && !live.attached;

  useEffect(() => {
    if (!runId || !stalled) return;
    // The chain reschedules itself rather than the effect re-running: `attach`
    // changes no state, so nothing would have re-run it and the retry fired
    // exactly once. `tries` living in the effect means the next stall starts
    // from the short wait -- a successful open clears `stalled` and this with it.
    let stop = false;
    let tries = 0;
    let timer: ReturnType<typeof setTimeout>;
    const schedule = () => {
      timer = setTimeout(
        () => {
          if (stop) return;
          tries += 1;
          // The gap is unreplayable, so whatever comes back has to be re-read.
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
    // React 19 StrictMode double-invokes effects, so this has to tolerate
    // being called twice; the waiter list is drained by whichever open wins.
    await new Promise<void>((resolve) => {
      // Removed on the way out, and it was not: the ceiling resolved the promise
      // and left the waiter on the list, which grew for the life of the tab.
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
