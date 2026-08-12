"use client";

import { BarChart3 } from "lucide-react";
import { useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { PanelShell } from "@/components/workbench/PanelShell";
import { describeError } from "@/lib/api/client";
import { fromAgent } from "@/lib/model/finding";
import { useKnowledge } from "@/lib/run/knowledge-queries";
import { useApplyFix, useDiff, useFindings, useRun, useRuns } from "@/lib/run/queries";
import { useRunStream } from "@/lib/run/stream";
import { useSpans } from "@/lib/run/trace-queries";
import { useOpenFile, useRevealLine, useSelectedFinding } from "@/lib/run/selection";
import { useRunId } from "@/lib/run/use-run-id";
import type { RunSummary as RunRecord } from "@/lib/api/types";
import FindingList from "./FindingList";
import RunSummary, { coverageOf } from "./RunSummary";

/** Radix needs a non-empty value, and `null` is not one. */
const NO_COMPARISON = "none";

/** `net.c 외 3 · 8/10 16:37 · 5건`, which is enough to tell two runs apart. */
function labelOf(run: RunRecord): string {
  const name = run.files[0] ?? run.run_id;
  const more = run.file_count > 1 ? ` 외 ${run.file_count - 1}` : "";
  const when = new Date(run.updated_at * 1000).toLocaleString("ko-KR", {
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
  return `${name}${more} · ${when} · ${run.findings ?? 0}건`;
}

/**
 * The bottom pane: what the run found. One thing, no tab strip.
 *
 * It had three tabs, and they were not three of a kind: 문제 is the answer, and
 * the other two were a state debugger and a graph canvas. A result list sharing a
 * strip with two developer tools meant the answer was a tab you had to pick. Those
 * two are off the tab strip entirely now -- they open from the command palette,
 * which is where a tool you reach for once a month belongs.
 *
 * A row opens in place to show why: the explanation, the evidence trail, the fix.
 * That used to need a third pane on the far side of the window, which was empty
 * until you had clicked something and replaced whatever you were reading when you
 * did.
 *
 * 요약 is the same panel's other half. A count of problems is only meaningful
 * beside how much was looked at to arrive at it, and that number was on the wire
 * all along -- so it sits behind one toggle here rather than in a tab of its own,
 * and opens by itself in the one case where it is the whole answer.
 */
export default function AgentDock() {
  const [runId] = useRunId();
  const [, setPath] = useOpenFile();
  const [, setLine] = useRevealLine();
  const [findingId, setFindingId] = useSelectedFinding();

  const { phase, live } = useRunStream();
  const findings = useFindings(runId);
  const knowledge = useKnowledge(runId);
  const spans = useSpans(runId);
  const run = useRun(runId);

  const ui = useMemo(() => fromAgent(findings.data?.findings ?? []), [findings.data]);
  const running = phase === "running" || phase === "starting";
  const { total, done } = coverageOf(findings.data?.stats, live);

  /**
   * The run this one is being read against.
   *
   * Local rather than in the URL: it is a question you ask of the run you are
   * already on, and it stops being a sensible question the moment you leave it.
   */
  const [against, setAgainst] = useState<string | null>(null);

  const runs = useRuns();
  // A run that was never inspected has no report to compare against, and the
  // server answers a diff against one with an error rather than an empty set.
  const others = useMemo(
    () => (runs.data ?? []).filter((each) => each.run_id !== runId && each.started),
    [runs.data, runId],
  );
  const diff = useDiff(runId, against);
  const apply = useApplyFix(runId);

  const compare = useMemo(() => {
    if (!against || !diff.data) return null;
    // Both sides through `fromAgent`: the rows these mark carry the view
    // model's engine-prefixed id, and the wire's bare one matches none of them.
    return {
      fresh: new Set(fromAgent(diff.data.new).map((each) => each.id)),
      fixed: fromAgent(diff.data.fixed),
    };
  }, [against, diff.data]);

  /**
   * Whether 요약 is open, once somebody has said.
   *
   * `null` means nobody has: an empty list opens it, because "did it actually
   * look at my code" is then the only question on the page, and a list with
   * something in it leaves it shut. Answering by hand pins it either way until
   * the run changes.
   */
  const [pinned, setPinned] = useState<boolean | null>(null);

  // Both are answers about one run, so a different run asks again. Adjusted
  // during render rather than in an effect, as EditorPane's draft is: React
  // re-runs this immediately, instead of painting the last run's answer first.
  const [asked, setAsked] = useState(runId);
  if (asked !== runId) {
    setAsked(runId);
    setPinned(null);
    setAgainst(null);
  }

  const open = pinned ?? (runId !== null && ui.length === 0);

  return (
    // The root has to carry the height chain: PanelShell is `h-full` and this
    // sits between it and the panel.
    <Collapsible open={open} onOpenChange={setPinned} className="flex h-full min-h-0 flex-col">
      <PanelShell
        className="min-h-0 flex-1"
        title="문제"
        note={
          <>
            {ui.length > 0 ? `${ui.length}건` : runId ? "0건" : null}
            {total > 0 && ` · 단위 ${done}/${total}`}
          </>
        }
        actions={
          <>
            {others.length > 0 && (
              <Select
                value={against ?? NO_COMPARISON}
                onValueChange={(next) => setAgainst(next === NO_COMPARISON ? null : next)}
              >
                <SelectTrigger size="sm" className="h-7 max-w-52 gap-1 text-2xs" aria-label="비교할 실행">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent align="end">
                  <SelectItem value={NO_COMPARISON} className="text-xs">
                    비교 안 함
                  </SelectItem>
                  {others.map((each) => (
                    <SelectItem key={each.run_id} value={each.run_id} className="text-xs">
                      {labelOf(each)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
            <CollapsibleTrigger asChild>
              <Button variant="ghost" size="xs" aria-expanded={open}>
                <BarChart3 />
                요약
              </Button>
            </CollapsibleTrigger>
          </>
        }
      >
        <CollapsibleContent>
          <RunSummary
            stats={findings.data?.stats}
            spans={spans.data?.summary}
            run={run.data}
            live={live}
            phase={phase}
            findings={ui.length}
            diff={
              against
                ? {
                    fresh: diff.data?.new?.length ?? 0,
                    fixed: diff.data?.fixed?.length ?? 0,
                    unchanged: diff.data?.unchanged?.length ?? 0,
                    failed: diff.error ? describeError(diff.error) : diff.isPending ? "불러오는 중…" : null,
                  }
                : null
            }
          />
        </CollapsibleContent>

        <FindingList
          findings={ui}
          knowledge={knowledge.data}
          openId={findingId}
          compare={compare}
          // Only with a run to write to, and never while one is in flight: the
          // inspection is reading these files.
          onApply={runId && !running ? (finding) => apply.mutate(finding.id) : undefined}
          applying={apply.isPending}
          onOpen={(finding) => void setFindingId(finding?.id ?? null)}
          // Opening a row navigates too -- FindingList calls both -- so the file
          // and the line are set in exactly one place, here.
          onNavigate={(file, line) => {
            void setPath(file);
            void setLine(line > 0 ? line : null);
          }}
          emptyHint={
            !runId
              ? "왼쪽 탐색기에 코드를 넣고 ‘검사 실행’을 누르세요."
              : running
                ? "검사 중입니다. 결과는 도착하는 대로 나타납니다."
                : run.data?.started
                  ? "이 코드에서는 취약점을 찾지 못했습니다. 위 요약이 무엇을 얼마나 살펴본 끝의 결과인지 말해 주고, 오른쪽 대화에 그 과정이 남아 있습니다."
                  : "아직 검사하지 않았습니다. ‘검사 실행’을 누르세요."
          }
        />
      </PanelShell>
    </Collapsible>
  );
}
