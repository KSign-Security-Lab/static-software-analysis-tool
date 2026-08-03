"use client";

import type { Finding, SeverityName } from "@/lib/agent-schema";
import { SEVERITIES } from "@/lib/agent-schema";
import { severityLabel, sortFindings } from "@/lib/markers";

/**
 * Every finding in the run, most severe first, filterable by severity.
 *
 * Complements the in-editor markers: markers answer "what is wrong with this
 * file", the list answers "what is wrong with this upload".
 */

export interface FindingListProps {
  findings: Finding[];
  selectedId: string | null;
  severityFilter: Set<SeverityName>;
  onToggleSeverity: (severity: SeverityName) => void;
  onSelect: (finding: Finding) => void;
}

export function FindingList({
  findings,
  selectedId,
  severityFilter,
  onToggleSeverity,
  onSelect,
}: FindingListProps) {
  const visible = sortFindings(findings).filter((f) => severityFilter.has(f.severity));
  const counts = SEVERITIES.map((severity) => ({
    severity,
    count: findings.filter((f) => f.severity === severity).length,
  }));

  return (
    <div className="findings">
      <div className="findings-filters">
        {counts.map(({ severity, count }) => (
          <button
            key={severity}
            type="button"
            disabled={count === 0}
            className={`filter-chip sev-${severity}${severityFilter.has(severity) ? " is-on" : ""}`}
            onClick={() => onToggleSeverity(severity)}
          >
            {severityLabel(severity)} {count}
          </button>
        ))}
      </div>

      {visible.length === 0 ? (
        <p className="empty">표시할 취약점이 없습니다.</p>
      ) : (
        <ul className="findings-list">
          {visible.map((finding) => (
            <li key={finding.id}>
              <button
                type="button"
                className={`finding-row${finding.id === selectedId ? " is-selected" : ""}`}
                onClick={() => onSelect(finding)}
              >
                <span className={`sev-dot sev-${finding.severity}`} aria-hidden />
                <span className="finding-title">{finding.title}</span>
                <span className="finding-where">
                  {finding.primary.file}:{finding.primary.start_line}
                </span>
                {!finding.verified && <span className="unverified-chip">미검증</span>}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
