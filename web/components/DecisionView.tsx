"use client";

import { useMemo, useState } from "react";
import { buildDecisions } from "@/lib/decision";
import ResultCard from "@/components/ResultCard";
import type { F2AResult } from "@/lib/types";

export default function DecisionView({
  result,
  source,
  onInspect,
}: {
  result: F2AResult;
  source: string;
  onInspect?: (fn: string) => void;
}) {
  const decisions = useMemo(() => buildDecisions(result), [result]);
  const [idx, setIdx] = useState(0);
  const d = decisions[Math.min(idx, decisions.length - 1)];

  // A handler-resolution report (no source→sink finding) gets a one-line summary
  // above the chip row so the two result types read as one report, not two UIs.
  // Counts are per-action (from the resolutions), not per-card — AMBIGUOUS emits
  // one card per candidate but is a single action outcome.
  const handlerMode = d?.kind === "handler";
  const res = result.handler_resolutions ?? [];
  const nRes = res.filter((r) => r.status === "RESOLVED").length;
  const nAmb = res.filter((r) => r.status === "AMBIGUOUS").length;
  const nUnres = res.filter((r) => r.status === "UNRESOLVED").length;

  return (
    <div className="report">
      {handlerMode && (
        <p className="status" style={{ margin: "0 0 12px" }}>
          소스→싱크 취약점은 발견되지 않았지만, 액션별 핸들러 분석을 완료했습니다 — 핸들러 확인{" "}
          {nRes} · 복수 후보 {nAmb} · 판정 불가 {nUnres}.
        </p>
      )}
      {decisions.length > 1 && (
        <div className="chiprow" style={{ marginBottom: 16 }}>
          {decisions.map((x, i) => (
            <button
              key={x.id}
              className={`tab ${i === idx ? "active" : ""}`}
              onClick={() => setIdx(i)}
            >
              {x.chipLabel}
            </button>
          ))}
        </div>
      )}
      <ResultCard d={d} source={source} onInspect={onInspect} />
    </div>
  );
}
