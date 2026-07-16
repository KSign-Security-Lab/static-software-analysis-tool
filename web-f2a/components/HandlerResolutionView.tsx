"use client";

import type { HandlerResolution, ResolutionStatus } from "@/lib/types";

function resStatusTag(status: ResolutionStatus): { cls: string; label: string } {
  switch (status) {
    case "RESOLVED":
      return { cls: "sat", label: "확정 · RESOLVED" };
    case "AMBIGUOUS":
      return { cls: "weak", label: "모호 · AMBIGUOUS" };
    default:
      return { cls: "unv", label: "미해결 · UNRESOLVED" };
  }
}

const STATUS_ORDER: Record<ResolutionStatus, number> = {
  RESOLVED: 0,
  AMBIGUOUS: 1,
  UNRESOLVED: 2,
};

export function HandlerResolutionCard({ hr }: { hr: HandlerResolution }) {
  const st = resStatusTag(hr.status);
  const top = hr.candidates[0];
  return (
    <div className="card">
      <div className="row" style={{ justifyContent: "space-between" }}>
        <h3 style={{ margin: 0 }}>
          {hr.action} <span className={`tag ${st.cls}`}>{st.label}</span>
        </h3>
        {hr.status === "RESOLVED" && top && (
          <span className="overall">
            <span className="num">{top.confidence.toFixed(2)}</span>
            <span className="status">신뢰도</span>
          </span>
        )}
      </div>

      {hr.status === "RESOLVED" && hr.chosen && (
        <>
          <p className="status" style={{ marginTop: 10 }}>
            선택된 핸들러: <span className="mono">{hr.chosen.function}</span> @ {hr.chosen.file}:
            {String(hr.chosen.line)}
          </p>
          {top && (
            <div className="row">
              <span className="status">근거 종류:</span>
              {top.evidence_kinds.map((k) => (
                <span key={k} className="badge">
                  {k}
                </span>
              ))}
              <span className="badge">식별자 일관성: {top.action_id_consistency}</span>
            </div>
          )}
        </>
      )}

      {hr.status === "AMBIGUOUS" && (
        <>
          <p className="status" style={{ marginTop: 10 }}>
            경합하는 핸들러가 여러 개라 선택하지 않았습니다 (chosen = null).
            {hr.conflict ? ` 상위 두 후보 마진 ${hr.conflict.margin.toFixed(4)}.` : ""}
          </p>
          <table className="checks">
            <thead>
              <tr>
                <th>경합 후보</th>
                <th>신뢰도</th>
                <th>근거 종류</th>
              </tr>
            </thead>
            <tbody>
              {hr.candidates.map((c) => (
                <tr key={c.function}>
                  <td className="mono">{c.function}</td>
                  <td>{c.confidence.toFixed(2)}</td>
                  <td>
                    {c.evidence_kinds.map((k) => (
                      <span key={k} className="badge">
                        {k}
                      </span>
                    ))}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}

      {hr.status === "UNRESOLVED" && (
        <>
          <p className="status" style={{ marginTop: 10 }}>
            미해결 사유: <span className="mono">{hr.unresolved?.reason ?? "NO_EVIDENCE"}</span>
            {hr.unresolved?.secondary ? ` (${hr.unresolved.secondary})` : ""}
          </p>
          {hr.unresolved?.dispatch_site && (
            <p className="status mono" style={{ fontSize: 12 }}>
              디스패치 위치: {hr.unresolved.dispatch_site.code} @{" "}
              {hr.unresolved.dispatch_site.file}:{String(hr.unresolved.dispatch_site.line)}
            </p>
          )}
          {hr.unresolved && hr.unresolved.attempted_extractors.length > 0 && (
            <div className="row">
              <span className="status">시도한 추출기:</span>
              {hr.unresolved.attempted_extractors.map((e) => (
                <span key={e} className="badge">
                  {e}
                </span>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}

/**
 * First-class Handler Resolution view: one card per action, sorted
 * RESOLVED > AMBIGUOUS > UNRESOLVED. Rendered whenever there is no source→sink
 * finding but the resolver produced per-action outcomes, so handler analysis is
 * never an empty page.
 */
export default function HandlerResolutionView({
  resolutions,
}: {
  resolutions: HandlerResolution[];
}) {
  const sorted = [...resolutions].sort(
    (a, b) => STATUS_ORDER[a.status] - STATUS_ORDER[b.status] || a.action.localeCompare(b.action),
  );
  const nRes = sorted.filter((r) => r.status === "RESOLVED").length;
  const nAmb = sorted.filter((r) => r.status === "AMBIGUOUS").length;
  const nUnres = sorted.filter((r) => r.status === "UNRESOLVED").length;

  return (
    <>
      <h3 style={{ margin: "6px 0 2px" }}>핸들러 판정</h3>
      <p className="status" style={{ marginTop: 0 }}>
        소스→싱크 근거는 없지만, 액션별 핸들러 판정이 권위 있는 결과입니다 (확정 {nRes} · 모호{" "}
        {nAmb} · 미해결 {nUnres}).
      </p>
      {sorted.map((hr) => (
        <HandlerResolutionCard key={hr.action} hr={hr} />
      ))}
    </>
  );
}
