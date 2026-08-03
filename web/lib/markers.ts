import type { Finding, SeverityName } from "./agent-schema";
import { SEVERITY_RANK } from "./agent-schema";

/**
 * Findings -> Monaco markers and decorations.
 *
 * Monaco's marker API *is* the lint-warning surface: severity-coloured
 * squiggles, gutter marks, hover text and the problems list all come from the
 * same array. That is why the editor is Monaco -- the mapping below is nearly
 * the whole integration.
 *
 * Kept free of any `monaco` import so it can be unit-tested in node. The
 * numeric severities are Monaco's own `MarkerSeverity` values.
 */

/** monaco.MarkerSeverity: Hint=1, Info=2, Warning=4, Error=8. */
export const MARKER_SEVERITY = { Hint: 1, Info: 2, Warning: 4, Error: 8 } as const;

export interface EditorMarker {
  startLineNumber: number;
  startColumn: number;
  endLineNumber: number;
  endColumn: number;
  message: string;
  severity: number;
  source: string;
  /** Round-trip back to the finding when a marker is clicked. */
  code: string;
}

export interface EditorDecoration {
  range: {
    startLineNumber: number;
    startColumn: number;
    endLineNumber: number;
    endColumn: number;
  };
  options: {
    className?: string;
    inlineClassName?: string;
    hoverMessage?: { value: string };
    isWholeLine?: boolean;
  };
}

export function markerSeverity(severity: SeverityName): number {
  switch (severity) {
    case "critical":
    case "high":
      return MARKER_SEVERITY.Error;
    case "medium":
      return MARKER_SEVERITY.Warning;
    case "low":
      return MARKER_SEVERITY.Info;
    default:
      return MARKER_SEVERITY.Hint;
  }
}

const SEVERITY_LABEL: Record<SeverityName, string> = {
  critical: "치명적",
  high: "높음",
  medium: "보통",
  low: "낮음",
  info: "정보",
};

export function severityLabel(severity: SeverityName): string {
  return SEVERITY_LABEL[severity] ?? severity;
}

/** Findings in one file, as Monaco markers. */
export function markersFor(findings: Finding[], file: string): EditorMarker[] {
  return findings
    .filter((finding) => finding.primary.file === file)
    .map((finding) => {
      const span = finding.primary;
      const unverified = finding.verified ? "" : " (미검증)";
      return {
        startLineNumber: span.start_line,
        startColumn: span.start_column,
        endLineNumber: span.end_line,
        endColumn: span.end_column,
        message: `${finding.title}${unverified}\n\n${finding.explanation}`,
        severity: markerSeverity(finding.severity),
        source: finding.cwe ?? "agent",
        code: finding.id,
      };
    });
}

/**
 * Evidence spans as dimmer decorations.
 *
 * The sink gets the squiggle; the trail that leads to it gets a subdued
 * highlight, so the two read as different things rather than as five equal
 * warnings. Only evidence for a *selected* finding is passed in -- decorating
 * every finding's evidence at once turns the file into noise.
 */
export function evidenceDecorationsFor(finding: Finding | null, file: string): EditorDecoration[] {
  if (!finding) return [];
  // `evidence` is optional on the wire: it has a server-side default, so the
  // serialised form may omit it entirely.
  return (finding.evidence ?? [])
    .filter((item) => item.span.file === file)
    .map((item) => ({
      range: {
        startLineNumber: item.span.start_line,
        startColumn: item.span.start_column,
        endLineNumber: item.span.end_line,
        endColumn: item.span.end_column,
      },
      options: {
        inlineClassName: `evidence-${item.role}`,
        hoverMessage: { value: `**${item.role}** — ${item.note}` },
      },
    }));
}

/** Per-file counts by severity, for the file tree. */
export function countsByFile(findings: Finding[]): Map<string, Record<SeverityName, number>> {
  const counts = new Map<string, Record<SeverityName, number>>();
  for (const finding of findings) {
    const file = finding.primary.file;
    const bucket =
      counts.get(file) ?? { critical: 0, high: 0, medium: 0, low: 0, info: 0 };
    bucket[finding.severity] += 1;
    counts.set(file, bucket);
  }
  return counts;
}

/** The most severe level present in a bucket, or null if it is empty. */
export function worstSeverity(
  counts: Record<SeverityName, number> | undefined,
): SeverityName | null {
  if (!counts) return null;
  const present = (Object.keys(counts) as SeverityName[]).filter((key) => counts[key] > 0);
  if (present.length === 0) return null;
  return present.sort((a, b) => SEVERITY_RANK[a] - SEVERITY_RANK[b])[0];
}

export function totalCount(counts: Record<SeverityName, number> | undefined): number {
  if (!counts) return 0;
  return Object.values(counts).reduce((sum, n) => sum + n, 0);
}

/** Most severe first, then by position -- the same order the server uses. */
export function sortFindings(findings: Finding[]): Finding[] {
  return [...findings].sort((a, b) => {
    const bySeverity = SEVERITY_RANK[a.severity] - SEVERITY_RANK[b.severity];
    if (bySeverity !== 0) return bySeverity;
    const byFile = a.primary.file.localeCompare(b.primary.file);
    if (byFile !== 0) return byFile;
    return a.primary.start_line - b.primary.start_line;
  });
}
