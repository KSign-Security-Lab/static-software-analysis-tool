/**
 * What the benchmark surface reads. Mirrors `api/bench.py`.
 *
 * The one thing the types enforce that prose cannot: a `Score` is a union, not
 * a number with a flag beside it. `available: false` has no `value` at all, so
 * a component cannot render a figure it was never given -- the compiler
 * refuses before a reviewer has to notice.
 */

/** Where a run broke, in the order it would break. */
export type Stage =
  | "not_located"
  | "misread"
  | "false_flagged"
  | "patch_build_failed"
  | "built_not_fixed"
  | "fixed_tests_broke";

export type Outcome = Stage | "solved" | "awaiting_score" | "harness_error" | "not_run";

/**
 * `held_out` is a public benchmark we do not touch; `pinned` is the corpus the
 * tuner scores every config proposal against. The kind is what stops the two
 * ever being averaged, so it travels with the dataset rather than being
 * inferred from its id.
 */
export type DatasetKind = "held_out" | "pinned";

export interface Baseline {
  name: string;
  /** Empty when not recorded. A baseline without it is not a comparison. */
  model: string;
  /** Null when not recorded, which is not the same as zero. */
  resolved: number | null;
  /** A paper or a repository. A category is not a citation. */
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
  /** `exact` or `family` -- see CWE_FAMILIES in api/bench.py. */
  matched: "exact" | "family";
  note: string;
}

/**
 * A number, or a stated refusal.
 *
 * Modelled as a union so the unavailable case cannot carry a value. The
 * alternative -- `value: number | null` beside `available: boolean` -- lets a
 * component read the number and forget the flag, which is exactly the failure
 * this surface exists to prevent.
 */
export type Score =
  | {
      available: true;
      value: number;
      solved: number;
      /** Of `solved`, how many named the exact CWE rather than a sibling. */
      exact: number;
      /** Never scored: the harness failed before the agent had an opinion. */
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
  /** Never the same word for both kinds. */
  score_label: string;
  note: string;
  total: number;
  stages: Stage[];
  baselines: Baseline[];
  excluded_tracks: { track: string; reason: string }[];
  how_to_run: string;
  baseline_note: string;
  ran_at: number | null;
  /** Which SEC-bench split this reads; empty for the corpus, which has none. */
  split: string;
}

export interface DatasetView {
  dataset: Dataset;
  score: Score;
  instances: Instance[];
}

export interface DatasetList {
  datasets: Dataset[];
  stages: { id: Stage; label: string }[];
}

/** A baseline is shown as a figure only when all three parts are there. */
export function isComplete(baseline: Baseline): boolean {
  return baseline.resolved !== null && Boolean(baseline.model) && Boolean(baseline.source);
}

/** Korean labels, so a stage id never reaches the screen. */
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

/**
 * The dot beside a row. `solved` is the only green one; every stage is a
 * failure and reads as one, and `not_run` is absent rather than bad.
 */
export const OUTCOME_DOT: Record<Outcome, string> = {
  solved: "bg-ok",
  not_located: "bg-danger",
  misread: "bg-warn",
  false_flagged: "bg-warn",
  patch_build_failed: "bg-danger",
  built_not_fixed: "bg-danger",
  fixed_tests_broke: "bg-warn",
  // Work in flight, not a verdict: the same neutral as not-run.
  awaiting_score: "bg-accent",
  // Ours, not the agent's. Never scored, always shown.
  harness_error: "bg-line-3",
  not_run: "bg-line-3",
};

/**
 * Instances grouped by outcome, in the dataset's declared stage order.
 *
 * Failures first and `solved` last, because the page leads with where it broke.
 * Only the stages this dataset can reach get a group -- a dataset with no build
 * step showing an empty 패치 빌드 실패 would read as "we never fail that way"
 * when the truth is "we never test that way".
 */
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

/**
 * What the sweep is doing, read off disk rather than held in the API.
 *
 * A run started here outlives the page that started it -- its own session, its
 * own process group, its own log -- so this is the same answer in every browser
 * and after every restart. Coming back two days later and finding the panel
 * still tracking the run is the whole point of it being a file.
 */
export interface SweepStatus {
  running: boolean;
  pid: number | null;
  started_at: number | null;
  /** The instance it is on, when it is on one. */
  instance: string | null;
  position: number | null;
  of: number | null;
  log: string[];
  log_path: string;
  /** What the running sweep was told to do, so a browser that did not start it
      can still say what it is. */
  split: string | null;
  chose: string[];
}

/** What to run: a selection, or the whole split when empty. */
export interface SweepOrder {
  instances: string[];
  split: string;
  /** Redo instances that already have a result. */
  force: boolean;
}
