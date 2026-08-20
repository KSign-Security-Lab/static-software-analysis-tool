import type { RunLive } from "@/lib/run/reduce";
import type { RunSummary } from "@/lib/api/types";

/**
 * Which of the three screens 검사 is on.
 *
 * One route, three states, and the state is derived rather than stored: a stage
 * held in React would be a second source of truth next to the run's own status,
 * and the two would disagree exactly when it mattered -- a reload mid-scan, a
 * shared `?run=` link, a run this tab did not start.
 *
 * Pure so the transitions are testable without a browser. The awkward cases are
 * all here rather than spread across effects: a run that is inspecting but whose
 * stream this tab has not attached to yet, a run that failed after producing
 * findings, and a run parked at a breakpoint.
 */

export type Stage = "intake" | "scanning" | "results";

export interface StageInput {
  run: RunSummary | undefined;
  live: RunLive;
  /** Whether the report has any findings yet, from the findings query. */
  hasFindings: boolean;
}

export function stageOf({ run, live, hasFindings }: StageInput): Stage {
  // No run at all: nothing has been given to the tool yet.
  if (!run) return "intake";

  // The stream is authoritative while it is open, because it is ahead of the
  // row: `run_finished` arrives before the status column is re-read.
  if (live.active && !live.finished) return "scanning";

  switch (run.status) {
    case "created":
    case "indexing":
      // Uploaded and still being read. Intake owns this: it is the screen with
      // somewhere to put "reading 1,204 files".
      return "intake";
    case "indexed":
      // Indexed and never started. Intake, because the button to start is there.
      return "intake";
    case "inspecting":
      return "scanning";
    case "interrupted":
      // Parked. Findings so far are real and worth reading, so this is results
      // rather than a third kind of progress screen.
      return hasFindings ? "results" : "scanning";
    case "done":
      return "results";
    case "failed":
      // A run that died having already reported something still has something
      // to show. One that died with nothing has only the error, and the place
      // that renders an error next to a retry is intake.
      return hasFindings ? "results" : "intake";
    default:
      return "intake";
  }
}

/**
 * A sentence for where the scan is, or null when nothing is running.
 *
 * The graph's node names are the honest answer to "what is it doing" and they
 * are also jargon (`triage`, `scout`, `reduce`), so they are translated once,
 * here, rather than leaking into the progress screen.
 */
const PHASE_LABEL: Record<string, string> = {
  plan: "다음에 읽을 단위를 고르는 중",
  replan: "계획을 다시 세우는 중",
  context: "주변 코드를 모으는 중",
  triage: "볼 만한 단위인지 가리는 중",
  scout: "어느 부분을 읽을지 좁히는 중",
  memory: "메모리 문제를 찾는 중",
  injection: "주입 문제를 찾는 중",
  access: "권한 문제를 찾는 중",
  crypto: "암호 사용을 보는 중",
  logic: "논리 결함을 찾는 중",
  skip: "건너뛰는 중",
  locate: "지적한 위치를 소스에서 찾는 중",
  gather: "근거를 모으는 중",
  verify: "반박해 보는 중",
  reduce: "결과를 정리하는 중",
};

export function phaseOf(live: RunLive): string | null {
  if (!live.active || live.finished) return null;
  if (live.interrupted) return "중단점에서 멈춤";
  // Several nodes genuinely run at once -- a wave screens in parallel. The
  // furthest-along one reads better than a list, and the list is on the graph.
  for (const node of ["verify", "reduce", "gather", "locate"]) {
    if (live.running.includes(node)) return PHASE_LABEL[node];
  }
  const first = live.running.find((node) => PHASE_LABEL[node]);
  return first ? PHASE_LABEL[first] : "준비 중";
}

export interface Progress {
  done: number;
  total: number;
  /** 0-1, or null when the total is not known yet. */
  fraction: number | null;
}

/**
 * How much of the tree has been read.
 *
 * From the chunk counter on the stream rather than from files: a file is several
 * units and nothing on the wire says how many, so a per-file bar would stall at
 * whatever fraction the first file happened to be.
 */
export function progressOf(live: RunLive): Progress {
  const chunk = live.chunk;
  if (!chunk || chunk.total <= 0) return { done: 0, total: 0, fraction: null };
  const done = Math.max(0, chunk.total - chunk.remaining);
  return { done, total: chunk.total, fraction: Math.min(1, done / chunk.total) };
}
