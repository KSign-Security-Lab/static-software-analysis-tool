"use client";

import { CheckSquare, Square, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Toggle } from "@/components/ui/toggle";
import { byCwe, byFile, bySeverity, byStanding, isEmpty, type Facets } from "@/lib/inspect/filter";
import { SEVERITY_DOT, SEVERITY_LABEL, STANDING_LABEL, type Severity, type Standing } from "@/lib/model/finding";
import { SORTS, useSort } from "@/lib/run/selection";
import { cn } from "@/lib/utils";

const SORT_LABEL: Record<(typeof SORTS)[number], string> = {
  severity: "심각한 것부터",
  file: "파일별",
  confidence: "확신 높은 것부터",
};

/**
 * Narrowing the list, and saying how much of it is left.
 *
 * Every count is over the *whole* report rather than over what is currently
 * shown. A control whose number changes when you press it cannot tell you what
 * pressing it would do -- and these double as the summary of the run, so a
 * severity count that shrank as you filtered would stop being the answer to
 * "how bad is this".
 *
 * Facets are toggles rather than a single-select because the real questions are
 * plural: "critical and high", "these two files". An empty set means no opinion,
 * so nothing is excluded until something is pressed.
 */
export default function FilterBar({
  findings,
  shown,
  facets,
  onFacets,
  onTickAll,
  allTicked,
}: {
  findings: import("@/lib/model/finding").UiFinding[];
  shown: import("@/lib/model/finding").UiFinding[];
  facets: Facets;
  onFacets: (next: Facets) => void;
  onTickAll: (on: boolean) => void;
  allTicked: boolean;
}) {
  const [order, setOrder] = useSort();

  function toggleIn<T extends string>(key: "severity" | "cwe" | "file" | "standing", value: T) {
    const next = new Set(facets[key] as Set<string>);
    if (next.has(value)) next.delete(value);
    else next.add(value);
    onFacets({ ...facets, [key]: next } as Facets);
  }

  const severities = bySeverity(findings);
  const cwes = byCwe(findings).slice(0, 8);
  const files = byFile(findings).slice(0, 8);
  const standings = byStanding(findings);
  const filtered = !isEmpty(facets);

  return (
    <div className="shrink-0 space-y-2 border-b border-line bg-surface px-2.5 py-2">
      <div className="flex items-center gap-1.5">
        <Button
          size="sm"
          variant="ghost"
          onClick={() => onTickAll(!allTicked)}
          disabled={shown.length === 0}
          aria-label={allTicked ? "보이는 것 모두 빼기" : "보이는 것 모두 담기"}
        >
          {allTicked ? <CheckSquare className="size-3.5" /> : <Square className="size-3.5" />}
          {allTicked ? "모두 빼기" : "모두 담기"}
        </Button>

        <span className="font-mono text-2xs text-ink-faint">
          {filtered ? `${shown.length} / ${findings.length}` : `${findings.length}건`}
        </span>

        <span className="ml-auto flex items-center gap-1.5">
          <Input
            value={facets.query}
            onChange={(event) => onFacets({ ...facets, query: event.target.value })}
            placeholder="제목 · CWE · 경로"
            aria-label="검색"
            className="h-7 w-44 text-xs"
          />
          <Select value={order} onValueChange={(next) => void setOrder(next as typeof order)}>
            <SelectTrigger size="sm" className="w-36" aria-label="정렬">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {SORTS.map((each) => (
                <SelectItem key={each} value={each}>
                  {SORT_LABEL[each]}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </span>
      </div>

      <div className="flex flex-wrap items-center gap-1">
        {severities.map(({ value, count }) => (
          <Facet
            key={value}
            on={facets.severity.has(value)}
            onClick={() => toggleIn<Severity>("severity", value)}
            dot={SEVERITY_DOT[value]}
            count={count}
            label={`${SEVERITY_LABEL[value]}만 보기`}
          >
            {SEVERITY_LABEL[value]}
          </Facet>
        ))}

        {standings.map(({ value, count }) => (
          <Facet
            key={value}
            on={facets.standing.has(value)}
            onClick={() => toggleIn<Standing>("standing", value)}
            count={count}
            label={`${STANDING_LABEL[value]}만 보기`}
          >
            {STANDING_LABEL[value]}
          </Facet>
        ))}

        {cwes.map(({ value, count }) => (
          <Facet
            key={value}
            on={facets.cwe.has(value)}
            onClick={() => toggleIn("cwe", value)}
            count={count}
            label={`${value}만 보기`}
            mono
          >
            {value}
          </Facet>
        ))}

        {files.map(({ value, count }) => (
          <Facet
            key={value}
            on={facets.file.has(value)}
            onClick={() => toggleIn("file", value)}
            count={count}
            label={`${value}만 보기`}
            mono
          >
            {/* The basename. A full path is most of the row's width and the
                distinguishing part is at the end of it. */}
            {value.split("/").pop()}
          </Facet>
        ))}

        {filtered && (
          <Button size="sm" variant="ghost" onClick={() => onFacets({ ...facets, ...EMPTY })}>
            <X className="size-3" />
            조건 지우기
          </Button>
        )}
      </div>
    </div>
  );
}

const EMPTY = {
  severity: new Set<Severity>(),
  cwe: new Set<string>(),
  file: new Set<string>(),
  standing: new Set<Standing>(),
  query: "",
};

function Facet({
  on,
  onClick,
  dot,
  count,
  mono,
  label,
  children,
}: {
  on: boolean;
  onClick: () => void;
  dot?: string;
  count: number;
  mono?: boolean;
  /**
   * What pressing it does, for a screen reader.
   *
   * The visible text is the value alone -- `치명적`, `CWE-78` -- which reads as a
   * label rather than as a control, and collides with the severity a row
   * announces for its own dot. Naming it as a filter fixes both.
   */
  label: string;
  children: React.ReactNode;
}) {
  return (
    <Toggle
      pressed={on}
      onPressedChange={onClick}
      size="sm"
      aria-label={label}
      className={cn("h-6 gap-1 px-1.5 text-2xs", mono && "font-mono")}
    >
      {dot && <span className={cn("size-1.5 rounded-full", dot)} aria-hidden />}
      {children}
      <span className="text-ink-faint">{count}</span>
    </Toggle>
  );
}
