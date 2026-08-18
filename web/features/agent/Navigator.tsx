"use client";

import { Loader2 } from "lucide-react";
import { parseAsStringLiteral, useQueryState } from "nuqs";

import ExplorerPane from "@/features/agent/ExplorerPane";
import RunHistory from "@/features/agent/RunHistory";
import Problems from "@/features/agent/nav/Problems";
import Units from "@/features/agent/nav/Units";
import { useFindings, useRun } from "@/lib/run/queries";
import { phaseFor, type RunLive, type RunPhase } from "@/lib/run/reduce";
import { useRunStream } from "@/lib/run/stream";
import { useRunId } from "@/lib/run/use-run-id";
import { cn } from "@/lib/utils";

/**
 * The left column: which run, and what is in it.
 *
 * The run's name is here because this column lists that run's files and nothing
 * else on screen said which run they belonged to -- a reopened tab could not be
 * told from a fresh one except by the file in the editor.
 *
 * The progress line is here for the same reason and appears only while a run is
 * live. It is not a status bar: a finished run says so with its cost in the
 * right column, and an idle one says nothing at all rather than reserving a row
 * to say it.
 *
 * The buttons that act on the run are not here. They are in the centre's tab
 * strip -- see `RunControls`.
 */
const MODES = ["problems", "units", "files"] as const;

export default function Navigator() {
  const [runId] = useRunId();
  const { live, phase: streamed } = useRunStream();
  const run = useRun(runId);
  const findings = useFindings(runId);

  const phase = phaseFor(streamed, run.data?.status);
  const live_ = phase === "running" || phase === "starting" || phase === "paused";
  const count = findings.data?.findings?.length ?? 0;
  const files = run.data?.file_count ?? 0;
  const units = findings.data?.stats?.chunks_total ?? 0;

  /**
   * Which list, and it follows the run rather than sitting where it was left.
   *
   * 파일 before a run, because there is nothing to find yet and putting code in
   * is the only move. 문제 once one has finished, because that is the answer you
   * came back for. Picking a mode by hand pins it -- the param stops being
   * absent, and the default stops applying.
   */
  const [pinned, setMode] = useQueryState("nav", parseAsStringLiteral(MODES).withOptions({ history: "replace" }));
  const mode = pinned ?? (count > 0 ? "problems" : "files");

  return (
    <section className="flex h-full min-h-0 min-w-0 flex-col bg-surface">
      <header className="flex h-9 shrink-0 items-center border-b border-line px-1.5">
        <RunHistory />
      </header>

      {live_ && <Progress phase={phase} live={live} />}

      {/*
        One list, two subjects, switched.

        The findings were a shelf along the bottom of the window and the files
        were this column, so "what did it find" and "what did it read" were two
        places with no relationship on screen -- and the shelf cost the editor a
        third of its height to hold a list two rows long. They are the same
        column now, because you are never asking both at once.
      */}
      <div className="flex h-8 shrink-0 items-center gap-0.5 border-b border-line px-1.5">
        <Mode active={mode === "problems"} onClick={() => void setMode("problems")}>
          문제
          {count > 0 && <span className="ml-1 text-ink-faint">{count}</span>}
        </Mode>
        <Mode active={mode === "units"} onClick={() => void setMode("units")}>
          단위
          {units > 0 && <span className="ml-1 text-ink-faint">{units}</span>}
        </Mode>
        <Mode active={mode === "files"} onClick={() => void setMode("files")}>
          파일
          {files > 0 && <span className="ml-1 text-ink-faint">{files}</span>}
        </Mode>
      </div>

      <div className={cn("min-h-0 min-w-0 flex-1", mode !== "problems" && "hidden")}>
        <div className="h-full overflow-auto">
          <Problems />
        </div>
      </div>
      <div className={cn("min-h-0 min-w-0 flex-1", mode !== "units" && "hidden")}>
        <div className="h-full overflow-auto">
          <Units />
        </div>
      </div>
      <div className={cn("min-h-0 min-w-0 flex-1", mode !== "files" && "hidden")}>
        <ExplorerPane />
      </div>
    </section>
  );
}

function Mode({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={active}
      onClick={onClick}
      className={cn(
        "rounded-md px-2 py-0.5 text-xs transition-colors",
        active ? "bg-surface-2 text-ink-strong" : "text-ink-muted hover:bg-surface-2 hover:text-ink",
      )}
    >
      {children}
    </button>
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
