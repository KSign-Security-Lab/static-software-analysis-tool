import { Network, ScanSearch, ShieldCheck, TerminalSquare, type LucideIcon } from "lucide-react";

/**
 * The four surfaces, declared once.
 *
 * The activity bar and the title bar both read this, so a route cannot be
 * added in one place and forgotten in another -- and `carries` names the
 * params that must survive a switch, which is what stops the rail dropping
 * `?run=` on the way past.
 *
 * 트레이스 was a fifth until it turned out not to be a place. What it held is
 * spread across 검사 now: the pipeline drawing is the top of the right column and
 * the call record is the bottom panel's list. It was briefly a full-window
 * overlay, which had the width and covered the editor -- and the code is what all
 * of it is talking about, so hiding the code to explain the code was the wrong
 * trade.
 *
 * Nothing about that is carried between surfaces. An earlier version carried
 * `centre` with a comment claiming a round trip preserved it, which it never
 * could: `hrefFor` copies from the params it is handed, and the hop out drops
 * whatever the destination does not carry.
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
   * The panes this surface actually has.
   *
   * The title bar offered a fold for all three everywhere, so on 스테이지 --
   * which has neither a bottom panel nor an inspector -- two of the three
   * buttons unfolded a pane whose only content was a sentence explaining that
   * this screen does not have one. A control that reveals its own apology.
   *
   * `defaultLayoutFor` in layout-cookie.ts sizes the absent ones to 0; this is
   * the same fact said where the chrome can read it.
   */
  panes: readonly ("side" | "dock" | "inspector")[];
  /**
   * Whether this surface wants the title bar above it.
   *
   * 검사 does not. The bar was `SSAT │ 검사 │ 1,270px of nothing │ 사용법 ▣▣▣`
   * at 1600, with a second 36px run strip under it, and between them they cost
   * 72px of permanent chrome for information that is transient (the phase, the
   * coverage), post-hoc (tokens, duration) or pressed once a run (검사 실행,
   * the run selector). Moving those pieces around never helped because none of
   * them wanted to be permanent; they are inside the regions that use them now.
   *
   * The rail carries what is genuinely global, so nothing is lost -- see
   * `ActivityBar`'s foot.
   */
  chrome: boolean;
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
    carries: ["run", "file"],
    // No dock. The findings it held are the navigator's 문제 list, and the tool
    // calls it interleaved with them are steps in a finding's 판단 과정.
    panes: ["side", "inspector"],
    chrome: false,
    purpose:
      "이 코드에 취약점이 있는가, 그리고 에이전트는 왜 그렇게 판단했는가 — 결과와 과정을 나란히 봅니다.",
    steps: [
      "왼쪽 ‘탐색기’에 파일을 추가하거나, 가운데 편집기에 폴더를 끌어다 놓습니다. 코드를 그대로 붙여넣어도 됩니다.",
      "맨 위 ‘검사 실행’을 누릅니다. 고친 파일은 먼저 저장되고, 그 줄에 지금 어디까지 왔는지가 계속 표시됩니다.",
      "아래 ‘실행’의 ‘문제’ 에 찾은 것이 쌓입니다. 한 줄을 고르면 가운데 편집기가 그 줄로 가고, 오른쪽 아래 ‘상세’ 에 판단·근거·고치는 방법·판단 과정이 나옵니다. 패치가 있으면 그 자리에서 적용할 수 있습니다.",
      "같은 목록을 ‘전체’ 나 ‘도구’ 로 넓히면 에이전트가 한 호출이 전부 보입니다. 호출을 고르면 보낸 지시와 답변과 부른 도구가 ‘상세’ 에 나옵니다. 호출은 특정 줄에 대한 것이 아니라서 편집기는 그대로 있습니다.",
      "오른쪽 위 ‘에이전트 구조’ 는 검사가 지나가는 길입니다. 문제를 고르면 그 판단에 관여한 노드만 밝게 남고, 노드를 누르면 그 노드가 무엇인지 ‘상세’ 에 나옵니다. 그림이 작으면 경계선을 끌어 넓히면 됩니다.",
      "맨 위 숫자를 누르면 검사 범위와 판단 흐름, 든 비용이 나옵니다. ‘중단점’ 은 다음 실행을 원하는 노드에서 멈추고, ‘지난 검사’ 로 예전 검사를 다시 열거나 지울 수 있습니다.",
    ],
  },
  {
    id: "f2a",
    href: "/f2a",
    label: "F2-A",
    note: "어떤 요청이 어떤 핸들러로 가는지 정적으로 풀어냅니다",
    icon: ShieldCheck,
    carries: ["sample", "view"],
    panes: ["side", "dock", "inspector"],
    chrome: true,
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
    panes: ["side", "inspector"],
    chrome: true,
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
    panes: ["side"],
    chrome: true,
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
