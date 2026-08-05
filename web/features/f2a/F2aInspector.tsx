"use client";

import { useMemo } from "react";

import { fromF2A } from "@/lib/model/finding";
import FindingInspector from "../agent/FindingInspector";
import { useSelectedFinding } from "../agent/state";
import { useCpgSource } from "../cpg/provider";

export default function F2aInspector() {
  const cpg = useCpgSource();
  const [selectedId] = useSelectedFinding();

  const findings = useMemo(
    () => (cpg.response ? fromF2A(cpg.response.f2a, cpg.name) : []),
    [cpg.response, cpg.name],
  );
  const selected = useMemo(() => findings.find((each) => each.id === selectedId) ?? null, [findings, selectedId]);

  // No knowledge graph here: that is indexed per agent run, and the structural
  // line has no chunk ids to join on.
  return <FindingInspector finding={selected} onNavigate={() => undefined} />;
}
