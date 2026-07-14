"use client";

import { useMemo, useState } from "react";
import type { F2AResult } from "@/lib/types";

type Which = "fragment" | "evidence" | "full";

const OPTS: { key: Which; label: string; file: string }[] = [
  { key: "fragment", label: "최종 후보 (F6)", file: "ocpp_native_candidate_fragments.json" },
  { key: "evidence", label: "근거 패키지", file: "ocpp_evidence_packages.json" },
  { key: "full", label: "전체 결과", file: "f2a_result.json" },
];

function pick(result: F2AResult, which: Which): unknown {
  if (which === "fragment") return result.candidate_fragments;
  if (which === "evidence") return result.evidence_packages;
  return result;
}

export default function JsonView({ result }: { result: F2AResult }) {
  const [which, setWhich] = useState<Which>("fragment");
  const [copied, setCopied] = useState(false);
  const opt = OPTS.find((o) => o.key === which)!;
  const data = useMemo(() => pick(result, which), [result, which]);
  const text = useMemo(() => JSON.stringify(data, null, 2), [data]);

  const empty = Array.isArray(data) && data.length === 0;

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1200);
    } catch {
      /* clipboard unavailable */
    }
  };

  const download = () => {
    const blob = new Blob([text], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = opt.file;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="report">
      <div className="jsonbar">
        <div className="chiprow">
          {OPTS.map((o) => (
            <button
              key={o.key}
              className={`tab ${which === o.key ? "active" : ""}`}
              onClick={() => setWhich(o.key)}
            >
              {o.label}
            </button>
          ))}
        </div>
        <div className="row">
          <button className="tbbtn" onClick={copy}>
            {copied ? "복사됨 ✓" : "복사"}
          </button>
          <button className="tbbtn" onClick={download}>
            다운로드
          </button>
        </div>
      </div>
      <p className="muted small" style={{ margin: "0 0 12px" }}>
        F6로 넘어가는 최종 산출물(JSON). <code>component_type</code>, ocpp_context,
        code_evidence(flow), 검사 결과, 신뢰도, 한계가 모두 파일/줄로 추적됩니다.
      </p>
      {empty ? (
        <div className="card">
          <p className="muted small" style={{ margin: 0 }}>
            이 분석에서는 해당 산출물이 없습니다 (source→sink 후보 없음).
          </p>
        </div>
      ) : (
        <div className="codeblock">
          <div className="codeblock-bar">
            <span className="dots">
              <i />
              <i />
              <i />
            </span>
            <span className="cb-label">{opt.file}</span>
          </div>
          <pre className="jsoncode">{text}</pre>
        </div>
      )}
    </div>
  );
}
