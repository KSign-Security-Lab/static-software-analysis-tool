"use client";

import { FolderGit2, FolderOpen, Plus, ScanSearch } from "lucide-react";

import RunPicker from "@/features/inspect/RunPicker";
import WhoAmI from "@/features/inspect/WhoAmI";
import { Button } from "@/components/ui/button";
import type { Origin } from "@/lib/api/types";
import { SEVERITY_DOT, SEVERITY_LABEL, type UiFinding } from "@/lib/model/finding";
import { bySeverity } from "@/lib/inspect/filter";
import { useRun } from "@/lib/run/queries";
import { useRunId } from "@/lib/run/use-run-id";

export default function RunBar({ findings }: { findings: UiFinding[] }) {
  const [runId, setRunId] = useRunId();
  const run = useRun(runId);
  const origin = run.data?.origin;
  const counts = bySeverity(findings);

  return (
    <header className="flex h-11 shrink-0 items-center gap-3 border-b border-line bg-surface px-3">
      <span className="flex min-w-0 items-center gap-2">
        <OriginMark origin={origin} />
        <span className="min-w-0 truncate text-sm font-medium text-ink-strong">
          {origin?.label ?? (runId ? "검사" : "검사할 코드를 올려 주세요")}
        </span>
        {origin?.commit && (
          <span className="shrink-0 font-mono text-2xs text-ink-faint">{origin.commit.slice(0, 7)}</span>
        )}
      </span>

      {counts.length > 0 && (
        <span className="flex shrink-0 items-center gap-2.5 border-l border-line pl-3">
          {counts.map(({ value, count }) => (
            <span key={value} className="flex items-center gap-1 text-2xs text-ink-muted">
              <span className={`size-1.5 rounded-full ${SEVERITY_DOT[value]}`} aria-hidden />
              <span className="sr-only">{SEVERITY_LABEL[value]} </span>
              {count}
            </span>
          ))}
        </span>
      )}

      <span className="ml-auto flex shrink-0 items-center gap-1">
        <RunPicker />
        <WhoAmI />
        {runId && (
          <Button size="sm" variant="ghost" onClick={() => setRunId(null)}>
            <Plus className="size-3.5" />
            새 검사
          </Button>
        )}
      </span>
    </header>
  );
}

function OriginMark({ origin }: { origin: Origin | undefined }) {
  const Icon = origin?.kind === "git" ? FolderGit2 : origin ? FolderOpen : ScanSearch;
  return <Icon className="size-4 shrink-0 text-ink-faint" aria-hidden />;
}
