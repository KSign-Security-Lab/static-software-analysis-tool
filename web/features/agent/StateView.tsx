"use client";

import StatePanel from "@/features/trace/StatePanel";
import { useRunStream } from "@/lib/run/stream";
import { useCheckpoints, useResume } from "@/lib/run/trace-queries";
import { useRunId } from "@/lib/run/use-run-id";
import { useFullState, useSelectedCheckpoint } from "../trace/state";

/**
 * The run's history, wired to the run.
 *
 * A centre view rather than a dock tab. It belongs beside 에이전트 구조: you set
 * a breakpoint on the graph, the run stops, and this is where you look at the
 * state it stopped in and send it down another branch. Sharing a tab strip with
 * 문제 put the debugger and the answer on the same footing.
 */
export default function StateView() {
  const [runId] = useRunId();
  const [checkpointId, setCheckpointId] = useSelectedCheckpoint();
  const [full, setFull] = useFullState();

  const { live, phase, ensureAttached } = useRunStream();
  const checkpoints = useCheckpoints(runId, full);
  const resume = useResume(runId, ensureAttached);

  return (
    <StatePanel
      checkpoints={checkpoints.data?.checkpoints ?? []}
      selected={checkpointId ?? live.checkpointId}
      full={full}
      busy={resume.isPending}
      interrupted={phase === "paused"}
      waiting={phase === "running" || phase === "starting"}
      onSelect={(id) => void setCheckpointId(id)}
      onFull={(next) => void setFull(next)}
      onFork={(id, values) => resume.mutate({ checkpointId: id, values })}
      onRerun={(id) => resume.mutate({ checkpointId: id })}
    />
  );
}
