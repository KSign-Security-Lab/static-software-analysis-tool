"use client";

import { CirclePause, CircleStop, Ellipsis, Loader2, Play, Workflow } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import StructureOverlay from "@/features/trace/StructureOverlay";
import { countOf, useRunControls } from "@/lib/run/controls";
import { phaseFor, type RunLive, type RunPhase } from "@/lib/run/reduce";
import { useFindings, useRun, useStartRun } from "@/lib/run/queries";
import { useFilter, useOpenedByRun, useSelection, useStructureOpen } from "@/lib/run/selection";
import { useRunStream } from "@/lib/run/stream";
import { useGraphShape, useResume, useSpans } from "@/lib/run/trace-queries";
import { useRunState } from "@/lib/run/use-run-id";
import { cn } from "@/lib/utils";
import RunHistory from "./RunHistory";
import WhoAmI from "./WhoAmI";
import RunSummary, { Coverage, coverageOf, duration, n } from "./RunSummary";

/**
 * Where the run is, what it has covered, and the one button that drives it.
 *
 * The single owner of run state on this surface. It used to be spread over
 * nine components: the phase was read by all of them, coverage was drawn in six
 * -- the explorer, the 문제 header, RunSummary's row *and* its meter, RunPane's
 * tally *and* its status strip -- and 검사 실행 existed twice, in the editor and
 * on the graph, each with its own `useStartRun`. Two buttons for one action is
 * a bug waiting for the two to disagree about whether a run is in flight.
 *
 * A strip across the top rather than a panel header, because none of this is a
 * property of any one pane: the coverage is the run's, not the file list's, and
 * the answer to "how far along is it" should not depend on which pane you
 * happen to be reading.
 *
 * The detail sits behind the numbers rather than beside them. 판단 흐름 and the
 * cost breakdown are what you ask *after* the headline, and they used to be a
 * fold in the 문제 pane where they competed with the findings for the same
 * column.
 */
