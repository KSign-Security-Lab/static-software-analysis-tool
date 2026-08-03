"use client";

import type { Evidence, Finding } from "@/lib/agent-schema";
import { severityLabel } from "@/lib/markers";

/**
 * The detail view for one finding: why it is a vulnerability, the evidence
 * behind that claim, and a proposed fix.
 *
 * Evidence spans are clickable and may point into other files -- following the
 * trail from source to sink across a file boundary is most of what this view is
 * for, versus a flat list of warnings.
 *
 * The fix is shown, never applied. There is no write endpoint behind this.
 */

const ROLE_LABEL: Record<Evidence["role"], string> = {
  source: "유입 지점",
  propagation: "전파 경로",
  sink: "위험 지점",
  missing_check: "누락된 검증",
  context: "참고",
};

export interface FindingPanelProps {
  finding: Finding | null;
  onNavigate: (file: string, line: number) => void;
  onClose: () => void;
}

export function FindingPanel({ finding, onNavigate, onClose }: FindingPanelProps) {
  if (!finding) {
    return (
      <aside className="panel panel-empty">
        <p className="empty">취약점을 선택하면 근거와 수정 제안이 여기에 표시됩니다.</p>
      </aside>
    );
  }

  // Optional on the wire -- it carries a server-side default, so a serialised
  // finding may omit the key.
  const evidence = finding.evidence ?? [];

  return (
    <aside className="panel">
      <header className="panel-head">
        <div className="panel-title-row">
          <span className={`sev-chip sev-${finding.severity}`}>
            {severityLabel(finding.severity)}
          </span>
          {finding.cwe && <span className="cwe-chip">{finding.cwe}</span>}
          {!finding.verified && (
            <span className="unverified-chip" title="검증 단계를 거치지 않았습니다">
              미검증
            </span>
          )}
          <button type="button" className="panel-close" onClick={onClose} aria-label="닫기">
            ×
          </button>
        </div>
        <h2 className="panel-title">{finding.title}</h2>
        <button
          type="button"
          className="panel-location"
          onClick={() => onNavigate(finding.primary.file, finding.primary.start_line)}
        >
          {finding.primary.file}:{finding.primary.start_line}
        </button>
      </header>

      <section className="panel-section">
        <h3>설명</h3>
        <p className="prose">{finding.explanation}</p>
      </section>

      <section className="panel-section">
        <h3>근거</h3>
        {evidence.length === 0 ? (
          <p className="empty">제시된 근거가 없습니다.</p>
        ) : (
          <ol className="evidence-list">
            {evidence.map((item, index) => (
              <li key={`${item.span.file}:${item.span.start_line}:${index}`}>
                <button
                  type="button"
                  className={`evidence-row role-${item.role}`}
                  onClick={() => onNavigate(item.span.file, item.span.start_line)}
                >
                  <span className="evidence-role">{ROLE_LABEL[item.role] ?? item.role}</span>
                  <code className="evidence-code">{item.span.excerpt.trim()}</code>
                  <span className="evidence-where">
                    {item.span.file}:{item.span.start_line}
                  </span>
                  <span className="evidence-note">{item.note}</span>
                </button>
              </li>
            ))}
          </ol>
        )}
      </section>

      <section className="panel-section">
        <h3>수정 제안</h3>
        <p className="fix-summary">{finding.remediation.summary}</p>
        <p className="prose">{finding.remediation.detail}</p>
        {finding.remediation.diff && (
          <pre className="fix-diff">
            <code>{finding.remediation.diff}</code>
          </pre>
        )}
        <p className="fix-note">
          제안일 뿐이며 자동으로 적용되지 않습니다. 직접 검토 후 반영하세요.
        </p>
      </section>

      <footer className="panel-foot">
        신뢰도 {(finding.confidence * 100).toFixed(0)}%
      </footer>
    </aside>
  );
}
