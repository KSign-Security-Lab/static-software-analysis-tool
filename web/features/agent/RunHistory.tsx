"use client";

import { ChevronDown, GitCompareArrows, Trash2 } from "lucide-react";
import { useState } from "react";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { ScrollArea } from "@/components/ui/scroll-area";
import type { RunSummary as RunRecord } from "@/lib/api/types";
import { useDeleteRun, useDiff, useRuns } from "@/lib/run/queries";
import { useCompareAgainst, useOpenFile, useRevealLine, useSelection } from "@/lib/run/selection";
import { useRunState } from "@/lib/run/use-run-id";
import { ago } from "@/lib/format";
import { cn } from "@/lib/utils";

/**
 * The scans this server still has, and how to be rid of them.
 *
 * There was no way to see them and no way to clear them. The runs directory
 * accumulates one entry per scan and the only thing that ever listed them was the
 * 비교 dropdown -- a control for reading one run against another, which is not
 * where anybody looks for "what have I got, and delete it". The explorer's eraser
 * threw away the *current* run and nothing else, so history grew without bound
 * and without a UI.
 *
 * In the run bar because the bar owns which run this tab is on, and opening an old
 * one is exactly that: changing the run. Deleting is here for the same reason --
 * it is the same list.
 *
 * The trigger names the run it is on. `?run=` is the object this whole surface
 * is keyed to -- the report, the trace, the checkpoints and every finding hang
 * off it -- and until now no pixel on screen said which one it was. Somebody
 * reading a report had no way to tell it apart from the last one but the file
 * open in the editor, and a reopened tab said nothing at all. So the trigger is
 * the run's name and its state, on the left of the strip, first thing: what you
 * are looking at, before anything about what it found.
 *
 * The server deletes one run per request and there is no bulk endpoint, so
 * `전체 지우기` is a loop rather than a call. Sequential: these are directory
 * removals, and firing twenty at once at a local server buys nothing worth the
 * failure modes.
 */
