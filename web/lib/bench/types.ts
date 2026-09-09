export type Stage =
  | "not_located"
  | "misread"
  | "false_flagged"
  | "patch_build_failed"
  | "built_not_fixed"
  | "fixed_tests_broke";

export type Outcome = Stage | "solved" | "awaiting_score" | "harness_error" | "not_run";

export type DatasetKind = "held_out" | "pinned";

export interface Baseline {
  name: string;
  model: string;
  resolved: number | null;
  source: string;
}

export interface Instance {
  id: string;
  project: string;
  cwe: string;
  cve: string;
  outcome: Outcome;
  run_id: string | null;
  config_hash: string | null;
  contaminated: boolean;
  contamination_reason: string;
  matched: "exact" | "family";
  note: string;
}

export type Score =
  | {
      available: true;
      value: number;
      solved: number;
      exact: number;
      harness: number;
      scored: number;
      excluded: number;
      config_hash: string;
      model: string;
    }
  | {
      available: false;
      solved?: number;
      scored?: number;
      excluded?: number;
      harness: number;
      config_hash?: string | null;
      model?: string | null;
      unavailable_reason: string;
    };

export interface Dataset {
  id: string;
  label: string;
  kind: DatasetKind;
  score_label: string;
  note: string;
  total: number;
  stages: Stage[];
  baselines: Baseline[];
  excluded_tracks: { track: string; reason: string }[];
  how_to_run: string;
  baseline_note: string;
  ran_at: number | null;
  split: string;
}

export interface DatasetView {
  dataset: Dataset;
  score: Score;
  instances: Instance[];
  problem: string;
}

export interface DatasetList {
  datasets: Dataset[];
  stages: { id: Stage; label: string }[];
}

export function isComplete(baseline: Baseline): boolean {
  return baseline.resolved !== null && Boolean(baseline.model) && Boolean(baseline.source);
}

export const STAGE_LABEL: Record<Stage, string> = {
  not_located: "위치 못 찾음",
  misread: "찾고 오독",
  false_flagged: "오탐",
  patch_build_failed: "패치 빌드 실패",
  built_not_fixed: "빌드됐으나 미수정",
  fixed_tests_broke: "고쳤으나 테스트 깨짐",
};

export const OUTCOME_LABEL: Record<Outcome, string> = {
  ...STAGE_LABEL,
  solved: "통과",
  awaiting_score: "채점 대기",
  harness_error: "실행 실패",
  not_run: "안 돌림",
};

export const OUTCOME_DOT: Record<Outcome, string> = {
  solved: "bg-ok",
  not_located: "bg-danger",
  misread: "bg-warn",
  false_flagged: "bg-warn",
  patch_build_failed: "bg-danger",
  built_not_fixed: "bg-danger",
  fixed_tests_broke: "bg-warn",
  awaiting_score: "bg-accent",
  harness_error: "bg-line-3",
  not_run: "bg-line-3",
};

export function groupByOutcome(
  instances: Instance[],
  stages: Stage[],
): { outcome: Outcome; label: string; items: Instance[] }[] {
  const order: Outcome[] = [...stages, "solved", "awaiting_score", "harness_error", "not_run"];
  const groups = new Map<Outcome, Instance[]>();
  for (const instance of instances) {
    groups.set(instance.outcome, [...(groups.get(instance.outcome) ?? []), instance]);
  }
  return order
    .filter((outcome) => (groups.get(outcome) ?? []).length > 0)
    .map((outcome) => ({ outcome, label: OUTCOME_LABEL[outcome], items: groups.get(outcome) ?? [] }));
}

export interface SweepStatus {
  running: boolean;
  pid: number | null;
  started_at: number | null;
  instance: string | null;
  position: number | null;
  of: number | null;
  log: string[];
  log_path: string;
  split: string | null;
  chose: string[];
}

export interface SweepOrder {
  instances: string[];
  split: string;
  force: boolean;
}