export default function RunBar() {
  const { runId, restored, setRunId } = useRunState();
  const { live, phase: streamed, ensureAttached } = useRunStream();
  const { breakpoints, toggleBreakpoint, dirty, saving, saveAll } = useRunControls();
  const [, setFilter] = useFilter();
  const [, setOpenedByRun] = useOpenedByRun();
  const start = useStartRun(runId, ensureAttached);
  const { select, clear } = useSelection();
  const [, setStructure] = useStructureOpen();

  const findings = useFindings(runId);
  const spans = useSpans(runId);
  const run = useRun(runId);
  const shape = useGraphShape();

  const resume = useResume(runId, ensureAttached);

  // The record fills in for the stream on a run this tab never watched -- open
  // one from `?run=` and the stream has heard nothing, which is 검사 전 over a
  // finished report. See `phaseFor`.
  const phase = phaseFor(streamed, run.data?.status);
  const running = phase === "running" || phase === "starting";
  const paused = phase === "paused";

  /**
   * Save every changed file, start, then show it running.
   *
   * Here, in the component that owns the button, rather than on
   * `RunControlsProvider` -- which wraps the whole workbench, so reaching the
   * stream from it made every SSE event re-render the explorer, Monaco and the
   * dock. This component already reads the stream for its own phase label, so
   * nothing extra is subscribed.
   *
   * The overlay offers the same button and gets this as a prop. Two triggers for
   * one action is fine; two actions wearing one label is a bug waiting for the
   * two to disagree about whether a run is in flight, which is what the graph
   * pane's own second copy of `useStartRun` used to be.
   *
   * `saveAll`, not "save the open one". An inspection reads the whole run, so a
   * file edited and navigated away from was being scanned in its old state --
   * the report described code the reader had already changed, and nothing said
   * so. The button claims to inspect this code; this is what makes that true.
   *
   * An inspection takes minutes and the code has nothing to say for the first of
   * them, so the list widens from 문제 to 전체 on success -- a run in flight is
   * only legible as it moves, and 문제 is empty until the first unit finishes. On
   * success rather than on click, so a start that is refused leaves you where you
   * were, and flagged as ours so the list can say why it widened.
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

  const stats = findings.data?.stats;
  const { total, cached, inspected, done } = coverageOf(stats, live);
  const cost = spans.data?.summary;
  const files = run.data?.file_count ?? 0;

  return (
    <div className="shrink-0 bg-surface">
      {/*
        The strip begins where the workspace begins.

        It used to start at the window's left edge, which put 검사 전 and the
        coverage meter -- facts about one run, on one surface -- in the column
        the navigation rail occupies, and cut the rail in half on its way past.
        The title bar above solved this long ago with a cell exactly as wide as
        the rail; this is the same cell, carrying the rail's own right border and
        no bottom border of its own, so the rail reads straight through from the
        title bar to the floor.
      */}
      <div className="flex">
        <span className="h-9 w-16 shrink-0 border-r border-line" aria-hidden />

        <div className="flex h-9 min-w-0 flex-1 items-center gap-2 border-b border-line px-3">
          {/* Which run this is, first. See the note in RunHistory: `?run=` is
              what the whole surface hangs off and nothing on screen named it. */}
          <RunHistory />

          <span className="h-4 w-px shrink-0 bg-line" />

          <Phase phase={phase} live={live} />

        {/* One popover over the whole numeric group: these are all answers to
            "how much was looked at", and three separate triggers on a strip
            this dense would be three things to discover. */}
        {(total > 0 || inspected > 0 || cost) && (
          <Popover>
            <PopoverTrigger asChild>
              <button
                type="button"
                className="flex min-w-0 items-center gap-2.5 rounded-sm px-1.5 py-1 text-2xs text-ink-faint hover:bg-surface-2 hover:text-ink-muted"
              >
                {total > 0 && (
                  <span className="flex shrink-0 items-center gap-1.5">
                    <span>
                      단위 {n(done)}/{n(total)}
                    </span>
                    <Coverage total={total} inspected={inspected} cached={cached} className="w-16" />
                  </span>
                )}
                {cost && cost.tokens > 0 && <span className="shrink-0 font-mono">{n(cost.tokens)} tok</span>}
                {cost && cost.total_ms > 0 && <span className="shrink-0">{duration(cost.total_ms)}</span>}
              </button>
            </PopoverTrigger>
            <PopoverContent align="start" className="w-96 p-0">
              <RunSummary
                stats={stats}
                spans={cost}
                run={run.data}
                live={live}
                phase={phase}
                findings={findings.data?.findings?.length ?? 0}
              />
            </PopoverContent>
          </Popover>
        )}

        <div className="ml-auto flex shrink-0 items-center gap-1">
          {/* The drawing, at a size it can be read at. A button rather than a
              pane, because no pane on a four-pane workbench was big enough --
              the one it had fitted a sixteen-node pipeline at scale(0.3). */}
          <Button size="xs" variant="ghost" className="text-ink-muted" onClick={() => void setStructure(true)}>
            <Workflow />
            에이전트 구조
          </Button>

          {(running || paused) && (
            <Button size="xs" variant="ghost" onClick={() => resume.mutate({ action: "abort" })}>
              <CircleStop />
              중단
            </Button>
          )}

          {/* Stopped at a breakpoint is a thing you can look at, so it is
              selectable -- which is how the checkpoint panel is reached now that
              it is not a tab sitting dead most of the time. */}
          {paused && live.checkpointId && (
            <Button
              size="xs"
              variant="ghost"
              className="text-warn"
              onClick={() => select({ kind: "state", id: live.checkpointId! })}
            >
              멈춘 지점 보기
            </Button>
          )}

          {/*
            Settings, behind one trigger.

            중단점 and the owner name were two of six controls in this corner,
            all the same size and weight as the one that starts a run costing
            minutes and money -- so nothing in the group looked more important
            than anything else. Neither is an action: one configures the next
            run, the other filters a list. They are the two things that belong
            behind a ⋯.
          */}
          <Popover>
            <PopoverTrigger asChild>
              <Button size="icon-xs" variant="ghost" aria-label="검사 설정">
                <Ellipsis className="text-ink-muted" />
                {countOf(breakpoints) > 0 && (
                  <span className="absolute top-0.5 right-0.5 size-1.5 rounded-full bg-alt" aria-hidden />
                )}
              </Button>
            </PopoverTrigger>
            <PopoverContent align="end" className="w-72 p-0">
              {/* Whose runs those are. Not a login -- see `lib/run/whoami`. */}
              <div className="flex items-center gap-2 border-b border-line px-3 py-2">
                <span className="text-2xs text-ink-faint">이름</span>
                <WhoAmI />
              </div>

              {/* Not before there is a run to stop. On an empty workbench it
                  offered to set a breakpoint in an inspection that cannot be
                  started. */}
              {runId && (
                <>
                  <div className="flex items-baseline gap-2 border-b border-line px-3 py-2">
                    <span className="text-2xs text-ink-strong">
                      중단점{countOf(breakpoints) > 0 ? ` ${countOf(breakpoints)}` : ""}
                    </span>
                    <span className="min-w-0 flex-1 text-2xs text-ink-faint">
                      {running ? "실행 중에는 바꿀 수 없습니다" : "노드 앞/뒤에서 멈춥니다"}
                    </span>
                  </div>
                  <ScrollArea className="h-64">
                    <ul className={cn("p-1", running && "pointer-events-none opacity-50")}>
                      {(shape.data?.steppable ?? []).map((name) => (
                        <li key={name} className="flex items-center gap-2 rounded-sm px-2 py-1 hover:bg-surface-2">
                          <span className="flex-1 truncate font-mono text-2xs">{name}</span>
                          {(["before", "after"] as const).map((when) => (
                            <span key={when} className="flex items-center gap-1">
                              <Checkbox
                                id={`bp-${when}-${name}`}
                                checked={breakpoints[when].includes(name)}
                                onCheckedChange={() => toggleBreakpoint(name, when)}
                              />
                              <Label htmlFor={`bp-${when}-${name}`} className="text-2xs text-ink-faint">
                                {when === "before" ? "앞" : "뒤"}
                              </Label>
                            </span>
                          ))}
                        </li>
                      ))}
                    </ul>
                  </ScrollArea>
                </>
              )}
            </PopoverContent>
          </Popover>

          {/*
            The one filled button on the surface, and the largest.

            It was `size="xs"` in a row of five other `xs` ghosts at the far
            right corner of the window -- 81x28, about 1,500px from the file
            tree it acts on, indistinguishable from the controls beside it. This
            is the gesture the whole screen exists for and it costs minutes and
            money; it should not look like a toolbar affordance.

            `sm` is h-8 inside the h-9 strip, so it is visibly the biggest thing
            here without the strip having to grow.
          */}
          {paused ? (
            <Button size="sm" onClick={() => resume.mutate({ breakpoints })} disabled={resume.isPending}>
              <Play />
              이어서
            </Button>
          ) : (
            <Button size="sm" onClick={() => void inspect()} disabled={!runId || running || saving || start.isPending}>
              <Play />
              {/* Named, because it is a write to the reader's files and it can
                  take a moment on a tree. `n개 저장 중…` rather than a spinner:
                  saving three files you had forgotten were open is exactly the
                  moment to say how many.

                  And named for its target when it is idle: a button that starts
                  a scan should say what it is about to scan. */}
              {saving
                ? `${dirty.length}개 저장 중…`
                : running
                  ? "검사 중…"
                  : dirty.length > 0
                    ? `저장하고 검사 실행`
                    : files > 0
                      ? `검사 실행 · ${files}개 파일`
                      : "검사 실행"}
            </Button>
          )}
        </div>
        </div>
      </div>

      {/* The one thing the deleted chip strip said that nothing else did: this
          run was reopened from the tab's memory rather than asked for, so a fresh
          tab could show a scan the reader did not recognise. A sentence, beside
          the way out of it -- not a chip with an ×, which is what nobody could
          read. */}
      {/* Everything below the strip is inset by the rail's width too, or the
          rail is continuous for 36px and then cut in half by an alert. */}
      {(restored || live.refusal || run.data?.error || (!live.attached && live.active)) && (
        <div className="flex">
          <span className="w-16 shrink-0 border-r border-line" aria-hidden />
          <div className="min-w-0 flex-1 border-b border-line">
            {restored && (
              <p className="flex items-center gap-2 px-3 py-1 text-2xs text-ink-faint">
                지난 검사를 이어서 보고 있습니다
                <Button
                  size="xs"
                  variant="ghost"
                  className="h-5 px-1.5 text-2xs text-accent-ink"
                  onClick={() => {
                    setRunId(null);
                    clear();
                  }}
                >
                  새 검사
                </Button>
              </p>
            )}

            <Alerts live={live} error={run.data?.error} />
          </div>
        </div>
      )}

      {/* Rendered here, not beside this in the route slot. It portals to the
          body so where it is mounted is invisible, and being a child of the
          thing that opens it means the two cannot get out of step -- which they
          did, via a context whose hook threw when only one of the two modules
          had reloaded. */}
      <StructureOverlay inspect={inspect} starting={start.isPending} />
    </div>
  );
}

