"use client";

import { CirclePause, CircleStop, Play, Settings2, X } from "lucide-react";
import { useState } from "react";

import StepGraph from "@/components/graph/StepGraph.lazy";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { ScrollArea } from "@/components/ui/scroll-area";
import { PanelShell } from "@/components/workbench/PanelShell";
import { NO_BREAKPOINTS, type Breakpoints } from "@/lib/api/control";
import { useCommands } from "@/lib/commands/provider";
import { useStartRun } from "@/lib/run/queries";
import { useRunStream } from "@/lib/run/stream";
import { useGraphShape, useResume, useSpans } from "@/lib/run/trace-queries";
import { useRunId } from "@/lib/run/use-run-id";
import { useScopedNode } from "./state";

/**
 * The agent's structure, with the run painted on, and the controls that drive it.
 *
 * A centre tab of 검사 rather than a route of its own: this and the editor are
 * two views of one run, over one dock.
 *
 * Breakpoints are set on the node itself rather than in a list elsewhere, and
 * are locked once a run is going: they are compiled in when the graph is built,
 * so changing one mid-run would be a lie.
 */
export default function GraphPane() {
  const [runId] = useRunId();
  const [node, setNode] = useScopedNode();
  const { live, phase, ensureAttached } = useRunStream();

  const shape = useGraphShape();
  const spans = useSpans(runId);
  const start = useStartRun(runId, ensureAttached);
  const resume = useResume(runId, ensureAttached);

  const [breakpoints, setBreakpoints] = useState<Breakpoints>(NO_BREAKPOINTS);
  const running = phase === "running" || phase === "starting";
  const paused = phase === "paused";
  const count = breakpoints.before.length + breakpoints.after.length;

  const toggle = (name: string, when: "before" | "after") =>
    setBreakpoints((current) => {
      const list = current[when];
      return { ...current, [when]: list.includes(name) ? list.filter((n) => n !== name) : [...list, name] };
    });

  useCommands(
    () => [
      {
        id: "run.resume",
        title: "이어서 실행",
        group: "실행",
        icon: Play,
        when: () => paused,
        run: () => resume.mutate({ breakpoints }),
      },
      {
        id: "run.abort",
        title: "실행 중단",
        group: "실행",
        icon: CircleStop,
        when: () => running || paused,
        run: () => resume.mutate({ action: "abort" }),
      },
    ],
    [paused, running, breakpoints],
  );

  return (
    <PanelShell
      title="에이전트 구조"
      note={node ? undefined : "노드를 누르면 그 노드의 호출만 남습니다"}
      actions={
        <>
          {node && (
            <Button size="xs" variant="ghost" onClick={() => void setNode(null)}>
              {node} 만 보는 중
              <X />
            </Button>
          )}

          <Popover>
            <PopoverTrigger asChild>
              <Button size="xs" variant="outline" disabled={running}>
                <Settings2 />
                중단점{count > 0 ? ` ${count}` : ""}
              </Button>
            </PopoverTrigger>
            <PopoverContent align="end" className="w-64 p-0">
              <div className="border-b border-line px-3 py-2 text-2xs text-ink-faint">
                노드 앞/뒤에서 멈춥니다. 실행 중에는 바꿀 수 없습니다.
              </div>
              <ScrollArea className="h-64">
                <ul className="p-1">
                  {(shape.data?.steppable ?? []).map((name) => (
                    <li key={name} className="flex items-center gap-2 rounded-sm px-2 py-1 hover:bg-surface-2">
                      <span className="flex-1 truncate font-mono text-2xs">{name}</span>
                      {(["before", "after"] as const).map((when) => (
                        <span key={when} className="flex items-center gap-1">
                          <Checkbox
                            id={`bp-${when}-${name}`}
                            checked={breakpoints[when].includes(name)}
                            onCheckedChange={() => toggle(name, when)}
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
            </PopoverContent>
          </Popover>

          {paused ? (
            <Button size="xs" onClick={() => resume.mutate({ breakpoints })} disabled={resume.isPending}>
              <Play />
              이어서
            </Button>
          ) : (
            <Button size="xs" onClick={() => start.mutate({ breakpoints })} disabled={!runId || running}>
              <Play />
              {running ? "검사 중…" : "검사 실행"}
            </Button>
          )}

          {(running || paused) && (
            <Button size="xs" variant="ghost" onClick={() => resume.mutate({ action: "abort" })}>
              <CircleStop />
              중단
            </Button>
          )}
        </>
      }
      bodyClassName="overflow-hidden"
    >
      {live.refusal && (
        <div className="flex items-start gap-2 border-b border-warn/40 bg-warn-wash px-2.5 py-1.5 text-2xs text-ink">
          <CirclePause className="mt-0.5 size-3.5 shrink-0 text-warn" />
          <span>{live.refusal}</span>
        </div>
      )}
      {shape.data ? (
        <StepGraph
          shape={shape.data}
          spans={spans.data?.spans ?? []}
          running={live.running}
          queued={live.queued}
          breakpoints={breakpoints}
          selected={node}
          onSelect={(next) => void setNode(next)}
          onInterrupt={toggle}
          direction="LR"
        />
      ) : (
        <p className="p-4 text-xs text-ink-faint">에이전트 구조를 불러오는 중…</p>
      )}
    </PanelShell>
  );
}
