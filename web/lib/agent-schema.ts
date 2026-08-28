// GENERATED FILE -- DO NOT EDIT.
//
// The wire schema is defined in packages/agent/src/agent/schema.py. This file
// is generated from it by `python -m agent.schema_ts --write`, and
// packages/agent/tests/test_schema.py fails if the two drift apart.

export interface Evidence {
  role: "source" | "propagation" | "sink" | "missing_check" | "context";
  span: Span;
  note: string;
}

export interface Finding {
  schema_version?: "1";
  /** Content-derived and stable across runs, so two reports can be diffed. */
  id: string;
  chunk_id: string;
  severity: "critical" | "high" | "medium" | "low" | "info";
  confidence: number;
  title: string;
  cwe?: string | null;
  /** The span that gets the squiggle. */
  primary: Span;
  explanation: string;
  evidence?: Evidence[];
  remediation: Remediation;
  /** Survived the adversarial refute pass. */
  verified: boolean;
  lens?: "memory" | "injection" | "access" | "crypto" | "logic" | null;
}

export interface Remediation {
  summary: string;
  detail: string;
  diff?: string | null;
  replacement?: string | null;
}

export interface RunStats {
  files_indexed?: number;
  files_skipped?: number;
  chunks_total?: number;
  chunks_inspected?: number;
  chunks_cached?: number;
  triaged_out?: number;
  regions?: number;
  candidates?: number;
  dropped_unlocatable?: number;
  refuted?: number;
  failed?: number;
}

export interface Span {
  file: string;
  start_line: number;
  start_column: number;
  end_line: number;
  end_column: number;
  /** The text actually at this range, read from disk -- never from the model. */
  excerpt: string;
}

export interface Report {
  schema_version?: "1";
  run_id: string;
  findings?: Finding[];
  stats?: RunStats;
}

export const SEVERITIES = ["critical", "high", "medium", "low", "info"] as const;

export type SeverityName = (typeof SEVERITIES)[number];

/** Rank for sorting: lower is more severe. Mirrors SEVERITY_ORDER in schema.py. */
export const SEVERITY_RANK: Record<SeverityName, number> = {
  critical: 0,
  high: 1,
  medium: 2,
  low: 3,
  info: 4,
};

