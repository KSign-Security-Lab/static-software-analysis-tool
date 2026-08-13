import { Network, ScanSearch, ShieldCheck, TerminalSquare, type LucideIcon } from "lucide-react";

/**
 * The four surfaces, declared once.
 *
 * The activity bar, the command palette and the status bar all read this, so
 * a route cannot be added in one place and forgotten in another -- and
 * `carries` names the params that must survive a switch, which is what stops
 * the rail dropping `?run=` on the way past.
 *
 * 트레이스 was a fifth until it turned out not to be a place: it is the other
 * centre tab of 검사, over the same dock, and `carries` brings `centre` along
 * so leaving and coming back keeps the view you were on.
 */

export type PerspectiveId = "agent" | "f2a" | "extract" | "stages";

export interface Perspective {
  id: PerspectiveId;
  href: string;
  label: string;
  note: string;
  icon: LucideIcon;
  /** Search params that follow you into this perspective, if they are set. */
  carries: readonly string[];
  /**
   * What this surface answers, in one sentence.
   *
   * Five tools share one shell and they look alike from the outside -- the
   * same rail, the same four panels. Which question each one answers is the
   * thing an icon cannot say.
   */
  purpose: string;
  /**
   * How to use it, in order. Named after the controls actually on screen, so
   * following it is a matter of reading rather than of guessing.
   */
  steps: readonly string[];
}

export const PERSPECTIVES: readonly Perspective[] = [
  {
    id: "agent",
    href: "/agent",
    label: "검사",
    note: "코드를 올려 취약점을 찾고, 그 판단 과정을 그대로 열어 봅니다",
    icon: ScanSearch,
    carries: ["run", "file", "centre"],
    purpose:
      "이 코드에 취약점이 있는가, 그리고 에이전트는 왜 그렇게 판단했는가 — 결과와 과정을 나란히 봅니다.",
    steps: [
      "왼쪽 탐색기에서 파일을 추가하거나 폴더를 통째로 올립니다. 빈 파일에 붙여넣어도 됩니다.",
      "‘검사 실행’을 누릅니다. 오른쪽에 지금 무엇을 하고 있는지가 표시되고, 결과는 도착하는 대로 쌓입니다.",
      "오른쪽에는 에이전트별 대화가 쌓입니다. 각 줄을 펼치면 그 에이전트에게 보낸 프롬프트와, 부른 도구와 그 결과를 볼 수 있습니다.",
      "아래 ‘문제’에서 항목을 펼치면 그렇게 판단한 근거가 그 자리에 나옵니다.",
      "가운데 ‘에이전트 구조’ 탭은 검사가 지나가는 길입니다. 노드를 누르면 오른쪽 대화가 그 노드의 호출만 남기고, 중단점을 걸면 다음 실행이 거기서 멈춥니다.",
    ],
  },
  {
    id: "f2a",
    href: "/f2a",
    label: "F2-A",
    note: "어떤 요청이 어떤 핸들러로 가는지 정적으로 풀어냅니다",
    icon: ShieldCheck,
    carries: ["sample", "view"],
    purpose: "이 액션을 처리하는 함수는 무엇인가 — 등록·디스패치 흔적을 모아 후보를 고르고, 고른 이유를 남깁니다.",
    steps: [
      "왼쪽 ‘소스’에서 예제를 고르거나, 편집기에 코드를 직접 붙여넣습니다.",
      "‘분석’을 누릅니다. CPG를 만들고 F2-A를 돌리는 데 시간이 조금 걸립니다.",
      "아래 ‘근거’에서 액션별 판정을, 오른쪽에서 그 판정을 뒷받침한 증거 기록을 확인합니다.",
    ],
  },
  {
    id: "extract",
    href: "/extract",
    label: "추출",
    note: "같은 코드를 AST · CFG · DFG · 호출 그래프로 바꿔 봅니다",
    icon: Network,
    carries: ["sample", "view"],
    purpose: "이 코드의 구조는 어떻게 생겼는가 — Joern이 만든 CPG와 파이프라인이 만든 그래프를 나란히 봅니다.",
    steps: [
      "왼쪽 ‘소스’에서 예제를 고르거나 소스·CPG JSON 파일을 열고 ‘분석’을 누릅니다.",
      "가운데 위 선택기로 볼 그래프를 고릅니다. CPG 계열과 파이프라인 계열은 이름이 같아도 다른 산출물입니다.",
      "노드를 누르면 오른쪽에 그 노드의 속성이 그대로 표시됩니다.",
    ],
  },
  {
    id: "stages",
    href: "/extract/stages",
    label: "스테이지",
    note: "파이프라인 단계 하나만 돌려 원본 응답을 봅니다",
    icon: TerminalSquare,
    carries: ["sample", "stage"],
    purpose: "이 단계가 실제로 무엇을 돌려주는가 — 엔드포인트 하나를 그대로 호출해 응답을 날것으로 봅니다.",
    steps: [
      "왼쪽 ‘단계’에서 호출할 엔드포인트를 고릅니다.",
      "편집기에 소스나 CPG JSON을 넣습니다.",
      "‘실행’을 누르면 아래 ‘응답’에 가공하지 않은 결과가 그대로 나옵니다.",
    ],
  },
] as const;

const BY_ID = new Map(PERSPECTIVES.map((p) => [p.id, p]));

export function perspective(id: PerspectiveId): Perspective {
  const found = BY_ID.get(id);
  if (!found) throw new Error(`unknown perspective: ${id}`);
  return found;
}

/**
 * Which perspective a path belongs to.
 *
 * Longest match wins, so `/extract/stages` is 스테이지 rather than the 추출
 * view that merely shares its prefix.
 */
export function perspectiveFor(pathname: string): Perspective | undefined {
  let best: Perspective | undefined;
  for (const p of PERSPECTIVES) {
    if (pathname !== p.href && !pathname.startsWith(`${p.href}/`)) continue;
    if (!best || p.href.length > best.href.length) best = p;
  }
  return best;
}

/** A link into `id`, carrying across whichever of its params are currently set. */
export function hrefFor(id: PerspectiveId, params?: URLSearchParams | null): string {
  const target = perspective(id);
  if (!params) return target.href;

  const carried = new URLSearchParams();
  for (const key of target.carries) {
    const value = params.get(key);
    if (value) carried.set(key, value);
  }
  const query = carried.toString();
  return query ? `${target.href}?${query}` : target.href;
}

/**
 * The 검사 half of the agent surface, as opposed to `/agent/machine`.
 *
 * One surface, two workspaces: one about your code and the problems in it, one
 * about the checker that found them. They share the run, the rail entry and the
 * layout cookie; what differs is which panes are worth having.
 */
export function isInspectSpace(pathname: string): boolean {
  return pathname === "/agent" || pathname === "/agent/";
}
