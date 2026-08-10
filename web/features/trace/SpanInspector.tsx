"use client";

import { MessageSquareCode, Play, RotateCcw, Save } from "lucide-react";
import { useMemo, useState } from "react";

import DiffView from "@/components/editor/DiffView.lazy";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { EmptyState, PanelShell } from "@/components/workbench/PanelShell";
import type { PromptRow, TraceSpan } from "@/lib/api/types";
import { seconds } from "@/lib/trace/process";
import { useReplay, useResetPrompt, useSavePrompt } from "@/lib/run/trace-queries";
import { promptOf } from "./Payload";

/**
 * One recorded call, and the means to make it answer better.
 *
 * Only that. Reading a call is what 진행 is for -- it shows the brief, the
 * message, the tools and the answer in the order they happened -- so this pane
 * no longer repeats them behind a tab strip, next to a raw JSON dump of the
 * payload and another of LangGraph's own metadata. Neither was ever the thing
 * anyone came here to read, and both made the one control that matters look
 * like a third debugging view.
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
      <PanelShell title="프롬프트 조정" note="고쳐서 다시 돌려볼 수 있습니다">
        <EmptyState icon={MessageSquareCode} title="고를 호출이 없습니다">
          아래 ‘진행’에서 모델 호출을 펼쳐 ‘프롬프트 고쳐 다시 실행’을 누르면, 주고받은 프롬프트를 여기서 고쳐 결과를
          비교할 수 있습니다.
        </EmptyState>
      </PanelShell>
    );
  }

  const step = typeof span.meta?.step === "string" ? span.meta.step : null;
  const prompt = step ? prompts.find((row) => row.name === step) : undefined;
  const edited = system !== null || user !== null;

  // Only a model call carries a prompt. A tool span reaches this pane when a
  // link names one, and telling the reader why there is nothing to edit beats a
  // pair of empty boxes.
  if (span.kind !== "llm") {
    return (
      <PanelShell title="프롬프트 조정" note={span.name}>
        <EmptyState icon={MessageSquareCode} title="이 호출에는 프롬프트가 없습니다">
          {span.name} 은 도구 호출입니다. 도구를 부른 모델 호출을 고르면 그 프롬프트를 고칠 수 있습니다.
        </EmptyState>
      </PanelShell>
    );
  }

  return (
    <PanelShell
      title="프롬프트 조정"
      note={step ?? undefined}
      actions={
        <Button
          size="xs"
          disabled={!runId || replay.isPending}
          onClick={() => replay.mutate({ spanId: span.id, system, user })}
        >
          <Play />
          {replay.isPending ? "실행 중…" : "다시 실행"}
        </Button>
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
            {/* Side by side, rather than two <pre>s compared by eye -- which is
                how this was read before, and the reason a one-word change was
                invisible. */}
            <div className="h-64 overflow-hidden rounded-sm border border-line">
              <DiffView
                original={JSON.stringify(replay.data.recorded.output, null, 2)}
                modified={JSON.stringify(replay.data.output, null, 2)}
              />
            </div>
          </section>
        )}
      </div>
    </PanelShell>
  );
}
