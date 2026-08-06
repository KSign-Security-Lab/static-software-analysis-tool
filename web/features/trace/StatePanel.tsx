"use client";

import { GitFork, Info, Pencil, RefreshCw } from "lucide-react";
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
 * A patch as the fork will send it: the text, and what it parses to.
 *
 * Parsed on every keystroke rather than on submit, because the button is
 * disabled on the result -- a fork that fails to parse should never be
 * pressable, and finding that out from a toast after the request is a worse
 * way to learn it.
 */
export function parsePatch(text: string): { values?: Record<string, unknown>; error?: string } {
  try {
    const parsed: unknown = JSON.parse(text);
    if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) {
      return { error: "객체여야 합니다 — { \"키\": 값 }" };
    }
    return { values: parsed as Record<string, unknown> };
  } catch (err) {
    return { error: err instanceof Error ? err.message : "JSON을 읽을 수 없습니다" };
  }
}

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
  onFork: (checkpointId: string, values: Record<string, unknown>) => void;
  onRerun: (checkpointId: string) => void;
}) {
  const lanes = useMemo(() => lanesOf(checkpoints), [checkpoints]);
  const parents = useMemo(() => byId(checkpoints), [checkpoints]);
  const [open, setOpen] = useState<string | null>(null);
  // Keyed by the checkpoint it was seeded from, so selecting another step
  // reseeds rather than carrying one step's patch onto the next.
  const [draft, setDraft] = useState<{ id: string; text: string } | null>(null);
  // One draft at a time, so one parse -- the rows read the same result.
  const patch = useMemo(() => (draft ? parsePatch(draft.text) : {}), [draft]);

  if (checkpoints.length === 0) {
    return <p className="p-4 text-xs text-ink-faint">검사를 실행하면 단계마다 그 시점의 상태가 여기 쌓입니다. 중단점에 멈춰 있을 때는 여기서 상태를 고쳐 갈라 실행할 수 있습니다.</p>;
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
          <ToggleGroupItem value="summary" className="h-7 px-2 text-2xs">
            요약
          </ToggleGroupItem>
          <ToggleGroupItem value="full" className="h-7 px-2 text-2xs">
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
                  <div className="mt-1.5">
                    <div className="flex items-center gap-1.5">
                      <Button size="xs" variant="outline" disabled={busy || !interrupted} onClick={() => onRerun(id)}>
                        <RefreshCw />
                        여기서 다시
                      </Button>

                      {fanOut ? (
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <span>
                              <Button size="xs" variant="outline" disabled>
                                <Pencil />
                                고쳐서 갈라 실행
                              </Button>
                            </span>
                          </TooltipTrigger>
                          <TooltipContent className="max-w-64">
                            이 단계는 여러 갈래가 동시에 실행된 지점이라 상태를 쓸 곳이 하나로 정해지지 않습니다.
                            locate · reduce · plan 에서 편집하세요.
                          </TooltipContent>
                        </Tooltip>
                      ) : (
                        <Button
                          size="xs"
                          variant="outline"
                          disabled={busy || !interrupted}
                          onClick={() =>
                            setDraft(
                              draft?.id === id
                                ? null
                                : {
                                    id,
                                    // Seeded with what this step wrote, which is
                                    // the thing anyone stopping here came to
                                    // change. Only meaningful in 전체 상태: the
                                    // summary counts the bulky channels, and a
                                    // count cannot be written back as a list.
                                    text: JSON.stringify(
                                      Object.fromEntries(changed.map((key) => [key, point.values[key]])),
                                      null,
                                      2,
                                    ),
                                  },
                            )
                          }
                        >
                          <Pencil />
                          고쳐서 갈라 실행
                        </Button>
                      )}

                      {!interrupted && (
                        <span className="flex items-center gap-1 text-2xs text-ink-faint">
                          <Info className="size-3" />
                          중단점에 멈춰 있을 때만 가능합니다
                        </span>
                      )}
                    </div>

                    {draft?.id === id && (
                      <div className="mt-1.5">
                        {!full && (
                          <p className="mb-1 flex items-start gap-1 text-2xs text-warn">
                            <Info className="mt-px size-3 shrink-0" />
                            요약 보기에서는 긴 값이 개수로 줄어 있습니다. 위에서 전체 상태로 바꾼 뒤 편집하세요.
                          </p>
                        )}
                        <textarea
                          value={draft.text}
                          spellCheck={false}
                          rows={8}
                          aria-label="상태 편집"
                          onChange={(event) => setDraft({ id, text: event.target.value })}
                          className="w-full resize-y rounded-sm border border-line bg-field p-2 font-mono text-2xs text-ink outline-none focus-visible:border-accent"
                        />
                        <div className="mt-1 flex items-center gap-2">
                          <Button
                            size="xs"
                            disabled={busy || !interrupted || !patch.values}
                            onClick={() => patch.values && onFork(id, patch.values)}
                          >
                            <GitFork />
                            여기서 갈라 실행
                          </Button>
                          <Button size="xs" variant="ghost" onClick={() => setDraft(null)}>
                            취소
                          </Button>
                          <span className={cn("truncate text-2xs", patch.error ? "text-danger" : "text-ink-faint")}>
                            {patch.error ?? "적은 키만 덮어씁니다. 원래 갈래는 그대로 남습니다."}
                          </span>
                        </div>
                      </div>
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
