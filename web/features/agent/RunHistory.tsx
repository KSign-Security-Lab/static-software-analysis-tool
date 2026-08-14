"use client";

import { History, Trash2 } from "lucide-react";
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
import { useDeleteRun, useRuns } from "@/lib/run/queries";
import { useOpenFile, useRevealLine, useSelection } from "@/lib/run/selection";
import { useRunState } from "@/lib/run/use-run-id";

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

  const all = runs.data ?? [];
  // Everything else is fair game; the run on screen is not, because deleting what
  // you are looking at is a different act and wants its own confirmation.
  const others = all.filter((each) => each.run_id !== runId);

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
          <Button size="xs" variant="ghost" className="text-ink-muted">
            <History />
            지난 검사
            {all.length > 0 && <span className="text-ink-faint">{all.length}</span>}
          </Button>
        </PopoverTrigger>
        <PopoverContent align="end" className="w-96 p-0">
          <div className="flex items-center gap-2 border-b border-line px-3 py-2">
            <p className="text-xs font-semibold text-ink-strong">지난 검사</p>
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
                    onOpen={() => openRun(each.run_id)}
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

/** `main.c 외 1 · 8/13 16:37 · 3건`, and whether it is the one on screen. */
function Entry({
  run,
  current,
  onOpen,
  onDelete,
}: {
  run: RunRecord;
  current: boolean;
  onOpen: () => void;
  onDelete: () => void;
}) {
  const name = run.files[0] ?? run.run_id;
  const more = run.file_count > 1 ? ` 외 ${run.file_count - 1}` : "";
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
          <span className="min-w-0 truncate font-mono text-2xs text-ink">
            {name}
            {more}
          </span>
          {current && <span className="shrink-0 text-2xs text-accent-ink">보는 중</span>}
        </span>
        <span className="flex items-baseline gap-1.5 text-2xs text-ink-faint">
          {when}
          {/* Never inspected reads differently from inspected and clean, and the
              list is where that distinction is cheapest to make. */}
          <span>{run.started ? `${run.findings ?? 0}건` : "검사 안 함"}</span>
        </span>
      </button>
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
