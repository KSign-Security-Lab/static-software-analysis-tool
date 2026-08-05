"use client";

import { useRunId } from "@/lib/run/use-run-id";
import EditorPane from "./EditorPane";

/** Reads the run from the URL so the page itself can stay a server component. */
export default function EditorPaneRoute() {
  const [runId] = useRunId();
  return <EditorPane runId={runId} />;
}
