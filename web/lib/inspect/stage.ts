import type { RunLive } from "@/lib/run/reduce";
import type { RunSummary } from "@/lib/api/types";

export type Stage = "intake" | "results";

export interface StageInput {
  run: RunSummary | undefined;
  live: RunLive;
  hasFindings: boolean;
}

export function stageOf({ run, live, hasFindings }: StageInput): Stage {
  if (!run) return "intake";

  if (live.active && !live.finished) return "results";

  switch (run.status) {
    case "created":
    case "indexing":
      return "intake";
    case "indexed":
      return "intake";
    case "inspecting":
      return "results";
    case "interrupted":
    case "cancelled":
    case "done":
      return "results";
    case "failed":
      return hasFindings ? "results" : "intake";
    default:
      return "intake";
  }
}

export function isScanning({ run, live }: Pick<StageInput, "run" | "live">): boolean {
  if (!live.attached && run && run.status !== "inspecting") return false;
  if (live.active && !live.finished) return true;
  return run?.status === "inspecting";
}

export function isStopped({ run, live }: Pick<StageInput, "run" | "live">): boolean {
  if (isScanning({ run, live })) return false;
  return run?.status === "cancelled" || run?.status === "interrupted";
}

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
  if (live.cancelling) return "중단하는 중";
  if (live.interrupted) return "중단점에서 멈춤";
  for (const node of ["verify", "reduce", "gather", "locate"]) {
    if (live.running.includes(node)) return PHASE_LABEL[node];
  }
  const first = live.running.find((node) => PHASE_LABEL[node]);
  return first ? PHASE_LABEL[first] : "준비 중";
}

export interface Progress {
  done: number;
  total: number;
  fraction: number | null;
}

export function progressOf(live: RunLive): Progress {
  const chunk = live.chunk;
  if (!chunk || chunk.total <= 0) return { done: 0, total: 0, fraction: null };
  const done = Math.max(0, chunk.total - chunk.remaining);
  return { done, total: chunk.total, fraction: Math.min(1, done / chunk.total) };
}
