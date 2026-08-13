"use client";

import { useMemo, useState } from "react";

import { fromAgent } from "@/lib/model/finding";
import { useFindings } from "@/lib/run/queries";
import { useSelectedFinding } from "@/lib/run/selection";
import { useRunStream } from "@/lib/run/stream";
import { useGraphShape, usePrompts, useSpans, useThreads } from "@/lib/run/trace-queries";
import { useRunId } from "@/lib/run/use-run-id";
import { claimOf, trailOf, unitsOf } from "@/lib/trace/process";
import { usePaneMode, useScopedNode, useSelectedSpan } from "../trace/state";
import RunPane from "./RunPane";
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
 *
 * Opening a finding narrows it to that finding's own unit. This page exists to
 * put the answer beside the reasoning, and until now the two were only *next to*
 * each other: you read a claim in the dock and the pane on the right went on
 * showing all forty conversations in the run, of which one was the reason for
 * what you were reading. The join was already there and documented -- a thread
 * is keyed by chunk id, and a finding carries the chunk it came from.
 */
export default function InspectorPane() {
  const [runId] = useRunId();
  const [spanId, setSpanId] = useSelectedSpan();
  const [node, setNode] = useScopedNode();
  const [mode, setMode] = usePaneMode();
  const [findingId] = useSelectedFinding();
  const { live, phase } = useRunStream();

  const [tuning, setTuning] = useState(false);
  const [scoped, setScoped] = useState(true);

  const threads = useThreads(runId);
  const shape = useGraphShape();
  const spans = useSpans(runId);
  const prompts = usePrompts();
  const findings = useFindings(runId);

  const steps = useMemo(() => shape.data?.steps ?? [], [shape.data]);
  // What the picked node is. Five of them make no calls at all, so this is the only
  // thing the pane can say about them -- and it is the answer to why.
  const note = useMemo(
    () => (node ? shape.data?.node_notes?.find((each) => each.node === node) : undefined),
    [shape.data, node],
  );
  // Through `fromAgent`, because `?finding=` holds the view model's id and the
  // view model prefixes it with the engine -- matching against the wire id
  // matches nothing, silently, which is exactly how it read.
  const finding = useMemo(
    () => (findingId ? fromAgent(findings.data?.findings).find((each) => each.id === findingId) : undefined),
    [findings.data, findingId],
  );

  // A different claim is a different question, so the narrowing comes back on.
  // Adjusted during render rather than in an effect: React re-runs this
  // component immediately, before the browser sees the un-narrowed transcript.
  const [scopedFor, setScopedFor] = useState(findingId);
  if (scopedFor !== findingId) {
    setScopedFor(findingId);
    setScoped(true);
  }

  const all = useMemo(() => unitsOf(threads.data?.threads ?? [], steps, node), [threads.data, steps, node]);
  // Composed with the node scope rather than replacing it: narrowed to both, the
  // pane answers "what did 검증 say about this one", which is a real question.
  const narrowed = Boolean(finding?.chunkId) && scoped;
  // Down to the claim, not just to its unit. A unit holds every specialist's
  // reading of one function, so scoping by chunk alone still answered "what was
  // said about this function" when the question was "why does this line have a
  // problem". `trailOf` keeps the chain that produced this finding and drops the
  // other lenses and the other claims.
  const units = useMemo(
    () =>
      narrowed
        ? all.filter((unit) => unit.id === finding!.chunkId).map((unit) => trailOf(unit, claimOf(finding!)))
        : all,
    [all, narrowed, finding],
  );

  const span = useMemo(() => spans.data?.spans.find((each) => each.id === spanId) ?? null, [spans.data, spanId]);

  return (
    <>
      <RunPane
        units={units}
        steps={steps}
        // The standing brief behind a node, which is most of what a node *is*. The
        // list was already fetched here for the editor and only the editor saw it.
        prompts={prompts.data ?? []}
        mode={mode}
        onMode={(next) => void setMode(next)}
        phase={phase}
        live={live}
        node={node}
        onClearNode={() => void setNode(null)}
        note={note}
        focus={finding ? { title: finding.title, scoped: narrowed, onScoped: setScoped } : null}
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
