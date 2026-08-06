"use client";

import { Play, RotateCcw, Save } from "lucide-react";
import { useMemo, useState } from "react";

import DiffView from "@/components/editor/DiffView.lazy";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { PanelShell } from "@/components/workbench/PanelShell";
import type { PromptRow, TraceSpan } from "@/lib/api/types";
import { useReplay, useResetPrompt, useSavePrompt } from "@/lib/run/trace-queries";
import { seconds } from "@/lib/trace/tree";
import { Payload, promptOf, replyOf } from "./Payload";

const PRE = "max-h-72 overflow-auto rounded-sm bg-field p-2 font-mono text-2xs leading-relaxed whitespace-pre-wrap text-ink-muted";

/**
 * One recorded call, and the means to make it answer better.
 *
 * Replay writes nothing -- not the run, not the trace, not the report -- which
 * is the contract that makes it safe to press repeatedly. Saving the prompt is
 * the separate, deliberate act, and it applies to every later run.
 */
export default function SpanInspector({
  runId,
  span,
  prompts,
}: {
  runId: string | null;
  span: TraceSpan | null;
  prompts: PromptRow[];
}) {
  const recorded = useMemo(() => promptOf(span?.inputs), [span]);
  const [system, setSystem] = useState<string | null>(null);
  const [user, setUser] = useState<string | null>(null);

  // A new span means new text. Adjusted during render rather than in an
  // effect, so the pane never paints the previous call's prompt.
  const [shownSpan, setShownSpan] = useState(span?.id ?? null);
  if (shownSpan !== (span?.id ?? null)) {
    setShownSpan(span?.id ?? null);
    setSystem(null);
    setUser(null);
  }

  const replay = useReplay(runId);
  const savePrompt = useSavePrompt();
  const resetPrompt = useResetPrompt();

  if (!span) {
    return (
      <PanelShell title="호출 상세" note="프롬프트를 고쳐 다시 돌려볼 수 있습니다">
        <div className="grid h-full place-items-center p-6 text-center">
          <p className="max-w-64 text-sm text-ink-faint">호출을 선택하면 여기에서 읽고 다시 실행할 수 있습니다.</p>
        </div>
      </PanelShell>
    );
  }

  const step = typeof span.meta?.step === "string" ? span.meta.step : null;
  const prompt = step ? prompts.find((row) => row.name === step) : undefined;
  const isLlm = span.kind === "llm";
  const edited = system !== null || user !== null;

  return (
    <PanelShell
      title="호출 상세"
      note={span.kind}
      actions={
        isLlm && (
          <Button
            size="xs"
            disabled={!runId || replay.isPending}
            onClick={() => replay.mutate({ spanId: span.id, system, user })}
          >
            <Play />
            {replay.isPending ? "실행 중…" : "다시 실행"}
          </Button>
        )
      }
    >
      <div className="space-y-3 p-3">
        <header className="space-y-1">
          <h3 className="truncate font-mono text-xs text-ink-strong">{span.name}</h3>
          <div className="flex flex-wrap items-center gap-1.5 text-2xs text-ink-faint">
            <Badge variant="outline" className="px-1.5 py-0 text-2xs font-normal">
              {span.status}
            </Badge>
            <span>{seconds(span.latency_ms)}</span>
            {span.tokens ? <span>{span.tokens} tok</span> : null}
            {typeof span.meta?.ls_model_name === "string" && <span className="truncate">{span.meta.ls_model_name}</span>}
          </div>
          {span.error && <p className="text-2xs text-danger">{span.error}</p>}
        </header>

        <Tabs defaultValue={isLlm ? "prompt" : "io"}>
          <TabsList variant="line" className="h-7 gap-0 bg-transparent p-0">
            {isLlm && (
              <TabsTrigger value="prompt" className="px-2 text-2xs">
                프롬프트
              </TabsTrigger>
            )}
            <TabsTrigger value="io" className="px-2 text-2xs">
              원본 입출력
            </TabsTrigger>
            <TabsTrigger value="meta" className="px-2 text-2xs">
              메타
            </TabsTrigger>
          </TabsList>

          {isLlm && (
            <TabsContent value="prompt" className="space-y-2 pt-2">
              <p className="text-2xs text-ink-faint">
                여기서 실행해도 이 실행의 기록·보고서는 바뀌지 않습니다. 저장해야 이후 실행에 적용됩니다.
              </p>

              <label className="block space-y-1">
                <span className="text-2xs text-ink-muted">시스템</span>
                <Textarea
                  rows={6}
                  className="font-mono text-2xs"
                  value={system ?? recorded.system}
                  onChange={(event) => setSystem(event.target.value)}
                />
              </label>

              <label className="block space-y-1">
                <span className="text-2xs text-ink-muted">사용자</span>
                <Textarea
                  rows={8}
                  className="font-mono text-2xs"
                  value={user ?? recorded.user}
                  onChange={(event) => setUser(event.target.value)}
                />
              </label>

              {prompt && (
                <div className="flex items-center gap-1.5">
                  <Button
                    size="xs"
                    variant="outline"
                    disabled={!edited || savePrompt.isPending}
                    onClick={() => savePrompt.mutate({ name: prompt.name, text: system ?? recorded.system })}
                  >
                    <Save />
                    {prompt.name} 으로 저장
                  </Button>
                  {prompt.override !== null && (
                    <Button size="xs" variant="ghost" onClick={() => resetPrompt.mutate(prompt.name)}>
                      <RotateCcw />
                      기본값으로
                    </Button>
                  )}
                </div>
              )}

              {replay.data && (
                <section className="space-y-1">
                  <div className="flex items-center gap-2 text-2xs text-ink-faint">
                    <span className="text-ink-muted">기록된 결과 ↔ 다시 실행한 결과</span>
                    <span>{replay.data.latency_ms}ms</span>
                    {replay.data.schema && (
                      <Badge variant="outline" className="px-1 py-0 text-2xs font-normal">
                        {replay.data.schema}
                      </Badge>
                    )}
                  </div>
                  {/* Side by side, rather than two <pre>s compared by eye --
                      which is how this was read before, and the reason a
                      one-word change was invisible. */}
                  <div className="h-64 overflow-hidden rounded-sm border border-line">
                    <DiffView
                      original={JSON.stringify(replay.data.recorded.output, null, 2)}
                      modified={JSON.stringify(replay.data.output, null, 2)}
                    />
                  </div>
                </section>
              )}
            </TabsContent>
          )}

          <TabsContent value="io" className="space-y-2 pt-2">
            <div className="space-y-1">
              <span className="text-2xs text-ink-muted">입력</span>
              <Payload value={span.inputs} className={PRE} />
            </div>
            <div className="space-y-1">
              <span className="text-2xs text-ink-muted">출력</span>
              {replyOf(span.outputs) ? (
                <pre className={PRE}>{replyOf(span.outputs)}</pre>
              ) : (
                <Payload value={span.outputs} className={PRE} />
              )}
            </div>
          </TabsContent>

          <TabsContent value="meta" className="pt-2">
            <pre className={PRE}>{JSON.stringify(span.meta, null, 2)}</pre>
          </TabsContent>
        </Tabs>
      </div>
    </PanelShell>
  );
}
