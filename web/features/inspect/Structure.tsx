"use client";

import { useMemo, useState } from "react";

import StepGraph from "@/components/graph/StepGraph.lazy";
import type { UiFinding } from "@/lib/model/finding";
import { useClaimTrail } from "@/lib/run/claim-trail";
import { useGraphShape, useSpans } from "@/lib/run/trace-queries";
import { useRunId } from "@/lib/run/use-run-id";

/**
 * The path this claim took through the agent, drawn.
 *
 * Scoped to one finding, which is the difference between this and the canvas it
 * replaces. That one drew the whole graph with the whole run painted on it, in a
 * pane that had to be big enough to be legible -- and answered a question nobody
 * had, because the graph is the same graph every time. What varies per finding is
 * which way through it the claim came, and that is what `path` lights.
 *
 * No breakpoints and nothing to click into. Interrupting a run at a node was the
 * studio's, and the node inspector it opened is the step list above this.
 */
export default function Structure({ finding }: { finding: UiFinding }) {
  const [runId] = useRunId();
  const shape = useGraphShape();
  const spans = useSpans(runId);
  const trail = useClaimTrail(finding);
  const [expanded, setExpanded] = useState(false);

  // The nodes this claim actually went through, in order. A specialist lens is
  // a node like any other, so an injection finding lights `injection` and not
  // the other four.
  const path = useMemo(
    () => [...new Set(trail.map((each) => each.node).filter((node): node is string => Boolean(node)))],
    [trail],
  );

  if (!shape.data) {
    return <p className="px-2.5 py-2 text-2xs text-ink-faint">구조를 불러오는 중…</p>;
  }

  return (
    <div className="space-y-1 px-2.5 py-2">
      {/* `relative` is load-bearing. `StepGraph` is `absolute inset-0` on
          purpose -- it takes its size from a positioned ancestor rather than
          from a percentage of an indefinite flex height -- so without this the
          canvas resolves against the viewport and draws itself across the whole
          window, over the findings list, leaving this box empty. */}
      <div className="relative h-[26rem] overflow-hidden rounded-md border border-line">
        <StepGraph
          shape={shape.data}
          spans={spans.data?.spans ?? []}
          running={[]}
          queued={[]}
          breakpoints={{ before: [], after: [] }}
          selected={null}
          onSelect={() => undefined}
          onInterrupt={() => undefined}
          // Top-to-bottom, not left-to-right. A node is 160px wide and the
          // pipeline is eleven ranks deep, so `LR` in a 500px column draws the
          // whole thing at 40px a node -- present and unreadable. `TB` spends
          // the column's width on one rank at a time, which is what it has.
          direction="TB"
          path={path.length > 0 ? path : null}
          expanded={expanded}
          onExpand={setExpanded}
        />
      </div>
      <p className="text-2xs leading-relaxed text-ink-faint">
        {path.length > 0
          ? "밝게 남은 노드가 이 판단에 관여한 단계입니다."
          : "이 판단의 호출 기록이 이 검사에 없어 지나온 길을 표시할 수 없습니다."}
      </p>
    </div>
  );
}