/**
 * The three things that are wrong, when any of them is.
 *
 * Rows under the strip rather than more things crammed into it: each is an
 * exception, none is on during an ordinary run, and a strip that reserved room
 * for all three would be mostly empty space most of the time.
 */
export function Alerts({ live, error }: { live: RunLive; error?: string }) {
  return (
    <>
      {!live.attached && live.active && <p className="px-3 py-1 text-2xs text-warn">연결 끊김 · 다시 연결 중</p>}
      {live.refusal && (
        <p className="flex items-start gap-1.5 bg-warn-wash px-3 py-1 text-2xs text-ink">
          <CirclePause className="mt-px size-3 shrink-0 text-warn" />
          {live.refusal}
        </p>
      )}
      {error && <p className="px-3 py-1 text-2xs text-danger">{error}</p>}
    </>
  );
}

const PHASE_LABEL: Record<RunPhase, string | null> = {
  idle: null,
  starting: "시작하는 중",
  running: "검사 중",
  paused: "중단점에서 멈춤",
  finished: "검사 완료",
  failed: "검사 실패",
};

const PHASE_TONE: Record<RunPhase, string> = {
  idle: "",
  starting: "text-ink-muted",
  running: "text-accent-ink",
  paused: "text-warn",
  finished: "text-ok",
  failed: "text-danger",
};

/** Where the run is, and what it is doing there. */
export function Phase({ phase, live }: { phase: RunPhase; live: RunLive }) {
  const label = PHASE_LABEL[phase];
  if (!label) return <span className="text-xs text-ink-faint">검사 전</span>;

  const busy = phase === "running" || phase === "starting";
  // The node names as the graph and the stream spell them. Deduplicated,
  // because four verifiers in flight is one activity.
  const doing = [...new Set(live.running)].join(", ");

  return (
    <span className="flex min-w-0 shrink-0 items-center gap-1.5 text-xs">
      {busy && <Loader2 className="size-3 shrink-0 animate-spin text-accent-ink" />}
      <span className={cn("shrink-0 font-medium", PHASE_TONE[phase])}>{label}</span>
      {busy && doing && (
        <Tooltip>
          <TooltipTrigger asChild>
            <span className="min-w-0 truncate font-mono text-2xs text-ink-faint">{doing}</span>
          </TooltipTrigger>
          <TooltipContent>{doing}</TooltipContent>
        </Tooltip>
      )}
    </span>
  );
}
