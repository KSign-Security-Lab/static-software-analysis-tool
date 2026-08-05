"use client";

import { useMemo } from "react";

import { fromAgent } from "@/lib/model/finding";
import { useKnowledge } from "@/lib/run/knowledge-queries";
import { useFindings } from "@/lib/run/queries";
import { useRunId } from "@/lib/run/use-run-id";
import FindingInspector from "./FindingInspector";
import { useOpenFile, useSelectedFinding } from "./state";

export default function InspectorPane() {
  const [runId] = useRunId();
  const [, setPath] = useOpenFile();
  const [selectedId, setSelectedId] = useSelectedFinding();

  const findings = useFindings(runId);
  const knowledge = useKnowledge(runId);
  const ui = useMemo(() => fromAgent(findings.data?.findings ?? []), [findings.data]);
  const selected = useMemo(() => ui.find((each) => each.id === selectedId) ?? null, [ui, selectedId]);

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
