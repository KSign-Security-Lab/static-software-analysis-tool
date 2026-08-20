"use client";

import { useEffect, useMemo } from "react";

import BackendDown from "@/features/inspect/BackendDown";
import Findings from "@/features/inspect/Findings";
import Intake from "@/features/inspect/Intake";
import Progress from "@/features/inspect/Progress";
import RunBar from "@/features/inspect/RunBar";
import { reconcile } from "@/lib/inspect/bucket";
import { stageOf } from "@/lib/inspect/stage";
import { fromAgent } from "@/lib/model/finding";
import { useFindings, useRun } from "@/lib/run/queries";
import { useRunStream } from "@/lib/run/stream";
import { useRunId } from "@/lib/run/use-run-id";

/**
 * Which of the three screens to show, and the strip above all of them.
 *
 * The stage is derived -- see `lib/inspect/stage.ts` -- so this component holds
 * no state at all. Everything it renders is a function of the run row, the event
 * stream and the report.
 *
 * Findings are read here rather than in `Findings` because two things below need
 * them: the results table, and the stage decision itself, which has to know
 * whether a failed or parked run has anything worth showing.
 */
export default function Inspect() {
  const [runId] = useRunId();
  const run = useRun(runId);
  const report = useFindings(runId);
  const { live } = useRunStream();

  const findings = useMemo(() => fromAgent(report.data?.findings), [report.data]);
  const stage = stageOf({ run: run.data, live, hasFindings: findings.length > 0 });

  // Ticks for findings the report no longer has, dropped as soon as the report
  // says so. A re-scan gives every changed finding a new id -- they are derived
  // from the anchor text -- so without this the tray would count claims the
  // server would then refuse as unknown.
  //
  // In an effect, not during render: `reconcile` notifies an external store, and
  // a store that changes mid-render tears the components already subscribed to
  // it. React's own rule, and this is exactly the shape it is about.
  useEffect(() => {
    if (!runId || !report.data) return;
    reconcile(
      runId,
      findings.map((each) => each.id),
    );
  }, [runId, report.data, findings]);

  return (
    <>
      <RunBar stage={stage} findings={findings} />
      {/* Above the stage, not inside one. A dead backend is not a property of
          intake or of results -- and it is exactly the moment the screen below
          becomes untrustworthy, so it has to be said where it cannot be
          mistaken for part of the flow. */}
      <BackendDown />
      {stage === "intake" && <Intake run={run.data} />}
      {stage === "scanning" && <Progress findings={findings} />}
      {stage === "results" && <Findings findings={findings} />}
    </>
  );
}
