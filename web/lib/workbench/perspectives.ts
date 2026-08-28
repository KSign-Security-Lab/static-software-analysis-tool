import { Network, ScanSearch, ShieldCheck, TerminalSquare, Trophy, type LucideIcon } from "lucide-react";

/**
 * The five surfaces, declared once.
 *
 * The rail reads this, so a route cannot be added in one place and forgotten in
 * another -- and `carries` names the params that must survive a switch, which is
 * what stops the rail dropping `?run=` on the way past.
 *
 * Two shells, one list. 검사 left the workbench: it is a flow -- give code, read
 * findings, take a patch -- and a four-pane IDE is the wrong shape for a flow.
 * The four research surfaces stayed, because comparing a graph against the code
 * that produced it is exactly what resizable panes are for. `panes` and `chrome`
 * are the workbench's fields and 검사 answers both with nothing.
 *
 * 트레이스 was a sixth until it turned out not to be a place. What it held now
 * belongs to the finding it explains: 판단 과정 and 에이전트 구조 are the last two
 * sections of a finding's detail, closed until asked for. They were two of four
 * centre tabs competing with the code for width, which is why neither was ever
 * read -- the reader had to leave the finding to look at its own reasoning.
 */

export type PerspectiveId = "agent" | "f2a" | "extract" | "stages" | "bench";

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
    note: "코드를 올려 취약점을 찾고, 고칠 것만 골라 패치를 받습니다",
    icon: ScanSearch,
    carries: ["run"],
    // Neither. This surface has its own shell -- see app/(inspect) -- and the
    // workbench never renders it, so a pane list or a title bar here would be
    // describing a layout that does not exist.
    panes: [],
    chrome: false,
    purpose:
      "이 코드에 취약점이 있는가, 그리고 그중 무엇을 지금 고칠 것인가 — 찾고, 읽고, 골라서 패치까지 갑니다.",
    steps: [
      "폴더를 끌어다 놓거나, 압축 파일을 고르거나, git 주소를 붙여넣습니다.",
      "‘검사 시작’을 누릅니다. 다 끝나기를 기다릴 필요는 없습니다 — 찾은 것이 그 자리에서 쌓이고, 바로 읽어도 됩니다.",
      "목록에서 한 줄을 고르면 오른쪽에 판단·근거·고치는 방법·패치가 나옵니다. 심각도나 CWE, 파일로 좁힐 수 있습니다.",
      "왜 그렇게 판단했는지 궁금하다면 ‘판단 과정’을 펼칩니다. 그 판단을 낸 호출이 순서대로 나오고, 하나를 고르면 주고받은 말이 그대로 보입니다.",
      "고칠 것에 체크합니다. 아래에 담긴 개수가 나오고, ‘패치 만들기’를 누르면 무엇이 들어가고 무엇이 빠지는지 먼저 보여 줍니다.",
      "패치 파일이나 수정된 소스를 내려받습니다. git 주소로 가져온 검사라면 브랜치로 바로 올릴 수도 있습니다.",
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
    id: "bench",
    href: "/bench",
    label: "벤치마크",
    note: "공개 벤치마크에서 어디까지 하고 어디서 깨지는지 봅니다",
    icon: Trophy,
    // This surface's own state, and only that. `carries` is the *rail's*
    // mechanism -- `hrefFor` copies these off the current URL when you switch
    // *into* bench -- so it has nothing to do with opening an instance's run.
    // That link is built by hand in `InstanceDetail` from `instance.run_id`,
    // because this surface's URL never holds a `run=` to carry.
    carries: ["dataset", "instance"],
    panes: ["side", "inspector"],
    chrome: false,
    purpose:
      "우리 에이전트가 공개 벤치마크에서 어디까지 하는가, 그리고 어디서 깨지는가 — 실패한 지점부터 보고, 점수는 그 다음입니다.",
    steps: [
      "왼쪽 위 선택기에서 볼 데이터셋과 트랙을 고릅니다. 아직 돌린 것이 없으면 무엇을 돌려야 하는지 그 자리에 나옵니다.",
      "왼쪽 목록은 기본이 ‘깨진 지점별’ 묶음입니다 — 위치 못 찾음 · 찾고 오독 · 패치 빌드 실패 · 빌드됐으나 미수정 · 고쳤으나 테스트 깨짐. 어느 칸이 두꺼운지가 지금 무엇을 고쳐야 하는지입니다.",
      "한 인스턴스를 고르면 오른쪽 ‘상세’ 에 그 인스턴스가 어디서 어떻게 끊겼는지가 나옵니다. ‘검사에서 열기’ 를 누르면 그때 기록된 검사가 그대로 열립니다 — 판단 과정도, 부른 도구도 그대로입니다.",
      "오른쪽 위 점수는 설정 해시·모델·제외된 인스턴스 수와 함께만 나옵니다. 셋 중 하나라도 없으면 숫자 대신 ‘점수 없음’ 입니다. 어떤 설정으로 낸 숫자인지 모르면 그 숫자는 쓸 데가 없기 때문입니다.",
      "‘오염됨’ 으로 표시된 인스턴스는 목록에 그대로 남고 점수에서만 빠집니다. 무엇을 왜 뺐는지도 결과의 일부입니다.",
      "아래 ‘공개 수치’ 는 같은 트랙의 발표된 성적입니다. 각자 쓴 모델이 함께 적혀 있고, 우리가 재현한 것이 아니라 보고된 값입니다.",
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
 *
 * Takes a nullable path because every caller hands it `usePathname()` directly,
 * and that returns `null` outside a router -- which threw
 * `Cannot read properties of null` from three call sites rather than answering
 * "no perspective", which is the honest answer to "where am I" when nobody
 * knows.
 */
export function perspectiveFor(pathname: string | null | undefined): Perspective | undefined {
  if (!pathname) return undefined;
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
