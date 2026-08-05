"use client";

import { GitFork, Info, RefreshCw } from "lucide-react";
import { useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { isFanOut } from "@/lib/api/control";
import type { Checkpoint } from "@/lib/api/types";
import { byId, changedKeys, lanesOf } from "@/lib/trace/lanes";
import { cn } from "@/lib/utils";

/**
 * The run's history, as lanes.
 *
 * A history is a straight line until somebody writes over an old step. That
 * write records the old step as its parent, so a second child of any step is a
 * second line -- which is what a fork is, and the only thing it can be drawn
 * from.
 */
export default function StatePanel({
  checkpoints,
  selected,
  full,
  busy,
  interrupted,
  onSelect,
  onFull,
  onFork,
  onRerun,
}: {
  checkpoints: Checkpoint[];
  selected: string | null;
  full: boolean;
  busy?: boolean;
  interrupted?: boolean;
  onSelect: (checkpointId: string | null) => void;
  onFull: (full: boolean) => void;
  onFork: (checkpointId: string) => void;
  onRerun: (checkpointId: string) => void;
}) {
  const lanes = useMemo(() => lanesOf(checkpoints), [checkpoints]);
  const parents = useMemo(() => byId(checkpoints), [checkpoints]);
  const [open, setOpen] = useState<string | null>(null);

  if (checkpoints.length === 0) {
    return <p className="p-4 text-xs text-ink-faint">아직 기록된 단계가 없습니다.</p>;
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex shrink-0 items-center gap-2 border-b border-line px-2.5 py-1.5">
        <ToggleGroup
          type="single"
          size="sm"
          variant="outline"
          value={full ? "full" : "summary"}
          onValueChange={(next) => next && onFull(next === "full")}
        >
          <ToggleGroupItem value="summary" className="h-6 px-2 text-2xs">
            요약
          </ToggleGroupItem>
          <ToggleGroupItem value="full" className="h-6 px-2 text-2xs">
            전체 상태
          </ToggleGroupItem>
        </ToggleGroup>
        <span className="ml-auto text-2xs text-ink-faint">{checkpoints.length}단계</span>
      </div>

      <ol className="min-h-0 flex-1 overflow-auto py-1">
        {checkpoints.map((point) => {
          const id = point.checkpoint_id;
          if (!id) return null;
          const lane = lanes.get(id) ?? 0;
          const parent = point.parent_checkpoint_id ? parents.get(point.parent_checkpoint_id) : undefined;
          const changed = changedKeys(point, parent);
          // The server refuses a state edit whose parent had more than one task
          // queued -- the triage fan-out, the four lenses, the verify pass --
          // because there is no single node to attribute the write to. That is
          // visible from here, so say so instead of letting the user type an
          // edit, press fork, get a 200, and watch nothing happen.
          const fanOut = isFanOut(parent?.next);

          return (
            <li key={id} className={cn("border-l-2", selected === id ? "border-l-accent" : "border-l-transparent")}>
              <div
                className={cn("px-2.5 py-1.5 transition-colors hover:bg-surface-2", selected === id && "bg-accent-wash")}
                style={{ paddingInlineStart: 10 + lane * 12 }}
              >
                <button type="button" onClick={() => onSelect(id)} className="flex w-full items-center gap-2 text-left">
                  <span className="font-mono text-2xs text-ink-faint">{point.step ?? "–"}</span>
                  <span className="truncate text-xs text-ink">{point.node ?? "(시작)"}</span>
                  {lane > 0 && (
                    <Badge variant="outline" className="shrink-0 px-1 py-0 text-2xs font-normal text-alt">
                      갈래 {lane}
                    </Badge>
                  )}
                  {point.next.length > 1 && (
                    <Badge variant="outline" className="shrink-0 px-1 py-0 text-2xs font-normal">
                      {point.next.length}갈래 동시
                    </Badge>
                  )}
                  <span className="ml-auto shrink-0 text-2xs text-ink-faint">{changed.length}개 변경</span>
                </button>

                {changed.length > 0 && (
                  <Collapsible open={open === id} onOpenChange={(o) => setOpen(o ? id : null)}>
                    <CollapsibleTrigger className="mt-0.5 font-mono text-2xs text-ink-faint hover:text-ink-muted">
                      {changed.slice(0, 4).join(", ")}
                      {changed.length > 4 ? ` +${changed.length - 4}` : ""}
                    </CollapsibleTrigger>
                    <CollapsibleContent>
                      <pre className="mt-1 max-h-48 overflow-auto rounded-sm bg-field p-2 font-mono text-2xs whitespace-pre-wrap text-ink-muted">
                        {JSON.stringify(
                          Object.fromEntries(changed.map((key) => [key, point.values[key]])),
                          null,
                          2,
                        )}
                      </pre>
                    </CollapsibleContent>
                  </Collapsible>
                )}

                {selected === id && (
                  <div className="mt-1.5 flex items-center gap-1.5">
                    <Button size="xs" variant="outline" disabled={busy || !interrupted} onClick={() => onRerun(id)}>
                      <RefreshCw />
                      여기서 다시
                    </Button>

                    {fanOut ? (
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <span>
                            <Button size="xs" variant="outline" disabled>
                              <GitFork />
                              갈라 실행
                            </Button>
                          </span>
                        </TooltipTrigger>
                        <TooltipContent className="max-w-64">
                          이 단계는 여러 갈래가 동시에 실행된 지점이라 상태를 쓸 곳이 하나로 정해지지 않습니다. locate ·
                          reduce · plan 에서 편집하세요.
                        </TooltipContent>
                      </Tooltip>
                    ) : (
                      <Button size="xs" variant="outline" disabled={busy || !interrupted} onClick={() => onFork(id)}>
                        <GitFork />
                        갈라 실행
                      </Button>
                    )}

                    {!interrupted && (
                      <span className="flex items-center gap-1 text-2xs text-ink-faint">
                        <Info className="size-3" />
                        중단점에 멈춰 있을 때만 가능합니다
                      </span>
                    )}
                  </div>
                )}
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
