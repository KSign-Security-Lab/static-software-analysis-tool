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
  /**
   * The unit this was found in, for the agent engine.
   *
   * Carried because it is the join to the knowledge graph: a node's id *is* a
   * chunk id, which is what lets the structure map be painted with severity
   * rather than being a picture beside the findings. The structural engine has
   * no equivalent, so it is null there.
   */
  chunkId: string | null;
  severity: Severity;
  title: string;
  cwe: string | null;
  primary: Span;
  explanation: string;
  evidence: Evidence[];
  remediation: string | null;
  /**
   * The code that replaces `primary`, when the run produced any.
   *
   * Separate from `remediation`, which is prose. This is what the editor's quick
   * fix splices and what the apply endpoint writes; a finding with advice and no
   * replacement must not be offered as something that can be fixed.
   */
  replacement: string | null;
  /**
   * The fix as a patch, when the agent could name one for these exact lines.
   *
   * Computed server-side from the resolved span and the replacement, so what is
   * shown is what applying would do rather than something the model wrote about
   * it. Null means it said it could not fix this in place -- which is an answer,
   * not a gap.
   */
  diff: string | null;
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
        chunkId: null,
        severity: severityFromConfidence(d.confidence),
        title: d.title,
        cwe: d.cwe[0] ?? null,
        primary: span(sink?.file || file, sink?.line ?? 0),
        explanation: d.overview,
        evidence,
        remediation: d.remediation.join("\n") || null,
        // F2-A reports advice, never code.
        replacement: null,
        diff: null,
        confidence: d.confidence,
        verified: null,
        raw: d,
      };
    });
}

/** Agent findings -> the shared shape. Already close; mostly renaming. */
/**
 * The id the producing engine knows a finding by.
 *
 * View-model ids are prefixed with their engine so that two engines' findings can
 * share one list without colliding -- and anything talking *back* to an engine
 * has to take the prefix off again. It did not, so both `이대로 고치기` and
 * `고칠 코드 만들기` posted `agent:0a6b…` to an API that only knows `0a6b…` and
 * got `unknown finding` every time.
 *
 * This is the second time the prefix has been missed in a round trip; the first
 * was `?finding=` matching nothing, silently. One function now, so the next
 * caller has something to reach for.
 */
export function wireId(id: string): string {
  const at = id.indexOf(":");
  return at === -1 ? id : id.slice(at + 1);
}

export function fromAgent(findings: AgentFinding[] | null | undefined): UiFinding[] {
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

/**
 * The same tally, keyed by unit rather than file.
 *
 * What paints the structure map: node ids are chunk ids, so this joins
 * straight onto them.
 */
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

/**
 * What verification made of a claim.
 *
 * Three states, and the third was invisible. A finding over
 * `max_verify_per_chunk` is stored `verified: false, confidence 0.3` -- never put
 * to a verifier at all -- and the list showed it exactly like one that had been
 * checked and held. Neither confirmed nor refuted is its own answer and now says
 * so.
 *
 * The words are compounds rather than sentences. `반박을 견딤` was a literal
 * rendering of "withstood refutation": accurate about the mechanism, and not
 * something anybody says.
 */
export type Standing = "confirmed" | "candidate";

/**
 * Null is not a third state, it is no state: F2-A findings never go near a
 * verifier, so a badge saying anything about verification would be inventing a
 * step that does not exist for them.
 */
export function standingOf(finding: { verified: boolean | null }): Standing | null {
  if (finding.verified === null) return null;
  return finding.verified ? "confirmed" : "candidate";
}

export const STANDING_LABEL: Record<Standing, string> = {
  confirmed: "취약 확인",
  candidate: "취약 후보",
};

/** Refuted claims never reach a report, so this only ever appears in the record. */
export const REFUTED_LABEL = "취약 미검출";

export const SEVERITY_LABEL: Record<Severity, string> = {
  critical: "치명적",
  high: "높음",
  medium: "보통",
  low: "낮음",
  info: "정보",
};

/**
 * Severity colour as Tailwind classes.
 *
 * Five components carried their own byte-identical copy of the dot map. The
 * index type stays `string` because not every caller has narrowed its severity
 * yet -- `KnowledgeNodeData.severity` is `string | null` -- while `satisfies`
 * still requires every severity to appear, so adding one cannot be missed here.
 */
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

/**
 * Evidence role as a left-border colour.
 *
 * For `EvidenceRole` only. `features/f2a/EvidenceReport.tsx` draws the same kind
 * of stripe but over `TraceStep.role` from `lib/decision`, whose vocabulary is
 * `source | step | sink` -- a different set, so it keeps its own map rather than
 * sharing one that cannot describe `step`.
 */
export const ROLE_TONE: Record<string, string> = {
  source: "border-l-warn",
  propagation: "border-l-line-3",
  sink: "border-l-danger",
  missing_check: "border-l-alt",
  context: "border-l-line-2",
} satisfies Record<EvidenceRole, string>;

/** monaco.MarkerSeverity: Hint=1, Info=2, Warning=4, Error=8. */
export function markerSeverity(severity: Severity): number {
  if (severity === "critical" || severity === "high") return 8;
  if (severity === "medium") return 4;
  if (severity === "low") return 2;
  return 1;
}

export { toLine };
