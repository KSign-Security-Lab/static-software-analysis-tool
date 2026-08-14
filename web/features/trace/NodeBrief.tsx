"use client";

import { Copy } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { CodeBlock } from "@/components/panel/code-block";
import { Button } from "@/components/ui/button";
import { PanelShell } from "@/components/workbench/PanelShell";
import NodeCard from "@/features/agent/NodeCard";
import SpanInspector from "@/features/trace/SpanInspector";
import { idOf, useSelection } from "@/lib/run/selection";
import { useGraphShape, usePrompts, useSpans } from "@/lib/run/trace-queries";
import { useRunId } from "@/lib/run/use-run-id";
import { cn } from "@/lib/utils";

/**
 * 노드: the one thing picked on this canvas, in full.
 *
 * The overlay's answer to the rule the page runs on -- the drawing is many, this
 * is one. It used to be only the prompt, with the node's card in a rail to the
 * right, which put one subject in two panels: what `verify` *is* over there, and
 * what `verify` is actually *told* down here. They are the same answer.
 *
 * Two kinds land here. A node, picked on the canvas, gets its card and the
 * standing instructions it runs under -- the most literal statement of its role
 * available, and the reason this panel is worth the width: a 1,600-character
 * brief was a scroll in a 320px rail and is a read across the canvas.
 *
 * A call, picked in 실행 기록, gets `SpanInspector` -- the prompts as sent, the
 * reply, the tool results. Already written, and reused rather than restated.
 */
export default function NodeBrief() {
  const [runId] = useRunId();
  const { selection } = useSelection();
  const node = idOf(selection, "node");
  const call = idOf(selection, "call");

  const shape = useGraphShape();
  const prompts = usePrompts();
  const spans = useSpans(runId);
  const [which, setWhich] = useState<string | null>(null);

  if (call) {
    const span = spans.data?.spans.find((each) => each.id === call) ?? null;
    return (
      <PanelShell title="호출" note={<span className="truncate font-mono text-2xs">{span?.name ?? call}</span>}>
        <SpanInspector runId={runId} span={span} prompts={prompts.data ?? []} />
      </PanelShell>
    );
  }

  const note = shape.data?.node_notes?.find((each) => each.node === node);
  const steps = (shape.data?.steps ?? []).filter((step) => step.node === node);
  // `verify` runs two -- the judgement and, when asked, the patch -- and they are
  // different instructions. Everything else runs one, and a picker for one thing
  // is a control that never earns its row.
  const step = steps.find((each) => each.step === which) ?? steps[0];
  const row = step ? prompts.data?.find((each) => each.name === step.prompt) : undefined;
  const text = row?.override ?? row?.default ?? "";

  return (
    <PanelShell
      title="노드"
      note={node && <span className="truncate font-mono text-2xs text-ink-faint">{node}</span>}
      actions={
        <>
          {steps.length > 1 && (
            <span className="flex items-center gap-0.5">
              {steps.map((each) => (
                <Button
                  key={each.step}
                  size="xs"
                  variant="ghost"
                  onClick={() => setWhich(each.step)}
                  className={cn("font-mono text-2xs", each.step === step?.step && "bg-surface-2 text-ink-strong")}
                >
                  {each.step}
                </Button>
              ))}
            </span>
          )}
          {text && (
            <Button
              size="xs"
              variant="ghost"
              className="text-ink-muted"
              onClick={() => void navigator.clipboard.writeText(text).then(() => toast.success("지시문을 복사했습니다"))}
            >
              <Copy />
              복사
            </Button>
          )}
        </>
      }
    >
      {!node ? (
        <p className="px-3 py-3 text-2xs leading-relaxed text-ink-faint">
          위 그림에서 노드를 하나 고르면, 그 노드가 무엇이고 실제로 어떤 지시를 받고 도는지 여기 나옵니다.
        </p>
      ) : (
        <>
          {note ? (
            <NodeCard note={note} steps={shape.data?.steps ?? []} prompts={prompts.data ?? []} />
          ) : (
            <p className="px-3 py-2.5 text-2xs text-ink-faint">이 노드에 대한 설명이 아직 없습니다.</p>
          )}

          {steps.length === 0 ? (
            // Five of the fourteen call no model at all, and this is the whole
            // answer for them -- they looked like agents that had done nothing.
            <p className="px-3 py-2.5 text-2xs leading-relaxed text-ink-faint">
              <span className="font-mono text-ink-muted">{node}</span> 는 모델을 부르지 않습니다. 정해진 코드가 돌
              뿐이라 지시문이 없습니다.
            </p>
          ) : !text ? (
            <p className="px-3 py-2.5 text-2xs text-ink-faint">지시문을 불러오는 중…</p>
          ) : (
            <div className="space-y-1 p-2.5">
              <h4 className="text-2xs text-ink-faint">
                지시문 · {step!.step}
                {row?.override ? " · 수정됨" : ""}
              </h4>
              <CodeBlock text={text} />
            </div>
          )}
        </>
      )}
    </PanelShell>
  );
}
