"use client";

import { useMemo } from "react";

import NodeCard from "@/features/agent/NodeCard";
import RunShape from "@/features/agent/RunShape";
import Verdict from "@/features/agent/Verdict";
import { PanelShell } from "@/components/workbench/PanelShell";
import SpanInspector from "@/features/trace/SpanInspector";
import { fromAgent } from "@/lib/model/finding";
import { useFindings } from "@/lib/run/queries";
import { idOf, useSelection } from "@/lib/run/selection";
import { useGraphShape, usePrompts, useSpans } from "@/lib/run/trace-queries";
import { useRunId } from "@/lib/run/use-run-id";

/**
 * The right column: is this real, and how sure are we.
 *
 * It used to be `상세`, which rendered whichever of four kinds of thing was last
 * selected -- a finding, a call, a node, a checkpoint -- in 460px, so it was
 * sized for none of them and picking a call destroyed the finding you were
 * reading it for. Two of those four have somewhere better now: a call is a step
 * in the centre's 과정 view, and checkpoints are gone with the feature.
 *
 * What is left is a verdict. The patch and the reasoning chain moved to the
 * centre because a diff and a 3,628-character prompt want width; this column
 * keeps the claim, the confidence, one sentence and a walk through the
 * evidence, and stays on screen while you read either of them.
 *
 * With nothing selected it is the run's own shape rather than a "pick
 * something" apology -- which is also where the cost went when the run strip
 * was dissected.
 */
export default function AgentAside() {
  const [runId] = useRunId();
  const { selection } = useSelection();
  const findings = useFindings(runId);
  const shape = useGraphShape();
  const prompts = usePrompts();
  const spans = useSpans(runId);

  const id = idOf(selection, "finding");
  const finding = useMemo(() => {
    if (!id) return null;
    const all = fromAgent(findings.data?.findings);
    return all.find((each) => each.id === id) ?? all.find((each) => each.mergedIds.includes(id)) ?? null;
  }, [findings.data, id]);

  if (finding) return <Verdict finding={finding} />;

  // A node, picked on the drawing. Its card is small and belongs beside the
  // thing it describes rather than in a tab of its own.
  const node = idOf(selection, "node");
  if (node) {
    const note = shape.data?.node_notes?.find((each) => each.node === node);
    return (
      <PanelShell title="노드" note={<span className="font-mono text-2xs">{node}</span>}>
        {note ? (
          <NodeCard note={note} steps={shape.data?.steps ?? []} prompts={prompts.data ?? []} />
        ) : (
          <p className="px-3 py-2.5 text-2xs text-ink-faint">이 노드에 대한 설명이 아직 없습니다.</p>
        )}
      </PanelShell>
    );
  }

  // A call picked from somewhere other than the 과정 view -- the drawing's log,
  // say. Rare, and the centre is where its full text lives.
  const call = idOf(selection, "call");
  if (call) {
    const span = spans.data?.spans.find((each) => each.id === call) ?? null;
    return (
      <PanelShell title="호출" note={<span className="truncate font-mono text-2xs">{span?.name ?? call}</span>}>
        <SpanInspector runId={runId} span={span} prompts={prompts.data ?? []} />
      </PanelShell>
    );
  }

  return <RunShape />;
}
