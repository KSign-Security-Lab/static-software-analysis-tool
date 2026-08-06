import { Network, ScanSearch, ShieldCheck, TerminalSquare, Waypoints, type LucideIcon } from "lucide-react";

/**
 * The five surfaces, declared once.
 *
 * The activity bar, the command palette and the status bar all read this, so
 * a route cannot be added in one place and forgotten in another -- and `href`
 * carries the params that must survive a switch. Today only one place does
 * that, by hand, so navigating via the rail loses `?run=` and the trace view
 * silently forgets which run you were looking at.
 */

export type PerspectiveId = "agent" | "trace" | "f2a" | "extract" | "stages";

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
    note: "코드를 올리고 LLM 에이전트로 취약점을 찾습니다",
    icon: ScanSearch,
    carries: ["run", "file"],
    purpose: "이 코드에 취약점이 있는가 — 에이전트가 청크 단위로 읽고, 찾은 것마다 근거를 남깁니다.",
    steps: [
      "왼쪽 탐색기에서 파일을 추가하거나 폴더를 통째로 올립니다. 빈 파일에 붙여넣어도 됩니다.",
      "오른쪽 위 ‘검사 실행’을 누릅니다. 진행 상황은 맨 아래 상태 표시줄에 나옵니다.",
      "아래 ‘문제’ 탭에서 발견된 결과를 고르면 편집기가 해당 줄로 이동하고, 오른쪽에 판단 근거가 표시됩니다.",
    ],
  },
  {
    id: "trace",
    href: "/agent/trace",
    label: "트레이스",
    note: "검사가 그 답에 이른 과정을 열어 보고, 고쳐서 다시 돌립니다",
    icon: Waypoints,
    carries: ["run", "span", "node", "cp"],
    purpose: "에이전트가 왜 그렇게 판단했는가 — 호출 하나하나와 각 단계의 상태를 그대로 보여줍니다.",
    steps: [
      "‘중단점’에서 멈출 노드를 고른 뒤 검사를 실행하면 그 앞뒤에서 멈춥니다.",
      "아래 ‘호출 기록’에서 모델 호출을 고르면 오른쪽에서 프롬프트를 읽고, 고쳐서 ‘다시 실행’해 결과를 비교할 수 있습니다.",
      "‘상태 단계’에서는 어느 지점이든 골라 상태를 고친 뒤 갈라 실행할 수 있습니다. 원래 갈래는 그대로 남습니다.",
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
 * Longest match wins, so `/agent/trace` is the trace view rather than the
 * inspect view that merely shares its prefix.
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
