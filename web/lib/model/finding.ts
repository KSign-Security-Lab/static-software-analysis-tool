import type { Finding as AgentFinding } from "@/lib/agent-schema";
import { buildDecisions, type Decision } from "@/lib/decision";
import type { F2AResult } from "@/lib/types";

/**
 * One finding shape for both engines.
 *
 * The structural line (F2-A over a CPG) and the LLM agent answer the same
 * question about the same code and used to have nothing in common on screen:
 * different pages, different components, different vocabulary. They still run
 * independently -- nothing here couples them -- but once a result exists it is
 * described the same way, so one list, one set of editor markers and one detail
 * panel serve both.
 *
 * This is a view model. Neither backend shape changes.
 */

export type Engine = "structural" | "agent";

export type Severity = "critical" | "high" | "medium" | "low" | "info";

export const SEVERITY_ORDER: Record<Severity, number> = {
  critical: 0,
  high: 1,
  medium: 2,
  low: 3,
  info: 4,
};

export type EvidenceRole = "source" | "propagation" | "sink" | "missing_check" | "context";

export interface Span {
  file: string;
  startLine: number;
  startColumn: number;
  endLine: number;
  endColumn: number;
  excerpt: string;
}

export interface Evidence {
  role: EvidenceRole;
  span: Span;
  note: string;
}

export interface UiFinding {
  id: string;
  engine: Engine;
  severity: Severity;
  title: string;
  cwe: string | null;
  primary: Span;
  explanation: string;
  evidence: Evidence[];
  remediation: string | null;
  /** 0-1. F2-A reports its own confidence; the agent reports the verify pass's. */
  confidence: number;
  /** Agent only: survived the refute pass. Null where the notion does not apply. */
  verified: boolean | null;
  /** The engine's own object, for the detail panel to render natively. */
  raw: Decision | AgentFinding;
}

function span(file: string, line: number, excerpt = ""): Span {
  return { file, startLine: line, startColumn: 1, endLine: line, endColumn: 1, excerpt };
}

function toLine(value: string | number | undefined): number {
  const n = typeof value === "string" ? Number.parseInt(value, 10) : value;
  return Number.isFinite(n) && (n as number) > 0 ? (n as number) : 0;
}

/**
 * F2-A confidence is a 0-1 score, but it is not a severity: the pipeline does
 * not rank findings. Mapping the score is the honest option -- inventing
 * "critical" for something the engine never called critical would be worse.
 */
function severityFromConfidence(confidence: number): Severity {
  if (confidence >= 0.85) return "high";
  if (confidence >= 0.6) return "medium";
  if (confidence > 0) return "low";
  return "info";
}

/** F2-A decisions -> the shared shape. Only vulnerability results become findings. */
export function fromF2A(result: F2AResult | null | undefined, file: string): UiFinding[] {
  if (!result) return [];
  return buildDecisions(result)
    .filter((d) => d.kind === "vuln" && d.hasFinding)
    .map((d) => {
      const sink = d.trace.find((s) => s.role === "sink") ?? d.trace[d.trace.length - 1];
      const evidence: Evidence[] = d.trace.map((step) => ({
        role: step.role === "source" ? "source" : step.role === "sink" ? "sink" : "propagation",
        span: span(step.file || file, step.line),
        note: step.note,
      }));
      for (const check of d.checks) {
        evidence.push({
          role: "missing_check",
          span: span(file, 0),
          note: `${check.id}: ${check.observed ?? check.status}`,
        });
      }

      return {
        id: `f2a:${d.id}`,
        engine: "structural" as const,
        severity: severityFromConfidence(d.confidence),
        title: d.title,
        cwe: d.cwe[0] ?? null,
        primary: span(sink?.file || file, sink?.line ?? 0),
        explanation: d.overview,
        evidence,
        remediation: d.remediation.join("\n") || null,
        confidence: d.confidence,
        verified: null,
        raw: d,
      };
    });
}

/** Agent findings -> the shared shape. Already close; mostly renaming. */
export function fromAgent(findings: AgentFinding[] | null | undefined): UiFinding[] {
  return (findings ?? []).map((f) => ({
    id: `agent:${f.id}`,
    engine: "agent" as const,
    severity: f.severity as Severity,
    title: f.title,
    cwe: f.cwe ?? null,
    primary: {
      file: f.primary.file,
      startLine: f.primary.start_line,
      startColumn: f.primary.start_column,
      endLine: f.primary.end_line,
      endColumn: f.primary.end_column,
      excerpt: f.primary.excerpt,
    },
    explanation: f.explanation,
    evidence: (f.evidence ?? []).map((e) => ({
      role: e.role as EvidenceRole,
      span: {
        file: e.span.file,
        startLine: e.span.start_line,
        startColumn: e.span.start_column,
        endLine: e.span.end_line,
        endColumn: e.span.end_column,
        excerpt: e.span.excerpt,
      },
      note: e.note,
    })),
    remediation: f.remediation ? `${f.remediation.summary}\n\n${f.remediation.detail}` : null,
    confidence: f.confidence,
    verified: f.verified,
    raw: f,
  }));
}

export function sortFindings(findings: UiFinding[]): UiFinding[] {
  return [...findings].sort((a, b) => {
    const bySeverity = SEVERITY_ORDER[a.severity] - SEVERITY_ORDER[b.severity];
    if (bySeverity !== 0) return bySeverity;
    const byFile = a.primary.file.localeCompare(b.primary.file);
    return byFile !== 0 ? byFile : a.primary.startLine - b.primary.startLine;
  });
}

export interface FileCount {
  total: number;
  worst: Severity | null;
}

export function countByFile(findings: UiFinding[]): Map<string, FileCount> {
  const counts = new Map<string, FileCount>();
  for (const f of findings) {
    const current = counts.get(f.primary.file) ?? { total: 0, worst: null };
    current.total += 1;
    if (current.worst === null || SEVERITY_ORDER[f.severity] < SEVERITY_ORDER[current.worst]) {
      current.worst = f.severity;
    }
    counts.set(f.primary.file, current);
  }
  return counts;
}

export const SEVERITY_LABEL: Record<Severity, string> = {
  critical: "치명적",
  high: "높음",
  medium: "보통",
  low: "낮음",
  info: "정보",
};

export const ENGINE_LABEL: Record<Engine, string> = {
  structural: "구조 분석",
  agent: "LLM 에이전트",
};

export const ROLE_LABEL: Record<EvidenceRole, string> = {
  source: "유입",
  propagation: "전파",
  sink: "위험 지점",
  missing_check: "검증",
  context: "참고",
};

/** monaco.MarkerSeverity: Hint=1, Info=2, Warning=4, Error=8. */
export function markerSeverity(severity: Severity): number {
  if (severity === "critical" || severity === "high") return 8;
  if (severity === "medium") return 4;
  if (severity === "low") return 2;
  return 1;
}

export { toLine };
