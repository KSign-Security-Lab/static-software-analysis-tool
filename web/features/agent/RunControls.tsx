"use client";

import { CircleStop, Play } from "lucide-react";

import { Button } from "@/components/ui/button";
import RunMenu from "@/features/agent/RunMenu";
import { useRunControls } from "@/lib/run/controls";
import { useRun, useStartRun } from "@/lib/run/queries";
import { phaseFor } from "@/lib/run/reduce";
import { useFilter, useOpenedByRun } from "@/lib/run/selection";
import { useRunStream } from "@/lib/run/stream";
import { useResume } from "@/lib/run/trace-queries";
import { useRunId } from "@/lib/run/use-run-id";

/**
 * The three controls that act on the run, at the end of the centre's tab strip.
 *
 * Not a bar. The tab strip has to exist for 코드 and 구조, and its right half is
 * empty -- so these cost no height at all, which is the whole reason the 36px
 * strip they used to live on is gone.
 *
 * One slot for the primary action, because you can never want two of them: it
 * starts a run, aborts the one going, or resumes the one stopped at a
 * breakpoint. `⋯` holds the two settings -- the owner name and the breakpoints
 * -- which are neither actions nor wanted often.
 *
 * A paused run used to offer 멈춘 지점 보기 here as well, opening a panel of
 * checkpoint lanes to fork and re-run from. That feature is gone; resuming is
 * the only thing anyone did with a pause.
 */
export default function RunControls() {
  const [runId] = useRunId();
  const { phase: streamed, ensureAttached } = useRunStream();
  const { breakpoints, dirty, saving, saveAll } = useRunControls();
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
   * `saveAll`, not "save the open one": an inspection reads the whole run, so a
   * file edited and navigated away from was being scanned in its old state --
   * the report described code the reader had already changed, and nothing said
   * so.
   *
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
    <span className="flex shrink-0 items-center gap-1">
      <RunMenu />

      {paused ? (
        <Button size="sm" onClick={() => resume.mutate({ breakpoints })} disabled={resume.isPending}>
          <Play />
          이어서
        </Button>
      ) : running ? (
        <Button size="sm" variant="outline" onClick={() => resume.mutate({ action: "abort" })}>
          <CircleStop />
          중단
        </Button>
      ) : (
        <Button size="sm" onClick={() => void inspect()} disabled={!runId || saving || start.isPending}>
          <Play />
          {saving ? `${dirty.length}개 저장 중…` : files > 0 ? `검사 실행 · ${files}개` : "검사 실행"}
        </Button>
      )}
    </span>
  );
}
