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
}

export const PERSPECTIVES: readonly Perspective[] = [
  {
    id: "agent",
    href: "/agent",
    label: "검사",
    note: "청크 단위 LLM 검사",
    icon: ScanSearch,
    carries: ["run", "file"],
  },
  {
    id: "trace",
    href: "/agent/trace",
    label: "트레이스",
    note: "실행이 답에 이른 경로",
    icon: Waypoints,
    carries: ["run", "span", "node", "cp"],
  },
  {
    id: "f2a",
    href: "/f2a",
    label: "F2-A",
    note: "핸들러 해석과 근거 추적",
    icon: ShieldCheck,
    carries: ["sample", "view"],
  },
  {
    id: "extract",
    href: "/extract",
    label: "추출",
    note: "CPG · AST · CFG · DFG · 파이프라인",
    icon: Network,
    carries: ["sample", "view"],
  },
  {
    id: "stages",
    href: "/extract/stages",
    label: "스테이지",
    note: "파이프라인 단계 하나만 실행",
    icon: TerminalSquare,
    carries: ["sample", "stage"],
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
