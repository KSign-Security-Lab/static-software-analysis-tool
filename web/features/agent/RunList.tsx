"use client";

import { Info, ShieldCheck, X } from "lucide-react";
import { useMemo, useState } from "react";

import { Meta } from "@/components/panel/code-block";
import { Verdict } from "@/components/panel/verdict";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { describeError } from "@/lib/api/client";
import type { FindingDiff, RunSummary as RunRecord } from "@/lib/api/types";
import { SEVERITY_DOT, SEVERITY_LABEL, fromAgent, standingOf } from "@/lib/model/finding";
import { useDiff, useFindings, useRun, useRuns } from "@/lib/run/queries";
import { useFilter, useOpenedByRun, useSelection, type Filter } from "@/lib/run/selection";
import { useRunStream } from "@/lib/run/stream";
import { useGraphShape, useThreads } from "@/lib/run/trace-queries";
import { useRunId } from "@/lib/run/use-run-id";
import { outcomeOf } from "@/lib/trace/outcome";
import { labelOf, seconds, unitsOf } from "@/lib/trace/process";
import { countKept, filterRows, rowsOf, type Row } from "@/lib/trace/rows";
import { cn } from "@/lib/utils";

/**
 * Everything the run did, as one list.
 *
 * This replaces two tabs and a three-way mode switch. 문제 and 기록 were never two
 * things -- a finding *is* the row where the pipeline reached a verdict -- so
 * reading one finding's reasoning was a round trip between two lists of the same
 * events. Here the rows are the same rows and 문제 · 전체 · 도구 is how much of
 * them you want. See `lib/trace/rows.ts` for what a row is and why a finding row
 * can exist with no call behind it.
 *
 * Rows do not expand. A row is a summary and its full text -- the prompt, the
 * reply, the tool results, the evidence, the fix -- is 상세's, on the right. That
 * is the rule the whole surface now runs on: bottom is many, right is one.
 */
const FILTER_LABEL: Record<Filter, string> = { problems: "문제", all: "전체", tools: "도구" };

