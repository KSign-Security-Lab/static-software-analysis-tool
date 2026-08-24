"use client";

import { History, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { ago } from "@/lib/format";
import { useDeleteRun, useRuns } from "@/lib/run/queries";
import { useRunId } from "@/lib/run/use-run-id";
import { cn } from "@/lib/utils";

/**
 * 지난 검사.
 *
 * A scan costs minutes and tokens, so reopening one has to be possible -- and
 * the report is the whole of what it produced, so reopening is just setting
 * `?run=`. Everything else on this screen is derived from that.
 *
 * A popover rather than a pane. The previous version was a 321-line panel with
 * comparison, deletion and a run's whole statistics in it; what a reader actually
 * does here is pick one and occasionally delete one, and both fit in a list.
 *
 * The list is this owner's, by the `x-ssat-owner` header. Not a login -- see
 * `lib/run/whoami` -- just a way of not showing you a stranger's scans.
 */
export default function RunPicker() {
  const [runId, setRunId] = useRunId();
  const runs = useRuns();
  const remove = useDeleteRun();

  const rows = runs.data ?? [];

  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button size="sm" variant="ghost">
          <History className="size-3.5" />
          지난 검사
          {rows.length > 0 && <span className="font-mono text-2xs text-ink-faint">{rows.length}</span>}
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-96 p-0">
        {rows.length === 0 ? (
          <p className="px-3 py-4 text-xs text-ink-faint">
            {/* Three states, and the third used to be told as the second. A
                failed request is not an empty history, and saying "아직 검사한
                것이 없습니다" to somebody whose backend is down sends them
                looking for their scans instead of at their server. */}
            {runs.isPending
              ? "불러오는 중"
              : runs.error
                ? "목록을 가져오지 못했습니다. 백엔드에 연결됐는지 확인하세요."
                : "아직 검사한 것이 없습니다."}
          </p>
        ) : (
          <ul className="max-h-96 overflow-auto py-1">
            {rows.map((row) => {
              const current = row.run_id === runId;
              return (
                <li key={row.run_id} className="group/row flex items-center gap-1 pr-1">
                  <button
                    type="button"
                    onClick={() => setRunId(row.run_id)}
                    className={cn(
                      "min-w-0 flex-1 px-2.5 py-1.5 text-left transition-colors hover:bg-surface-2",
                      current && "bg-surface-2",
                    )}
                  >
                    <span className="flex items-baseline gap-1.5">
                      <span
                        className={cn("min-w-0 truncate text-xs", current ? "text-ink-strong" : "text-ink")}
                      >
                        {/* The origin label is what somebody recognises. The
                            file names are the fallback for runs made before
                            intake recorded one. */}
                        {row.origin?.label ?? row.files.join(", ") ?? row.run_id}
                      </span>
                      {typeof row.findings === "number" && row.findings > 0 && (
                        <span className="shrink-0 font-mono text-2xs text-ink-muted">{row.findings}건</span>
                      )}
                    </span>
                    <span className="mt-0.5 flex items-baseline gap-1.5 font-mono text-2xs text-ink-faint">
                      <span>{ago(row.updated_at)}</span>
                      <span>{row.file_count}개 파일</span>
                      {row.status !== "done" && <span className="text-warn">{STATUS[row.status] ?? row.status}</span>}
                    </span>
                  </button>
                  <Button
                    size="icon-xs"
                    variant="ghost"
                    aria-label="이 검사 지우기"
                    className="shrink-0 opacity-0 transition-opacity group-hover/row:opacity-100"
                    onClick={() => {
                      // Clear the selection first: the queries against it are
                      // disabled the moment the id goes, so nothing re-fetches
                      // from a server that has just deleted it.
                      if (current) setRunId(null);
                      remove.mutate(row.run_id);
                    }}
                  >
                    <Trash2 className="text-ink-faint" />
                  </Button>
                </li>
              );
            })}
          </ul>
        )}
      </PopoverContent>
    </Popover>
  );
}

/** Only the ones worth saying. `done` is the expected case and says nothing. */
const STATUS: Record<string, string> = {
  created: "준비 중",
  indexing: "읽는 중",
  indexed: "검사 전",
  inspecting: "검사 중",
  interrupted: "멈춤",
  cancelled: "중단됨",
  failed: "실패",
};
