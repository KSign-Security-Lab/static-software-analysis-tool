"use client";

import { useMemo } from "react";

import TraceInspectorPane from "@/features/trace/TraceInspectorPane";
import { fromAgent } from "@/lib/model/finding";
import { useKnowledge } from "@/lib/run/knowledge-queries";
import { useFindings } from "@/lib/run/queries";
import { useRunId } from "@/lib/run/use-run-id";
import FindingInspector from "./FindingInspector";
import { useInspectorView, useOpenFile, useSelectedFinding } from "./state";

/**
 * The right pane: why the agent said it, or what it actually asked.
 *
 * Two inspectors, because the two questions have different answers -- a
 * finding's evidence is not a model call's prompt -- and since the merge both
 * of the lists that lead here sit in the same dock.
 *
 * It follows the last thing you clicked rather than offering a tab strip of
 * its own. You only ever arrive by picking something out of 문제 or 호출 기록,
 * so a switcher would be a second row of chrome above a header that already
 * names the pane, to reach a view you would have reached by clicking the thing
 * you wanted. `insp` is in the URL all the same, so a link can still say which
 * one it meant.
 */
export default function InspectorPane() {
  const [runId] = useRunId();
  const [, setPath] = useOpenFile();
  const [selectedId, setSelectedId] = useSelectedFinding();
  const [view] = useInspectorView();

  const findings = useFindings(runId);
  const knowledge = useKnowledge(runId);
  const ui = useMemo(() => fromAgent(findings.data?.findings ?? []), [findings.data]);
  const selected = useMemo(() => ui.find((each) => each.id === selectedId) ?? null, [ui, selectedId]);

  if (view === "span") return <TraceInspectorPane />;

  return (
    <FindingInspector
      finding={selected}
      knowledge={knowledge.data}
      onNavigate={(file) => {
        // Selecting is what moves the editor's caret; this only has to make
        // sure the right file is open. CodeEditor reveals the line itself.
        void setPath(file);
        if (!selectedId) void setSelectedId(null);
      }}
    />
  );
}
