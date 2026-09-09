import type { RunSummary } from "@/lib/api/types";

export type DuplicateAction =
  | "open"
  | "resume"
  | "unpark"
  | "start"
  | "watch";

export interface Duplicate {
  action: DuplicateAction;
  label: string;
  note: string;
}

export function duplicateOf(run: RunSummary): Duplicate {
  switch (run.status) {
    case "done":
      return {
        action: "open",
        label: "그 결과 열기",
        note: "이미 끝난 검사입니다. 결과를 그대로 볼 수 있습니다.",
      };
    case "inspecting":
      return {
        action: "watch",
        label: "진행 중인 검사 보기",
        note: "지금 돌고 있습니다. 새로 시작하면 같은 일을 두 번 하게 됩니다.",
      };
    case "interrupted":
      return {
        action: "unpark",
        label: "이어서 검사",
        note: "중단점에 멈춰 있습니다. 멈춘 자리에서 이어 갑니다.",
      };
    case "cancelled":
    case "failed":
      return {
        action: "resume",
        label: "이어서 검사",
        note: "끝까지 가지 못한 검사입니다. 이미 읽은 단위는 건너뛰고 남은 것만 읽습니다.",
      };
    default:
      return {
        action: "start",
        label: "그 검사 시작",
        note: "올라와 있지만 아직 검사하지 않은 코드입니다.",
      };
  }
}

const USEFULNESS: Record<DuplicateAction, number> = {
  open: 0,
  watch: 1,
  resume: 2,
  unpark: 3,
  start: 4,
};

export function bestMatch(matches: readonly RunSummary[]): RunSummary | undefined {
  return [...matches].sort((a, b) => {
    const rank = USEFULNESS[duplicateOf(a).action] - USEFULNESS[duplicateOf(b).action];
    return rank !== 0 ? rank : (b.updated_at ?? 0) - (a.updated_at ?? 0);
  })[0];
}

export function summarise(run: RunSummary): string {
  const parts: string[] = [`파일 ${run.file_count}개`];
  if (run.status === "done" && typeof run.findings === "number") {
    parts.push(run.findings > 0 ? `${run.findings}건 발견` : "발견된 것 없음");
  }
  const stats = run.index;
  if (stats?.chunks) parts.push(`단위 ${stats.chunks}개`);
  return parts.join(" · ");
}
