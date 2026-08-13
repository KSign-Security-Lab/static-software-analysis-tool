"use client";

import { Network, Play } from "lucide-react";
import { useMemo } from "react";

import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useAgentSheet, useScopedNode } from "@/features/trace/state";
import { useRunStream } from "@/lib/run/stream";
import { useGraphShape, useResume } from "@/lib/run/trace-queries";
import { useRunId } from "@/lib/run/use-run-id";
import { STAGES, stageCalls, stageStates } from "@/lib/trace/stages";
import { cn } from "@/lib/utils";

/**
 * The run, across the top of everything.
 *
 * This is the piece that makes one screen out of four panels. Every panel is
 * about some part of a run -- the code it read, the problems it found, the calls
 * it made -- and until now nothing said where the run *was* except a spinner in
 * a corner and a node lighting up on a canvas you had to go and look at.
 *
 * Seven stages, not fourteen nodes: `skip` and `locate` are real and belong in
 * the drawing, and neither is something anybody watches for. See `stages.ts`.
 *
 * Before a run it is the shape of what will happen, which is the answer to "what
 * does this thing actually do" for somebody who has just arrived. During, it is
 * where the run is. After, it is how many calls each stage made. Clicking a
 * stage opens the canvas on it, which is the whole of what the second workspace
 * was for.
 */
export default function PipelineStrip() {
  const [runId] = useRunId();
  const shape = useGraphShape();
  const { live, phase, ensureAttached } = useRunStream();
  const resume = useResume(runId, ensureAttached);
  const [, setSheet] = useAgentSheet();
  const [, setNode] = useScopedNode();

  const calls = useMemo(() => stageCalls(shape.data?.node_notes ?? []), [shape.data]);
  const states = useMemo(() => stageStates(live.running, phase, calls), [live.running, phase, calls]);

  const busy = phase === "running" || phase === "starting";
  const chunk = live.chunk;
  const done = chunk && chunk.total > 0 ? chunk.total - chunk.remaining : null;

  const open = (stage: string) => {
    // The canvas opens on the stage you asked about, which is the only reason
    // anybody clicks one of these.
    const first = STAGES.find((each) => each.id === stage)?.nodes[0];
    if (first) void setNode(first);
    void setSheet(true);
  };

  return (
    <div className="flex h-10 shrink-0 items-center gap-3 border-b border-line bg-surface px-3">
      <ol className="flex min-w-0 flex-1 items-center gap-1 overflow-x-auto">
        {STAGES.map((stage, at) => (
          <li key={stage.id} className="flex shrink-0 items-center gap-1">
            {at > 0 && <span className="h-px w-3 bg-line-2" aria-hidden />}
            <Tooltip>
              <TooltipTrigger asChild>
                <button
                  type="button"
                  onClick={() => open(stage.id)}
                  className={cn(
                    "flex items-center gap-1.5 rounded-sm px-1.5 py-1 text-2xs transition-colors hover:bg-surface-2",
                    states[stage.id] === "running" && "text-accent-ink",
                    states[stage.id] === "done" && "text-ink-muted",
                    states[stage.id] === "waiting" && "text-ink-faint",
                  )}
                >
                  <span
                    aria-hidden
                    className={cn(
                      "size-1.5 shrink-0 rounded-full",
                      states[stage.id] === "running" && "animate-pulse bg-accent",
                      states[stage.id] === "done" && "bg-ok",
                      states[stage.id] === "waiting" && "bg-line-3",
                    )}
                  />
                  {stage.label}
                  {calls[stage.id] > 0 && (
                    <span className="font-mono text-ink-faint">{calls[stage.id]}</span>
                  )}
                </button>
              </TooltipTrigger>
              <TooltipContent>{stage.hint}</TooltipContent>
            </Tooltip>
          </li>
        ))}
      </ol>

      {busy && done !== null && chunk && (
        <span className="shrink-0 font-mono text-2xs text-ink-faint">
          {done}/{chunk.total}
        </span>
      )}
      {phase === "paused" && <span className="shrink-0 text-2xs text-warn">중단점에서 멈춤</span>}
      {live.refusal && <span className="min-w-0 truncate text-2xs text-warn">{live.refusal}</span>}

      <div className="flex shrink-0 items-center gap-1">
        {/* Resuming needs nothing but the run, so it lives here. 검사 실행 does
            not: it saves the editor's buffer first, and a second button that
            could not do that would be a second button that sometimes inspects
            code the server has never seen. */}
        {phase === "paused" && (
          <Button size="xs" disabled={resume.isPending} onClick={() => resume.mutate({})}>
            <Play />
            이어서
          </Button>
        )}
        <Tooltip>
          <TooltipTrigger asChild>
            <Button size="icon-xs" variant="ghost" onClick={() => void setSheet(true)} aria-label="에이전트 구조">
              <Network className="text-ink-faint" />
            </Button>
          </TooltipTrigger>
          <TooltipContent>에이전트 구조와 중단점</TooltipContent>
        </Tooltip>
      </div>
    </div>
  );
}
