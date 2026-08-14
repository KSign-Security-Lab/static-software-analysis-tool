"use client";

import { X } from "lucide-react";
import { useMemo } from "react";

import StepGraph from "@/components/graph/StepGraph.lazy";
import { Button } from "@/components/ui/button";
import { PanelShell } from "@/components/workbench/PanelShell";
import { useRunStream } from "@/lib/run/stream";
import { useClaimTrail } from "@/lib/run/claim-trail";
import { useRunControls } from "@/lib/run/controls";
import { useOpenFinding } from "@/lib/run/queries";
import { idOf, useSelection } from "@/lib/run/selection";
import { TERMINALS } from "@/lib/trace/layout";
import { useGraphShape, useSpans } from "@/lib/run/trace-queries";
import { useRunId } from "@/lib/run/use-run-id";

/**
 * The agent's structure, with the run painted on.
 *
 * The drawing and nothing else. It used to carry 검사 실행, 이어서, 중단 and the
 * breakpoint list as well -- a second copy of controls the editor also had, on
 * a pane whose subject is the shape of the pipeline. The run bar owns all four
 * now and this reads the same breakpoints out of `useRunControls`, so ticking a
 * node here and pressing the button up there are one gesture.
 *
 * The top of the right-hand column, drawn top to bottom, because that is the
 * shape of the space: a tall narrow column suits a vertical pipeline, and beside
 * the code beats stacked under it where three regions fought for one column's
 * height.
 *
 * It has been a centre tab, the left column of a full-window overlay, a tab of
 * the bottom panel, a row of pills that was not the graph at all, and the top of
 * the bottom panel. `direction` is the only thing that changed with the last move
 * -- `layoutGraph` has always taken it.
 *
 * Breakpoints are still set on the node itself, and are still locked once a run
 * is going: they are compiled in when the graph is built, so changing one
 * mid-run would be a lie.
 */
export default function GraphPane({ direction = "LR" }: { direction?: "LR" | "TB" } = {}) {
  const [runId] = useRunId();
  const { selection, select } = useSelection();
  const node = idOf(selection, "node");
  const { live } = useRunStream();

  const shape = useGraphShape();
  const spans = useSpans(runId);
  const { breakpoints, toggleBreakpoint } = useRunControls();

  /**
   * The nodes that produced the finding being read, when one is.
   *
   * This is the drawing's answer to "how was each agent involved in this
   * decision": the same chain `상세` lists in order, marked on the real pipeline
   * so it is a path through something rather than five names. Everything off it
   * dims; nothing is hidden, because a node that did not run is part of the
   * answer too -- `skip` staying dark is why the unit was looked at.
   */
  const finding = useOpenFinding(runId);
  const trail = useClaimTrail(finding);
  const path = useMemo(() => {
    if (!finding || trail.length === 0) return null;
    const names = trail.map((each) => each.node).filter((each): each is string => Boolean(each));
    // The terminals always belong: every run enters and leaves through them, and
    // a path that stopped short of `end` would read as an unfinished argument.
    return [...new Set([...names, ...TERMINALS])];
  }, [finding, trail]);

  return (
    <PanelShell
      // Titled again. It lost its title when it was a tab of the bottom panel and
      // the tab strip named it; it is the top of the right column now, nothing
      // else names it, and the app's own 사용법 was pointing at a pane with no
      // label on it.
      title="에이전트 구조"
      actions={
        node && (
          <Button size="xs" variant="ghost" onClick={() => select(null)}>
            {node}
            <X />
          </Button>
        )
      }
      bodyClassName="overflow-hidden"
    >
      {/* Nothing on screen said what a dotted line meant, so it had to be asked.
          The distinction is LangGraph's own -- `add_conditional_edges` against
          `add_edge` -- and it comes through the shape untouched. */}
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border-b border-line px-2.5 py-1.5 text-2xs text-ink-faint">
        <span className="flex items-center gap-1.5">
          <svg width="22" height="6" aria-hidden className="shrink-0">
            <line x1="0" y1="3" x2="22" y2="3" stroke="var(--line-3)" strokeWidth="1.5" />
          </svg>
          항상 실행
        </span>
        <span className="flex items-center gap-1.5">
          <svg width="22" height="6" aria-hidden className="shrink-0">
            <line x1="0" y1="3" x2="22" y2="3" stroke="var(--line-3)" strokeWidth="1.5" strokeDasharray="5 4" />
          </svg>
          조건부 — 라우터가 고릅니다
        </span>
        <span className="flex items-center gap-1.5">
          <svg width="22" height="6" aria-hidden className="shrink-0">
            <line x1="0" y1="3" x2="22" y2="3" stroke="var(--alt)" strokeWidth="1.5" />
          </svg>
          다음 차례로 되돌아가기
        </span>
        {path ? (
          <span className="ml-auto text-accent-ink">
            ‘{finding!.title}’ 의 판단에 관여한 노드만 밝게 — 위 ‘문제’ 칩의 × 로 전체를 봅니다
          </span>
        ) : (
          <span className="ml-auto">노드를 누르면 오른쪽 ‘상세’에 그 노드가 무엇인지 나옵니다</span>
        )}
      </div>

      {/* The refusal that used to sit here is on the run bar. It is a fact about
          the run rather than about the drawing, and it was on both. */}
      {shape.data ? (
        <StepGraph
          shape={shape.data}
          spans={spans.data?.spans ?? []}
          running={live.running}
          queued={live.queued}
          breakpoints={breakpoints}
          selected={node}
          path={path}
          onSelect={(next) => select(next ? { kind: "node", id: next } : null)}
          onInterrupt={toggleBreakpoint}
          direction={direction}
        />
      ) : (
        <p className="p-4 text-xs text-ink-faint">에이전트 구조를 불러오는 중…</p>
      )}
    </PanelShell>
  );
}
