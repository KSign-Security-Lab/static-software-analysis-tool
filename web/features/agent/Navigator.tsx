"use client";

import { CircleStop, Loader2, Play } from "lucide-react";

import { Button } from "@/components/ui/button";
import ExplorerPane from "@/features/agent/ExplorerPane";
import RunHistory from "@/features/agent/RunHistory";
import RunMenu from "@/features/agent/RunMenu";
import { useRunControls } from "@/lib/run/controls";
import { useRun, useStartRun } from "@/lib/run/queries";
import { phaseFor, type RunLive, type RunPhase } from "@/lib/run/reduce";
import { useFilter, useOpenedByRun, useSelection } from "@/lib/run/selection";
import { useRunStream } from "@/lib/run/stream";
import { useResume } from "@/lib/run/trace-queries";
import { useRunId } from "@/lib/run/use-run-id";
import { cn } from "@/lib/utils";

/**
 * The left column: which run, what is in it, and the one button that fills it.
 *
 * This replaces a 36px strip that ran the width of the window. Everything on
 * that strip was either transient (the phase, the coverage), post-hoc (tokens,
 * duration) or pressed once per run (검사 실행, the run selector) -- permanent
 * chrome for information that is never permanently wanted, which is why moving
 * it around never helped. Taken apart, each piece has an obvious home:
 *
 * - the run selector titles this column, because this column lists what is in
 *   that run and nothing else on screen names it
 * - 검사 실행 is pinned at the foot, full width, the way a sidebar's primary
 *   action is everywhere else -- and it is next to the files it will read
 * - progress is the list itself, units and files changing state as the run
 *   moves, which is how a test runner shows it and needs no reserved row
 * - the cost and the funnel are in the right column, which is where the
 *   question "how much of this do I believe" is already being answered
 */
export default function Navigator() {
  const [runId] = useRunId();
  const { live, phase: streamed, ensureAttached } = useRunStream();
  const { breakpoints, dirty, saving, saveAll } = useRunControls();
  const { select } = useSelection();
  const [, setFilter] = useFilter();
  const [, setOpenedByRun] = useOpenedByRun();
  const run = useRun(runId);
  const resume = useResume(runId, ensureAttached);
  const start = useStartRun(runId, ensureAttached);

  const phase = phaseFor(streamed, run.data?.status);
  const running = phase === "running" || phase === "starting";
  const paused = phase === "paused";
  const files = run.data?.file_count ?? 0;

  /**
   * Save every changed file, start, then show it running.
   *
   * Owned here because this is the component with the button, and it is now the
   * only one -- the structure overlay is a reader and gave its copy up. Two
   * buttons for one action is fine; two actions wearing one label is a bug
   * waiting for the two to disagree about whether a run is in flight.
   *
   * `saveAll`, not "save the open one": an inspection reads the whole run, so a
   * file edited and navigated away from was being scanned in its old state.
   * The list widens to 전체 on success because a run in flight is only legible
   * as it moves, and on success rather than on click so a refused start leaves
   * you where you were.
   */
  const inspect = async () => {
    if (!runId) return;
    await saveAll();
    start.mutate(
      { breakpoints },
      {
        onSuccess: () => {
          void setOpenedByRun(true);
          void setFilter("all");
        },
      },
    );
  };

  return (
    <section className="flex h-full min-h-0 min-w-0 flex-col bg-surface">
      {/* Which run. One line, and the only place on the surface that says it. */}
      <header className="flex h-9 shrink-0 items-center gap-1 border-b border-line px-1.5">
        <RunHistory />
        <RunMenu className="ml-auto" />
      </header>

      {/* How far along, and only while that is a live question. A run that
          finished says so in the right column, with the cost. */}
      {(running || paused) && <Progress phase={phase} live={live} />}

      <div className="min-h-0 min-w-0 flex-1">
        <ExplorerPane />
      </div>

      {/* The action, against the floor and full width. It was 81x28 in the far
          corner of the window, indistinguishable from five ghost buttons. */}
      <div className="shrink-0 border-t border-line p-2">
        {paused ? (
          <Button
            className="w-full"
            size="sm"
            onClick={() => resume.mutate({ breakpoints })}
            disabled={resume.isPending}
          >
            <Play />
            이어서
          </Button>
        ) : running ? (
          <Button
            className="w-full"
            size="sm"
            variant="outline"
            onClick={() => resume.mutate({ action: "abort" })}
          >
            <CircleStop />
            중단
          </Button>
        ) : (
          <Button
            className="w-full"
            size="sm"
            onClick={() => void inspect()}
            disabled={!runId || saving || start.isPending}
          >
            <Play />
            {saving ? `${dirty.length}개 저장 중…` : files > 0 ? `검사 실행 · ${files}개 파일` : "검사 실행"}
          </Button>
        )}

        {/* Stopped at a breakpoint is a thing you can look at, and this is the
            only way to reach the checkpoint panel. */}
        {paused && live.checkpointId && (
          <Button
            size="xs"
            variant="ghost"
            className="mt-1 w-full text-warn"
            onClick={() => select({ kind: "state", id: live.checkpointId! })}
          >
            멈춘 지점 보기
          </Button>
        )}
      </div>
    </section>
  );
}

const PHASE_LABEL: Record<RunPhase, string> = {
  idle: "",
  starting: "시작하는 중",
  running: "검사 중",
  paused: "중단점에서 멈춤",
  finished: "검사 완료",
  failed: "검사 실패",
};

/** Where the run is, while it is anywhere. */
function Progress({ phase, live }: { phase: RunPhase; live: RunLive }) {
  const busy = phase === "running" || phase === "starting";
  // The node names as the graph and the stream spell them. Deduplicated,
  // because four verifiers in flight is one activity.
  const doing = [...new Set(live.running)].join(", ");

  return (
    <div className="flex shrink-0 items-center gap-1.5 border-b border-line px-2.5 py-1.5">
      {busy && <Loader2 className="size-3 shrink-0 animate-spin text-accent-ink" />}
      <span className={cn("shrink-0 text-2xs font-medium", busy ? "text-accent-ink" : "text-warn")}>
        {PHASE_LABEL[phase]}
      </span>
      {doing && <span className="min-w-0 truncate font-mono text-2xs text-ink-faint">{doing}</span>}
    </div>
  );
}
