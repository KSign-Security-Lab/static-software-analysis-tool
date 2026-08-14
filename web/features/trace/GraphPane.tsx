"use client";

import { X } from "lucide-react";
import { useMemo, useState } from "react";

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
 * the bottom panel. It is the canvas of its own overlay now -- the first home
 * that is actually big enough for it. Everywhere else it was fitted into a pane
 * of a four-pane workbench, and the last of those was 460x334, which React Flow
 * solved at scale(0.3).
 *
 * Breakpoints are still set on the node itself, and are still locked once a run
 * is going: they are compiled in when the graph is built, so changing one
 * mid-run would be a lie.
 */
export default function GraphPane({
  direction = "LR",
  fit = 0,
}: { direction?: "LR" | "TB"; fit?: number } = {}) {
  const [runId] = useRunId();
  // The five specialists, drawn as one or as five. Collapsed by default: that
  // rank was six wide and owned ten of the graph's twenty-three edges, and five
  // boxes differing only in a word are not five things to understand.
  const [expanded, setExpanded] = useState(false);
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
      // No title. The overlay's own header names this, and a second 에이전트 구조
      // one row under the first is the panel saying what the reader just clicked.
      note={
        path ? (
          <span className="truncate text-2xs text-accent-ink">‘{finding!.title}’ 의 판단에 관여한 노드</span>
        ) : (
          <span className="truncate text-2xs text-ink-faint">노드를 누르면 오른쪽에 그 노드가 무엇인지 나옵니다</span>
        )
      }
      actions={
        <>
          {expanded && (
            <Button size="xs" variant="ghost" className="text-ink-muted" onClick={() => setExpanded(false)}>
              전문가 접기
            </Button>
          )}
          {node && (
            <Button size="xs" variant="ghost" onClick={() => select(null)}>
              {node}
              <X />
            </Button>
          )}
        </>
      }
      // `relative`, because the canvas inside is `absolute inset-0`. It cannot
      // take a percentage height off this box -- `PanelShell`'s body is
      // `min-h-0 flex-1`, which has no definite height for a percentage to
      // resolve against, so React Flow measured 0x0 and refused to draw
      // (error #004). Positioning sidesteps the question entirely.
      bodyClassName="relative overflow-hidden"
    >
      {/*
        The three-item legend that used to sit here is deleted, not moved.

        It explained a dash pattern, a solid line and a colour, and it cost two
        wrapped lines -- 55px of a pane that had 334px to draw in, so 13% of the
        canvas was spent teaching the reader how to read the other 87%. The
        router's name is on the edge it governs now, and 되돌아가기 is on the
        loop, which says the same three things where each applies and needs
        nothing read first.

        The refusal that used to sit here is on the run bar. It is a fact about
        the run rather than about the drawing, and it was on both.
      */}
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
          fit={fit}
          expanded={expanded}
          onExpand={setExpanded}
        />
      ) : (
        <p className="p-4 text-xs text-ink-faint">에이전트 구조를 불러오는 중…</p>
      )}
    </PanelShell>
  );
}
