"use client";

import { useMemo, useState } from "react";

import { useRunStream } from "@/lib/run/stream";
import { useGraphShape, usePrompts, useSpans, useThreads } from "@/lib/run/trace-queries";
import { useRunId } from "@/lib/run/use-run-id";
import { unitsOf } from "@/lib/trace/process";
import { useScopedNode, useSelectedSpan } from "../trace/state";
import ChatPane from "./ChatPane";
import PromptSheet from "./PromptSheet";

/**
 * The right pane: the run, as the conversation it is.
 *
 * It used to be two inspectors that swapped by whatever you last clicked -- a
 * finding's grounds, or one call's prompt -- and it sat empty until you had
 * clicked something. Neither was a view of the run; both were details of a row in
 * a list somewhere else.
 *
 * A transcript needs nothing selected to be worth reading, so this is simply on.
 * Editing a prompt is a sheet over the top, because it is an action on one turn
 * rather than a third thing the pane can be.
 */
export default function InspectorPane() {
  const [runId] = useRunId();
  const [spanId, setSpanId] = useSelectedSpan();
  const [node] = useScopedNode();
  const { live, phase } = useRunStream();

  const [tuning, setTuning] = useState(false);

  const threads = useThreads(runId);
  const shape = useGraphShape();
  const spans = useSpans(runId);
  const prompts = usePrompts();

  const steps = useMemo(() => shape.data?.steps ?? [], [shape.data]);
  // What the picked node is. Five of them make no calls at all, so this is the only
  // thing the pane can say about them -- and it is the answer to why.
  const note = useMemo(
    () => (node ? shape.data?.node_notes?.find((each) => each.node === node) : undefined),
    [shape.data, node],
  );
  const units = useMemo(() => unitsOf(threads.data?.threads ?? [], steps, node), [threads.data, steps, node]);
  const span = useMemo(() => spans.data?.spans.find((each) => each.id === spanId) ?? null, [spans.data, spanId]);

  return (
    <>
      <ChatPane
        units={units}
        steps={steps}
        phase={phase}
        live={live}
        node={node}
        note={note}
        selected={spanId}
        onTunePrompt={(id) => {
          void setSpanId(id);
          setTuning(true);
        }}
      />
      <PromptSheet runId={runId} span={span} prompts={prompts.data ?? []} open={tuning} onOpenChange={setTuning} />
    </>
  );
}
