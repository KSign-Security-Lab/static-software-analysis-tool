"use client";

import { useMemo, useState } from "react";

import StepGraph from "@/components/graph/StepGraph.lazy";
import type { UiFinding } from "@/lib/model/finding";
import { useClaimTrail } from "@/lib/run/claim-trail";
import { useGraphShape, useSpans } from "@/lib/run/trace-queries";
import { useRunId } from "@/lib/run/use-run-id";

export default function Structure({ finding }: { finding: UiFinding }) {
  const [runId] = useRunId();
  const shape = useGraphShape();
  const spans = useSpans(runId);
  const trail = useClaimTrail(finding);
  const [expanded, setExpanded] = useState(false);

  const path = useMemo(
    () => [...new Set(trail.map((each) => each.node).filter((node): node is string => Boolean(node)))],
    [trail],
  );

  if (!shape.data) {
    return <p className="px-2.5 py-2 text-2xs text-ink-faint">구조를 불러오는 중…</p>;
  }

  return (
    <div className="space-y-1 px-2.5 py-2">
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