export default function RunHistory() {
  const { runId, setRunId } = useRunState();
  const [, setPath] = useOpenFile();
  const [, setLine] = useRevealLine();
  const { clear } = useSelection();

  const runs = useRuns();
  const remove = useDeleteRun();
  const [open, setOpen] = useState(false);
  const [clearing, setClearing] = useState(false);
  const [busy, setBusy] = useState(false);

  /**
   * The run this one is being read against.
   *
   * Cleared when the run changes, during render rather than in an effect: a
   * comparison is an answer about one run, so a different run has to ask again.
   */
  const [against, setAgainst] = useCompareAgainst();
  const [asked, setAsked] = useState(runId);
  if (asked !== runId) {
    setAsked(runId);
    if (against) void setAgainst(null);
  }
  const diff = useDiff(runId, against);

  const all = runs.data ?? [];
  // Everything else is fair game; the run on screen is not, because deleting what
  // you are looking at is a different act and wants its own confirmation.
  const others = all.filter((each) => each.run_id !== runId);
  const current = all.find((each) => each.run_id === runId);

  const openRun = (id: string) => {
    setRunId(id);
    void setPath(null);
    void setLine(null);
    clear();
    setOpen(false);
  };

  const clearAll = async () => {
    setBusy(true);
    try {
      for (const each of others) await remove.mutateAsync(each.run_id);
    } finally {
      setBusy(false);
      setClearing(false);
    }
  };

  return (
    <>
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <Button size="xs" variant="ghost" className="min-w-0 max-w-72 text-ink-muted">
            <span className={cn("size-1.5 shrink-0 rounded-full", DOT[current?.status ?? "created"])} aria-hidden />
            <span className="min-w-0 truncate font-mono text-2xs text-ink">{current ? nameOf(current) : "검사 없음"}</span>
            {current && <span className="shrink-0 text-2xs text-ink-faint">{ago(current.updated_at)}</span>}
            {against && (
              <span className="shrink-0 rounded-sm bg-alt-wash px-1 text-2xs text-alt" title="다른 검사와 비교 중">
                비교
              </span>
            )}
            <ChevronDown className="shrink-0 text-ink-faint" />
          </Button>
        </PopoverTrigger>
        <PopoverContent align="start" className="w-96 p-0">
          <div className="flex items-center gap-2 border-b border-line px-3 py-2">
            {/* The count was on the trigger, which now has to name the run it is
                on instead -- a more useful thing for a permanently visible
                control to say than a number you only need once you have decided
                to go looking. It is still the first thing in the list it counts. */}
            <p className="text-xs font-semibold text-ink-strong">지난 검사 {all.length}</p>
            <p className="min-w-0 flex-1 truncate text-2xs text-ink-faint">이 컴퓨터에 남아 있는 것들입니다</p>
            {others.length > 0 && (
              <Button
                size="xs"
                variant="ghost"
                className="shrink-0 text-2xs text-danger"
                onClick={() => setClearing(true)}
              >
                전체 지우기
              </Button>
            )}
          </div>

          {/* What the comparison found, and the way out of it. Above the list
              because it is a fact about the run named at the top, not about any
              row below. */}
          {against && (
            <div className="flex items-center gap-2 border-b border-line bg-alt-wash/40 px-3 py-1.5">
              <span className="shrink-0 text-2xs text-alt">비교 중</span>
              {diff.data ? (
                <span className="flex min-w-0 flex-1 items-baseline gap-2 font-mono text-2xs">
                  <span className="text-accent-ink">새로 {diff.data.new?.length ?? 0}</span>
                  <span className="text-ok">해결됨 {diff.data.fixed?.length ?? 0}</span>
                  <span className="text-ink-faint">그대로 {diff.data.unchanged?.length ?? 0}</span>
                </span>
              ) : (
                <span className="min-w-0 flex-1 text-2xs text-ink-faint">비교하는 중…</span>
              )}
              <Button size="xs" variant="ghost" className="shrink-0 text-2xs" onClick={() => void setAgainst(null)}>
                그만
              </Button>
            </div>
          )}

          {all.length === 0 ? (
            <p className="px-3 py-3 text-2xs text-ink-faint">아직 검사한 기록이 없습니다.</p>
          ) : (
            <ScrollArea className="max-h-80">
              <ul className="p-1">
                {all.map((each) => (
                  <Entry
                    key={each.run_id}
                    run={each}
                    current={each.run_id === runId}
                    comparing={each.run_id === against}
                    onOpen={() => openRun(each.run_id)}
                    onCompare={
                      // Only against a run that was actually inspected: an
                      // uninspected one has no report, so every finding here
                      // would come back "new" and mean nothing.
                      each.run_id !== runId && each.started
                        ? () => void setAgainst(each.run_id === against ? null : each.run_id)
                        : undefined
                    }
                    onDelete={() => remove.mutate(each.run_id)}
                  />
                ))}
              </ul>
            </ScrollArea>
          )}
        </PopoverContent>
      </Popover>

      <AlertDialog open={clearing} onOpenChange={setClearing}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>지난 검사 {others.length}개를 지울까요?</AlertDialogTitle>
            <AlertDialogDescription>
              각 검사의 파일과 색인, 호출 기록과 보고서가 함께 지워집니다. 되돌릴 수 없습니다. 지금 보고 있는 검사는
              남습니다.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={busy}>그만두기</AlertDialogCancel>
            <AlertDialogAction
              disabled={busy}
              onClick={(event) => {
                // The dialog closes on action by default, and this one has to
                // stay up while a loop of deletes runs.
                event.preventDefault();
                void clearAll();
              }}
            >
              {busy ? "지우는 중…" : "지우기"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}

/**
 * What a run is called: its first file, and how many more.
 *
 * The id is a hex string nobody recognises and the server sends at most two
 * names, so this is as close to a name as a run has. Shared by the trigger and
 * the rows so the thing you picked is spelled the same way afterwards.
 */
export function nameOf(run: RunRecord): string {
  const first = run.files[0] ?? run.run_id;
  return run.file_count > 1 ? `${first} 외 ${run.file_count - 1}` : first;
}

/**
 * The run's state as one dot.
 *
 * The strip already says the phase in words, next to this. The dot is for the
 * rows in the list, where seven words of status per row would be a wall -- and
 * for the trigger, where it is the difference between "this finished" and "this
 * is still going" without reading anything.
 */
const DOT: Record<string, string> = {
  created: "bg-line-3",
  indexing: "bg-line-3",
  indexed: "bg-line-3",
  inspecting: "bg-accent animate-pulse",
  interrupted: "bg-warn",
  done: "bg-ok",
  failed: "bg-danger",
};

/** `main.c 외 1 · 8/13 16:37 · 3건`, and whether it is the one on screen. */
function Entry({
  run,
  current,
  comparing,
  onOpen,
  onCompare,
  onDelete,
}: {
  run: RunRecord;
  current: boolean;
  comparing: boolean;
  onOpen: () => void;
  /** Absent on the run you are on, and on one that was never inspected. */
  onCompare?: () => void;
  onDelete: () => void;
}) {
  const name = nameOf(run);
  const when = new Date(run.updated_at * 1000).toLocaleString("ko-KR", {
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });

  return (
    <li className="group flex items-center gap-1 rounded-sm hover:bg-surface-2">
      <button
        type="button"
        onClick={onOpen}
        disabled={current}
        className="flex min-w-0 flex-1 flex-col items-start gap-0.5 px-2 py-1.5 text-left disabled:cursor-default"
      >
        <span className="flex w-full min-w-0 items-baseline gap-1.5">
          <span className={cn("size-1.5 shrink-0 self-center rounded-full", DOT[run.status])} aria-hidden />
          <span className="min-w-0 truncate font-mono text-2xs text-ink">{name}</span>
          {current && <span className="shrink-0 text-2xs text-accent-ink">보는 중</span>}
        </span>
        <span className="flex items-baseline gap-1.5 text-2xs text-ink-faint">
          {when}
          {/* Never inspected reads differently from inspected and clean, and the
              list is where that distinction is cheapest to make. */}
          <span>{run.started ? `${run.findings ?? 0}건` : "검사 안 함"}</span>
        </span>
      </button>
      {onCompare && (
        <button
          type="button"
          aria-label={comparing ? `${name} 와 비교 그만두기` : `${name} 와 비교하기`}
          title={comparing ? "비교 그만두기" : "이 검사와 비교"}
          onClick={onCompare}
          className={cn(
            "shrink-0 rounded-xs p-1",
            comparing
              ? "bg-alt-wash text-alt"
              : "hidden text-ink-faint hover:bg-surface-3 hover:text-ink group-hover:block",
          )}
        >
          <GitCompareArrows className="size-3" />
        </button>
      )}
      {!current && (
        <button
          type="button"
          aria-label={`${name} 검사 지우기`}
          onClick={onDelete}
          className="mr-1 hidden shrink-0 rounded-xs p-1 text-ink-faint hover:bg-danger-wash hover:text-danger group-hover:block"
        >
          <Trash2 className="size-3" />
        </button>
      )}
    </li>
  );
}
