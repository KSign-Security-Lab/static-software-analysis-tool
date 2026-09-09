"use client";

import { useEffect, useMemo } from "react";

import BackendDown from "@/features/inspect/BackendDown";
import Findings from "@/features/inspect/Findings";
import Intake from "@/features/inspect/Intake";
import RunBar from "@/features/inspect/RunBar";
import { reconcile } from "@/lib/inspect/bucket";
import { isScanning, isStopped, stageOf } from "@/lib/inspect/stage";
import { fromAgent } from "@/lib/model/finding";
import { useFindings, useRun } from "@/lib/run/queries";
import { useRunStream } from "@/lib/run/stream";
import { useRunId } from "@/lib/run/use-run-id";

export default function Inspect() {
  const [runId] = useRunId();
  const { live } = useRunStream();
  const run = useRun(runId);
  const report = useFindings(runId);

  const findings = useMemo(() => fromAgent(report.data?.findings), [report.data]);
  const stage = stageOf({ run: run.data, live, hasFindings: findings.length > 0 });
  const scanning = isScanning({ run: run.data, live });
  const stopped = isStopped({ run: run.data, live });

  useEffect(() => {
    if (!runId || !report.data) return;
    reconcile(
      runId,
      findings.map((each) => each.id),
    );
  }, [runId, report.data, findings]);

  return (
    <>
      <RunBar findings={findings} />
      <BackendDown />
      {stage === "intake" && <Intake run={run.data} />}
      {stage === "results" && (
        <Findings findings={findings} stats={report.data?.stats} scanning={scanning} stopped={stopped} />
      )}
    </>
  );
}
