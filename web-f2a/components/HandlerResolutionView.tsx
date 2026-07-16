"use client";

import type {
  HandlerResolution,
  HandlerResolutionEvidence,
  ResolutionStatus,
} from "@/lib/types";

function EvidenceTrail({ evidence }: { evidence: HandlerResolutionEvidence[] }) {
  if (!evidence.length) return null;
  return (
    <div className="evtrail">
      {evidence.map((e, i) => {
        const a = e.action_id;
        const id = a.symbol ?? a.raw_expression ?? (a.numeric_id != null ? String(a.numeric_id) : null);
        return (
          <div className="evrec" key={i} style={{ marginTop: 8 }}>
            <div className="row" style={{ flexWrap: "wrap", gap: 6 }}>
              <span className="badge">{e.kind}</span>
              <span className="badge">일치 {e.match_strength}</span>
              <span className="badge">식별자 {e.action_id_consistency}</span>
              {e.provenance_group && <span className="badge mono">{e.provenance_group}</span>}
              <span className="badge">
                점수 {e.score_pre_penalty.toFixed(2)}→{e.score.toFixed(2)}
              </span>
            </div>
            {id && (
              <p className="status mono" style={{ margin: "6px 0", fontSize: 12 }}>
                매칭된 식별자: {id}
                {a.resolved_value != null ? ` (= ${a.resolved_value})` : ""}
              </p>
            )}
            <div className="flowline">
              {e.records.map((rec, j) => (
                <span key={j} style={{ display: "contents" }}>
                  {j > 0 && <span className="arrow">→</span>}
                  <span className="pill step" title={`${rec.file}:${String(rec.line)}`}>
                    <b>{rec.type}</b> {rec.value}
                  </span>
                </span>
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}

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
          {top && (top.evidence?.length ?? 0) > 0 && (
            <details className="limdetails" style={{ marginTop: 8 }}>
              <summary className="muted small">판정 근거 ({top.evidence!.length})</summary>
              <EvidenceTrail evidence={top.evidence!} />
            </details>
          )}
        </>
      )}

      {hr.status === "AMBIGUOUS" && (
        <>
          <p className="status" style={{ marginTop: 10 }}>
            경합하는 핸들러가 여러 개라 선택하지 않았습니다 (chosen = null).
            {hr.conflict ? ` 상위 두 후보 마진 ${hr.conflict.margin.toFixed(4)}.` : ""}
          </p>
          {/* Each candidate's evidence trail shown separately, so users can see
              why both survived and why no winner was chosen. */}
          {hr.candidates.map((c) => (
            <details className="limdetails" key={c.function} style={{ marginTop: 8 }}>
              <summary className="muted small">
                {c.function} · 신뢰도 {c.confidence.toFixed(2)} · {c.evidence_kinds.join(", ")}
              </summary>
              <EvidenceTrail evidence={c.evidence ?? []} />
            </details>
          ))}
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
