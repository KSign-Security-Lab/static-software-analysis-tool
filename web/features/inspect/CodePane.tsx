"use client";

import EditorPane from "@/features/agent/EditorPane";
import { useRunId } from "@/lib/run/use-run-id";

/** The editor, with the run it belongs to. `CentrePane` used to thread this. */
export default function CodePane() {
  const [runId] = useRunId();
  return <EditorPane runId={runId} />;
}
