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
  const handlerMode = d?.kind === "handler";
  const nRes = decisions.filter((x) => x.verdict === "확정").length;
  const nAmb = decisions.filter((x) => x.verdict === "모호").length;
  const nUnres = decisions.filter((x) => x.verdict === "미해결").length;

  return (
    <div className="report">
      {handlerMode && (
        <p className="status" style={{ margin: "0 0 12px" }}>
          소스→싱크 근거는 없지만, 액션별 핸들러 판정이 권위 있는 결과입니다 (확정 {nRes} · 모호{" "}
          {nAmb} · 미해결 {nUnres}).
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
