import type { RunSummary } from "@/lib/api/types";

/**
 * What to offer for a run that already holds the code you just uploaded.
 *
 * The cross-run cache makes re-scanning an unchanged tree free, so the useful
 * question is not "shall I scan this" but "what do you want with the one that
 * already did". And the answer depends on how that earlier run ended: a finished
 * one has results to open, a half-done one has work to carry on, and one that was
 * never started has nothing yet but a tree.
 *
 * Pure, because it is a small state machine over `RunStatus` and getting it wrong
 * means offering to resume something complete or to open something empty.
 */

export type DuplicateAction =
  /** It finished. Open what it found. */
  | "open"
  /** It stopped part-way. Carry on -- only the unread units cost anything. */
  | "resume"
  /** It is parked at a breakpoint, which is a different endpoint. */
  | "unpark"
  /** It has a tree and has never been scanned. */
  | "start"
  /** It is running right now. Watch it rather than starting anything. */
  | "watch";

export interface Duplicate {
  action: DuplicateAction;
  /** The primary button's label. */
  label: string;
  /** Why this is the offer, in one line, for under the button. */
  note: string;
}

/**
 * `findings` is undefined until a run has produced a report, so "finished with
 * nothing" and "never finished" are told apart by `status`, never by the count.
 */
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
      // `created`, `indexing`, `indexed`: a tree with no answer yet.
      return {
        action: "start",
        label: "그 검사 시작",
        note: "올라와 있지만 아직 검사하지 않은 코드입니다.",
      };
  }
}

/**
 * How useful each kind of match is, most useful first.
 *
 * Newest is not most useful, and the difference showed up the moment this ran
 * against real history: the most recent match was a tree somebody had uploaded
 * and never scanned, so the dialog offered `그 검사 시작` while two finished runs
 * with actual findings sat behind it. The question is "what do you want with the
 * code you already have", and an answer beats another empty upload.
 */
const USEFULNESS: Record<DuplicateAction, number> = {
  // It is done and has results.
  open: 0,
  // It is running, so an answer is coming for free.
  watch: 1,
  // It stopped part-way, so most of the work is already paid for.
  resume: 2,
  unpark: 3,
  // It has a tree and nothing else, which is what the reader already has.
  start: 4,
};

/**
 * The match worth offering, out of everything that shares this tree.
 *
 * Ranked by what it can do for the reader, and only then by recency -- two
 * finished runs of the same code are interchangeable, so the newer one wins.
 */
export function bestMatch(matches: readonly RunSummary[]): RunSummary | undefined {
  return [...matches].sort((a, b) => {
    const rank = USEFULNESS[duplicateOf(a).action] - USEFULNESS[duplicateOf(b).action];
    return rank !== 0 ? rank : (b.updated_at ?? 0) - (a.updated_at ?? 0);
  })[0];
}

/**
 * How much of the earlier run is worth saying beside the offer.
 *
 * Deliberately not the finding count alone: "0건" reads as "this code is clean"
 * when the run may simply never have got there, and that is exactly the
 * confusion the status is for.
 */
export function summarise(run: RunSummary): string {
  const parts: string[] = [`파일 ${run.file_count}개`];
  if (run.status === "done" && typeof run.findings === "number") {
    parts.push(run.findings > 0 ? `${run.findings}건 발견` : "발견된 것 없음");
  }
  const stats = run.index;
  if (stats?.chunks) parts.push(`단위 ${stats.chunks}개`);
  return parts.join(" · ");
}