/** `net.c 외 3 · 8/10 16:37 · 5건`, which is enough to tell two runs apart. */
function labelOfRun(run: RunRecord): string {
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

const NO_COMPARISON = "none";

export default function RunList() {
  const [runId] = useRunId();
  const [filter, setFilter] = useFilter();
  const [openedByRun, setOpenedByRun] = useOpenedByRun();
  const { selection, select } = useSelection();
  const { phase } = useRunStream();

  const findings = useFindings(runId);
  const threads = useThreads(runId);
  const shape = useGraphShape();
  const run = useRun(runId);

  const ui = useMemo(() => fromAgent(findings.data?.findings ?? []), [findings.data]);
  const groups = useMemo(
    () => rowsOf(unitsOf(threads.data?.threads ?? [], shape.data?.steps ?? [], null), ui),
    [threads.data, shape.data, ui],
  );
  const shown = useMemo(() => filterRows(groups, filter), [groups, filter]);

  /**
   * The run this one is being read against.
   *
   * Local rather than in the URL: it is a question you ask of the run you are
   * already on, and it stops being a sensible question the moment you leave it.
   */
  const [against, setAgainst] = useState<string | null>(null);
  const runs = useRuns();
  const others = useMemo(
    () => (runs.data ?? []).filter((each) => each.run_id !== runId && each.started),
    [runs.data, runId],
  );
  const diff = useDiff(runId, against);
  const fresh = useMemo(
    () => (against && diff.data ? new Set(fromAgent(diff.data.new).map((each) => each.id)) : null),
    [against, diff.data],
  );

  // A comparison is an answer about one run, so a different run asks again.
  const [asked, setAsked] = useState(runId);
  if (asked !== runId) {
    setAsked(runId);
    setAgainst(null);
  }

  const chosen = selection?.id ?? null;
  const running = phase === "running" || phase === "starting";

  return (
    <div className="flex h-full min-h-0 flex-col">
      {/* Why the list is showing the whole record when you did not ask it to. */}
      {openedByRun && filter !== "problems" && (
        <button
          type="button"
          onClick={() => void setOpenedByRun(false)}
          className="flex shrink-0 items-center gap-1.5 border-b border-line bg-accent-wash px-3 py-1 text-2xs text-accent-ink hover:bg-surface-3"
        >
          <Info className="size-3 shrink-0" aria-hidden />
          <span className="min-w-0 truncate">검사를 시작해서 ‘{FILTER_LABEL[filter]}’ 로 넓혔습니다</span>
          <X className="ml-auto size-3 shrink-0" aria-hidden />
        </button>
      )}

      <div className="flex h-9 shrink-0 items-center gap-2 border-b border-line px-2.5">
        {/* A filter, and it says how much each setting would show -- so 전체 is a
            number rather than a leap. */}
        <ToggleGroup
          type="single"
          size="sm"
          value={filter}
          onValueChange={(next) => next && void setFilter(next as Filter)}
          className="gap-0"
        >
          {(Object.keys(FILTER_LABEL) as Filter[]).map((each) => (
            <ToggleGroupItem key={each} value={each} aria-label={FILTER_LABEL[each]} className="h-6 gap-1 px-2 text-2xs">
              {FILTER_LABEL[each]}
              <span className="text-ink-faint">{countKept(groups, each)}</span>
            </ToggleGroupItem>
          ))}
        </ToggleGroup>

        {others.length > 0 && (
          <div className="ml-auto flex shrink-0 items-center gap-2">
            {against && <Diff data={diff.data} error={diff.error} pending={diff.isPending} />}
            <span className="text-2xs text-ink-faint">비교</span>
            <Select
              value={against ?? NO_COMPARISON}
              onValueChange={(next) => setAgainst(next === NO_COMPARISON ? null : next)}
            >
              <SelectTrigger size="sm" className="h-6 w-56 gap-1 text-2xs" aria-label="비교할 실행">
                <SelectValue />
              </SelectTrigger>
              <SelectContent align="end">
                <SelectItem value={NO_COMPARISON} className="text-xs">
                  비교 안 함
                </SelectItem>
                {others.map((each) => (
                  <SelectItem key={each.run_id} value={each.run_id} className="text-xs">
                    {labelOfRun(each)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        )}
      </div>

      <div className="min-h-0 flex-1 overflow-auto">
        {shown.length === 0 ? (
          <p className="flex items-start gap-2.5 px-3 py-4 text-xs leading-relaxed text-ink-faint">
            <ShieldCheck className="mt-0.5 size-4 shrink-0" />
            {!runId
              ? "검사할 코드를 넣으면 여기에 실행 기록이 쌓입니다."
              : running
                ? "검사 중입니다. 결과는 도착하는 대로 나타납니다."
                : filter === "problems" && run.data?.started
                  ? "이 코드에서는 취약점을 찾지 못했습니다. ‘전체’ 로 바꾸면 무엇을 살펴봤는지 볼 수 있습니다."
                  : filter === "tools"
                    ? "이 실행에서 도구를 쓴 호출이 없습니다."
                    : "아직 검사하지 않았습니다. 위 ‘검사 실행’을 누르세요."}
          </p>
        ) : (
          shown.map((group) => (
            <section key={group.file}>
              <h3 className="sticky top-0 z-10 border-b border-line bg-surface-2 px-3 py-1 font-mono text-2xs font-semibold text-ink-strong">
                {group.file}
              </h3>
              {group.units.map((unit) => (
                <div key={unit.id}>
                  {/* One unit is not worth a heading of its own when the file has
                      only that one -- it would be the filename twice. */}
                  {group.units.length > 1 && (
                    <p className="px-3 pt-1.5 font-mono text-2xs text-ink-faint">{unit.name}</p>
                  )}
                  <ul>
                    {unit.rows.map((row) => (
                      <RowLine
                        key={row.id}
                        row={row}
                        chosen={row.id === chosen}
                        fresh={row.kind === "finding" && fresh ? fresh.has(row.finding.id) : null}
                        onSelect={() =>
                          select(
                            row.id === chosen
                              ? null
                              : row.kind === "finding"
                                ? { kind: "finding", id: row.finding.id }
                                : { kind: "call", id: row.call.id },
                          )
                        }
                      />
                    ))}
                  </ul>
                </div>
              ))}
            </section>
          ))
        )}
      </div>
    </div>
  );
}

/**
 * One row: what it was, what it decided, what it cost.
 *
 * A finding row and a call row are deliberately the same shape -- same columns,
 * same rhythm -- because they are the same list. What tells them apart is a
 * severity dot and a verdict, which is exactly the difference: one of these
 * concluded something about the code and the other is a step on the way.
 */
function RowLine({
  row,
  chosen,
  fresh,
  onSelect,
}: {
  row: Row;
  chosen: boolean;
  /** Against another run: new here, or unchanged. Null when nothing is being compared. */
  fresh: boolean | null;
  onSelect: () => void;
}) {
  const finding = row.kind === "finding" ? row.finding : null;
  const call = row.call;
  const outcome = call ? outcomeOf(call) : null;
  const standing = finding ? standingOf(finding) : null;

  return (
    <li>
      <button
        type="button"
        aria-current={chosen ? "true" : undefined}
        onClick={onSelect}
        className={cn(
          "flex w-full items-baseline gap-2 px-3 py-1.5 text-left transition-colors hover:bg-surface-2",
          chosen && "bg-surface-2",
        )}
      >
        {finding ? (
          <span
            title={SEVERITY_LABEL[finding.severity]}
            aria-label={SEVERITY_LABEL[finding.severity]}
            className={cn("mt-1.5 size-1.5 shrink-0 rounded-full", SEVERITY_DOT[finding.severity])}
          />
        ) : (
          <span className="mt-1.5 size-1.5 shrink-0" aria-hidden />
        )}

        <span className="min-w-0 flex-1">
          <span className="flex flex-wrap items-baseline gap-x-2">
            <span className={cn("text-xs", finding ? "font-medium text-ink-strong" : "text-ink-muted")}>
              {finding ? finding.title : labelOf(call!)}
            </span>
            {finding?.cwe && <span className="font-mono text-2xs text-ink-faint">{finding.cwe}</span>}
            {finding && (
              <span className="font-mono text-2xs text-ink-faint">
                {finding.primary.file}:{finding.primary.startLine}
              </span>
            )}
            {standing && <Verdict standing={standing} confidence={finding?.confidence ?? undefined} />}
            {!finding && call?.error && <span className="text-2xs text-danger">실패</span>}
            {!finding && outcome && <span className="text-2xs text-ink-faint">{outcome.text}</span>}
            {finding && finding.mergedIds.length > 0 && (
              <span className="text-2xs text-ink-faint" title="여러 단위에서 같은 문제가 보고되었습니다">
                {finding.mergedIds.length + 1}개 단위에서 확인
              </span>
            )}
            {fresh !== null && (
              <span className={cn("text-2xs", fresh ? "text-accent-ink" : "text-ink-faint")}>
                {fresh ? "새로" : "그대로"}
              </span>
            )}
          </span>
          {call ? (
            <Meta
              parts={[
                call.calls.length > 0 && `도구 ${call.calls.length}`,
                call.tokens ? `${call.tokens.toLocaleString()} tok` : null,
                seconds(call.latency_ms),
              ]}
            />
          ) : (
            // Said, not left blank: a row with no cost looks like a row with no
            // data until it says why.
            <span className="block text-2xs text-ink-faint">지난 검사에서 가져옴</span>
          )}
        </span>
      </button>
    </li>
  );
}

/** `새로 3 · 해결됨 2 · 그대로 5`, or why there is no answer yet. */
function Diff({ data, error, pending }: { data: FindingDiff | undefined; error: unknown; pending: boolean }) {
  if (error) return <span className="text-2xs text-danger">{describeError(error)}</span>;
  if (pending || !data) return <span className="text-2xs text-ink-faint">불러오는 중…</span>;

  return (
    <span className="flex items-center gap-2 text-2xs text-ink-muted">
      <span className="text-accent-ink">새로 {data.new?.length ?? 0}</span>
      <span className="text-ok">해결됨 {data.fixed?.length ?? 0}</span>
      <span>그대로 {data.unchanged?.length ?? 0}</span>
    </span>
  );
}
