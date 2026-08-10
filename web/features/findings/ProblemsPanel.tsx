"use client";

import { ShieldCheck } from "lucide-react";
import { useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { ENGINE_LABEL, SEVERITY_LABEL, sortFindings, type Engine, type UiFinding } from "@/lib/model/finding";
import { cn } from "@/lib/utils";

const SEVERITY_TEXT: Record<string, string> = {
  critical: "text-sev-critical",
  high: "text-sev-high",
  medium: "text-sev-medium",
  low: "text-sev-low",
  info: "text-sev-info",
};

const SEVERITY_DOT: Record<string, string> = {
  critical: "bg-sev-critical",
  high: "bg-sev-high",
  medium: "bg-sev-medium",
  low: "bg-sev-low",
  info: "bg-sev-info",
};

/**
 * The findings, worst first.
 *
 * Shared, and here rather than under a surface, because F2-A is the only caller
 * left: 검사 shows its findings with the reasoning folded into each row (see
 * features/inspect/FindingList.tsx), which a list-plus-detail-pane cannot do.
 *
 * Both engines land here -- the structural line and the agent answer the same
 * question about the same code, so they are read the same way. The filter says
 * which produced what, because that is the one thing you cannot tell by
 * looking at a finding.
 */
export default function ProblemsPanel({
  findings,
  selectedId,
  onSelect,
  emptyHint,
}: {
  findings: UiFinding[];
  selectedId: string | null;
  onSelect: (finding: UiFinding) => void;
  emptyHint?: string;
}) {
  const [engines, setEngines] = useState<Engine[]>(["structural", "agent"]);

  const present = useMemo(() => new Set(findings.map((f) => f.engine)), [findings]);
  const shown = useMemo(
    () => sortFindings(findings.filter((finding) => engines.includes(finding.engine))),
    [findings, engines],
  );

  if (findings.length === 0) {
    return (
      <div className="grid h-full place-items-center p-6 text-center">
        <p className="max-w-80 text-sm text-ink-faint">
          <ShieldCheck className="mx-auto mb-2 size-5 opacity-40" />
          {emptyHint ?? "아직 결과가 없습니다."}
        </p>
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      {present.size > 1 && (
        <div className="flex shrink-0 items-center gap-2 border-b border-line px-2.5 py-1.5">
          <ToggleGroup
            type="multiple"
            size="sm"
            variant="outline"
            value={engines}
            onValueChange={(next) => next.length && setEngines(next as Engine[])}
          >
            {(["structural", "agent"] as Engine[]).map((engine) => (
              <ToggleGroupItem key={engine} value={engine} className="h-7 px-2 text-2xs">
                {ENGINE_LABEL[engine]}
              </ToggleGroupItem>
            ))}
          </ToggleGroup>
          <span className="ml-auto text-2xs text-ink-faint">{shown.length}건</span>
        </div>
      )}

      <ul className="min-h-0 flex-1 overflow-auto">
        {shown.map((finding) => (
          <li key={finding.id}>
            <button
              type="button"
              onClick={() => onSelect(finding)}
              className={cn(
                "flex w-full items-start gap-2 border-b border-line/60 px-2.5 py-1.5 text-left transition-colors",
                "hover:bg-surface-2",
                selectedId === finding.id && "bg-accent-wash",
              )}
            >
              <span className={cn("mt-1.5 size-1.5 shrink-0 rounded-full", SEVERITY_DOT[finding.severity])} />
              <span className="min-w-0 flex-1">
                <span className="flex items-baseline gap-1.5">
                  <span className="truncate text-xs text-ink">{finding.title}</span>
                  {finding.cwe && (
                    <Badge variant="outline" className="shrink-0 px-1 py-0 text-2xs font-normal">
                      {finding.cwe}
                    </Badge>
                  )}
                  {finding.verified && (
                    <span className="shrink-0 text-2xs text-ok" title="반증 통과">
                      검증됨
                    </span>
                  )}
                </span>
                <span className="mt-0.5 flex items-center gap-2 font-mono text-2xs text-ink-faint">
                  <span className={SEVERITY_TEXT[finding.severity]}>{SEVERITY_LABEL[finding.severity]}</span>
                  <span className="truncate">
                    {finding.primary.file}
                    {finding.primary.startLine > 0 && `:${finding.primary.startLine}`}
                  </span>
                </span>
              </span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
