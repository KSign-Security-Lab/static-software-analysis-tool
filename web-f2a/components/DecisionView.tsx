"use client";

import { useMemo, useState } from "react";
import CodeSnippet from "./CodeSnippet";
import { buildDecisions, koStatus, type Decision, type Reason } from "@/lib/decision";
import type { F2AResult } from "@/lib/types";

const ICON: Record<Reason["icon"], string> = {
  found: "✓",
  warn: "!",
  bad: "→",
  missing: "✗",
  info: "i",
};

function statusClass(status: string): string {
  switch (status) {
    case "SATISFIED":
      return "sat";
    case "NEGATIVE":
      return "neg";
    case "WEAKLY_RELATED":
      return "weak";
    default:
      return "unv";
  }
}

function ExtraDetail({ reason }: { reason: Reason }) {
  const d = reason.detail;
  if (!d) return null;
  if (d.kind === "checks") {
    return (
      <table className="checks" style={{ marginTop: 12 }}>
        <thead>
          <tr>
            <th>필요한 검사</th>
            <th>상태</th>
            <th>관찰된 검사</th>
          </tr>
        </thead>
        <tbody>
          {d.rows.map((r) => (
            <tr key={r.id}>
              <td className="mono">{r.id}</td>
              <td>
                <span className={`tag ${statusClass(r.status)}`}>{koStatus(r.status)}</span>
              </td>
              <td className="muted small mono">{r.observed ?? r.evidence ?? "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    );
  }
  return (
    <div style={{ marginTop: 4 }}>
      <div className="muted small" style={{ marginBottom: 8 }}>
        {d.note}
      </div>
      <div className="confgrid" style={{ gridTemplateColumns: "1fr 1fr 1fr" }}>
        {d.factors.map(([k, v]) => (
          <div className="confrow" key={k}>
            <span className="muted mono small">{k}</span>
            <span className="cbar">
              <span style={{ width: `${Math.round(v * 100)}%` }} />
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

function ReasonRow({
  reason,
  source,
  onInspect,
}: {
  reason: Reason;
  source: string;
  onInspect?: (fn: string) => void;
}) {
  return (
    <details className="reason">
      <summary>
        <span className={`ricon ${reason.icon}`}>{ICON[reason.icon]}</span>
        <span className="rbody">
          <span className="rtitle">{reason.title}</span>
          <span className="rplain">{reason.plain}</span>
        </span>
        <span className="rchev">▸</span>
      </summary>
      <div className="rdetail">
        {reason.code && reason.code.length > 0 && <CodeSnippet source={source} refs={reason.code} />}
        <ExtraDetail reason={reason} />
        {reason.inspectFn && onInspect && (
          <button className="tblink" onClick={() => onInspect(reason.inspectFn!)}>
            그래프 탐색기에서 {reason.inspectFn}() 열기 ▸
          </button>
        )}
      </div>
    </details>
  );
}

function DecisionCard({
  d,
  source,
  onInspect,
}: {
  d: Decision;
  source: string;
  onInspect?: (fn: string) => void;
}) {
  const verdictCls = d.hasFinding ? "suspect" : "none";
  return (
    <div className="decision">
      <div className={`verdict ${verdictCls}`}>
        <div className="vtop">
          <span className={`vbadge ${verdictCls}`}>{d.verdict}</span>
        </div>
        <div className="vhero">
          <div>
            <h2 className="vheadline mono">{d.headline}</h2>
            <p className="vlead">{d.lead}</p>
            {d.cwe.length > 0 && (
              <div className="chiprow">
                {d.cwe.map((w) => (
                  <span key={w} className="badge">
                    {w}
                  </span>
                ))}
              </div>
            )}
          </div>
          {d.hasFinding && (
            <div className="confring">
              <div
                className="ring"
                style={{
                  background: `conic-gradient(var(--accent) ${Math.round(d.confidence * 360)}deg, rgba(255,255,255,0.08) 0)`,
                }}
              >
                <span className="rval">{d.confidence.toFixed(2)}</span>
              </div>
              <div className="rcap">신뢰도 · {d.confidenceLabel}</div>
            </div>
          )}
        </div>
      </div>

      {d.hasFinding ? (
        <>
          <div className="howlabel muted small">이렇게 판단했습니다 — 각 단계를 눌러 코드 근거를 확인하세요</div>
          <div className="reasons">
            {d.reasons.map((r) => (
              <ReasonRow key={r.id} reason={r} source={source} onInspect={onInspect} />
            ))}
          </div>
        </>
      ) : (
        <div className="card">
          {d.handlers.length > 0 && (
            <>
              <div className="muted small mono" style={{ marginBottom: 6 }}>
                발견된 핸들러
              </div>
              <div className="chiprow">
                {d.handlers.map((h, i) => (
                  <span key={i} className="badge">
                    {h.action} → {h.fn}
                  </span>
                ))}
              </div>
            </>
          )}
        </div>
      )}

      {d.limitations.length > 0 && (
        <details className="limdetails" style={{ marginTop: 16 }}>
          <summary className="muted small">한계 및 범위 ({d.limitations.length})</summary>
          <ul className="limits">
            {d.limitations.map((l, i) => (
              <li key={i}>{l}</li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}

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

  return (
    <div className="report">
      {decisions.length > 1 && (
        <div className="chiprow" style={{ marginBottom: 14 }}>
          {decisions.map((x, i) => (
            <button key={x.id} className={`tab ${i === idx ? "active" : ""}`} onClick={() => setIdx(i)}>
              {x.action}.{x.field}
            </button>
          ))}
        </div>
      )}
      <DecisionCard d={d} source={source} onInspect={onInspect} />
    </div>
  );
}
