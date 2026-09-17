import type { Finding as AgentFinding, Reach as AgentReach } from "@/lib/agent-schema";
import { buildDecisions, type Decision } from "@/lib/decision";
import type { F2AResult } from "@/lib/types";

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
  chunkId: string | null;
  severity: Severity;
  title: string;
  cwe: string | null;
  primary: Span;
  explanation: string;
  evidence: Evidence[];
  remediation: string | null;
  replacement: string | null;
  diff: string | null;
  chunkIds: string[];
  mergedIds: string[];
  confidence: number;
  verified: boolean | null;
  reach: AgentReach | null;
  raw: Decision | AgentFinding;
}

function span(file: string, line: number, excerpt = ""): Span {
  return { file, startLine: line, startColumn: 1, endLine: line, endColumn: 1, excerpt };
}

function toLine(value: string | number | undefined): number {
  const n = typeof value === "string" ? Number.parseInt(value, 10) : value;
  return Number.isFinite(n) && (n as number) > 0 ? (n as number) : 0;
}

function severityFromConfidence(confidence: number): Severity {
  if (confidence >= 0.85) return "high";
  if (confidence >= 0.6) return "medium";
  if (confidence > 0) return "low";
  return "info";
}

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
        chunkId: null,
        severity: severityFromConfidence(d.confidence),
        title: d.title,
        cwe: d.cwe[0] ?? null,
        primary: span(sink?.file || file, sink?.line ?? 0),
        explanation: d.overview,
        evidence,
        remediation: d.remediation.join("\n") || null,
        replacement: null,
        diff: null,
        chunkIds: [],
        mergedIds: [],
        confidence: d.confidence,
        verified: null,
        reach: null,
        raw: d,
      };
    });
}

export function wireId(id: string): string {
  const at = id.indexOf(":");
  return at === -1 ? id : id.slice(at + 1);
}

export function fromAgent(findings: AgentFinding[] | null | undefined): UiFinding[] {
  return mergeFindings(eachAgent(findings));
}

function eachAgent(findings: AgentFinding[] | null | undefined): UiFinding[] {
  return (findings ?? []).map((f) => ({
    id: `agent:${f.id}`,
    engine: "agent" as const,
    chunkId: f.chunk_id,
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
    replacement: f.remediation?.replacement ?? null,
    diff: f.remediation?.diff ?? null,
    chunkIds: f.chunk_id ? [f.chunk_id] : [],
    mergedIds: [],
    confidence: f.confidence,
    verified: f.verified,
    reach: f.reach ?? null,
    raw: f,
  }));
}

function claimKey(finding: UiFinding): string {
  return [finding.title, finding.cwe ?? "", finding.primary.file, finding.primary.startLine].join("\u0000");
}

function richness(finding: UiFinding): number {
  return (
    (finding.diff ? 8 : 0) +
    (finding.remediation ? 4 : 0) +
    Math.min(finding.evidence.length, 3) +
    finding.confidence
  );
}

export function mergeFindings(findings: UiFinding[]): UiFinding[] {
  const groups = new Map<string, UiFinding[]>();
  for (const finding of findings) {
    const key = claimKey(finding);
    const found = groups.get(key);
    if (found) found.push(finding);
    else groups.set(key, [finding]);
  }

  return [...groups.values()].map((group) => {
    if (group.length === 1) return group[0];

    const best = group.reduce((a, b) => (richness(b) > richness(a) ? b : a));
    return {
      ...best,
      chunkIds: [...new Set(group.flatMap((each) => each.chunkIds))],
      mergedIds: group.filter((each) => each.id !== best.id).map((each) => each.id),
    };
  });
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

export function countByChunk(findings: UiFinding[]): Map<string, FileCount> {
  const counts = new Map<string, FileCount>();
  for (const f of findings) {
    if (!f.chunkId) continue;
    const current = counts.get(f.chunkId) ?? { total: 0, worst: null };
    current.total += 1;
    if (current.worst === null || SEVERITY_ORDER[f.severity] < SEVERITY_ORDER[current.worst]) {
      current.worst = f.severity;
    }
    counts.set(f.chunkId, current);
  }
  return counts;
}

export type Standing = "confirmed" | "candidate";

export function standingOf(finding: { verified: boolean | null }): Standing | null {
  if (finding.verified === null) return null;
  return finding.verified ? "confirmed" : "candidate";
}

export const STANDING_LABEL: Record<Standing, string> = {
  confirmed: "취약 확인",
  candidate: "취약 후보",
};

export const REFUTED_LABEL = "취약 미검출";

export type Liveness = "live" | "unreferenced" | "unreachable" | "excluded" | "unknown";

export function livenessOf(finding: { reach: AgentReach | null }): Liveness | null {
  return (finding.reach?.state as Liveness | undefined) ?? null;
}

export const LIVENESS_LABEL: Record<Liveness, string> = {
  live: "실행 경로",
  unreferenced: "참조 없음",
  unreachable: "도달 불가",
  excluded: "시험·예제 코드",
  unknown: "판단 불가",
};

export const FOLDED_LIVENESS: readonly Liveness[] = ["unreachable", "excluded"];

export function isFolded(finding: { reach: AgentReach | null }): boolean {
  const liveness = livenessOf(finding);
  return liveness !== null && FOLDED_LIVENESS.includes(liveness);
}

export const SEVERITY_LABEL: Record<Severity, string> = {
  critical: "치명적",
  high: "높음",
  medium: "보통",
  low: "낮음",
  info: "정보",
};

export const SEVERITY_DOT: Record<string, string> = {
  critical: "bg-sev-critical",
  high: "bg-sev-high",
  medium: "bg-sev-medium",
  low: "bg-sev-low",
  info: "bg-sev-info",
} satisfies Record<Severity, string>;

export const SEVERITY_TEXT: Record<string, string> = {
  critical: "text-sev-critical",
  high: "text-sev-high",
  medium: "text-sev-medium",
  low: "text-sev-low",
  info: "text-sev-info",
} satisfies Record<Severity, string>;

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

export const ROLE_TONE: Record<string, string> = {
  source: "border-l-warn",
  propagation: "border-l-line-3",
  sink: "border-l-danger",
  missing_check: "border-l-alt",
  context: "border-l-line-2",
} satisfies Record<EvidenceRole, string>;

export function markerSeverity(severity: Severity): number {
  if (severity === "critical" || severity === "high") return 8;
  if (severity === "medium") return 4;
  if (severity === "low") return 2;
  return 1;
}

export { toLine };
