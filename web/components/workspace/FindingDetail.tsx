"use client";

import { ENGINE_LABEL, ROLE_LABEL, SEVERITY_LABEL, type UiFinding } from "@/lib/model/finding";

/**
 * Why this is a finding, what it rests on, and what to do.
 *
 * Evidence rows are clickable and may point into other files -- following the
 * trail from source to sink across a file boundary is most of the value over a
 * flat list. Remediation is shown, never applied.
 */
export default function FindingDetail({
  finding,
  onNavigate,
  onClose,
}: {
  finding: UiFinding | null;
  onNavigate: (file: string) => void;
  onClose: () => void;
}) {
  if (!finding) {
    return (
      <aside className="ws-detail is-empty">
        <p className="ws-empty">결과를 선택하면 근거와 권고가 표시됩니다.</p>
      </aside>
    );
  }

  return (
    <aside className="ws-detail">
      <header className="ws-detail-head">
        <div className="ws-detail-chips">
          <span className={`ws-chip-solid sev-${finding.severity}`}>{SEVERITY_LABEL[finding.severity]}</span>
          <span className={`ws-tag eng-${finding.engine}`}>{ENGINE_LABEL[finding.engine]}</span>
          {finding.cwe && <span className="ws-chip-mono">{finding.cwe}</span>}
          {finding.verified === false && <span className="ws-chip-warn">미검증</span>}
          <button type="button" className="ws-close" onClick={onClose} aria-label="닫기">
            ×
          </button>
        </div>
        <h2>{finding.title}</h2>
        {finding.primary.startLine > 0 && (
          <button
            type="button"
            className="ws-jump"
            onClick={() => onNavigate(finding.primary.file)}
          >
            {finding.primary.file}:{finding.primary.startLine}
          </button>
        )}
      </header>

      <section className="ws-section">
        <h3>설명</h3>
        <p className="ws-prose">{finding.explanation}</p>
      </section>

      <section className="ws-section">
        <h3>근거</h3>
        {finding.evidence.length === 0 ? (
          <p className="ws-empty">제시된 근거가 없습니다.</p>
        ) : (
          <ol className="ws-evidence">
            {finding.evidence.map((e, i) => (
              <li key={`${e.span.file}-${e.span.startLine}-${i}`}>
                <button
                  type="button"
                  className={`ws-ev role-${e.role}`}
                  onClick={() => onNavigate(e.span.file)}
                  disabled={e.span.startLine <= 0}
                >
                  <span className="ws-ev-role">{ROLE_LABEL[e.role]}</span>
                  {e.span.startLine > 0 && (
                    <span className="ws-ev-where">
                      {e.span.file}:{e.span.startLine}
                    </span>
                  )}
                  {e.span.excerpt.trim() && <code className="ws-ev-code">{e.span.excerpt.trim()}</code>}
                  <span className="ws-ev-note">{e.note}</span>
                </button>
              </li>
            ))}
          </ol>
        )}
      </section>

      {finding.remediation && (
        <section className="ws-section">
          <h3>권고</h3>
          <p className="ws-prose">{finding.remediation}</p>
          <p className="ws-note">제안일 뿐이며 자동으로 적용되지 않습니다.</p>
        </section>
      )}

      <footer className="ws-detail-foot">신뢰도 {(finding.confidence * 100).toFixed(0)}%</footer>
    </aside>
  );
}
