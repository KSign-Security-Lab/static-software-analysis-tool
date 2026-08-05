"use client";

import { ArrowRight } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { PanelShell } from "@/components/workbench/PanelShell";
import { ROLE_LABEL, SEVERITY_LABEL, type UiFinding } from "@/lib/model/finding";
import { cn } from "@/lib/utils";

const SEVERITY_TEXT: Record<string, string> = {
  critical: "text-sev-critical",
  high: "text-sev-high",
  medium: "text-sev-medium",
  low: "text-sev-low",
  info: "text-sev-info",
};

const ROLE_TONE: Record<string, string> = {
  source: "border-l-warn",
  propagation: "border-l-line-3",
  sink: "border-l-danger",
  missing_check: "border-l-alt",
  context: "border-l-line-2",
};

/** Why this is a finding, and where the evidence for it sits. */
export default function FindingInspector({
  finding,
  onNavigate,
}: {
  finding: UiFinding | null;
  onNavigate: (file: string, line: number) => void;
}) {
  if (!finding) {
    return (
      <PanelShell title="인스펙터">
        <div className="grid h-full place-items-center p-6 text-center">
          <p className="max-w-64 text-sm text-ink-faint">결과를 선택하면 근거가 여기에 표시됩니다.</p>
        </div>
      </PanelShell>
    );
  }

  const confidence = Math.round(finding.confidence * 100);

  return (
    <PanelShell title="인스펙터" note={finding.cwe ?? undefined}>
      <div className="space-y-4 p-3">
        <header className="space-y-1.5">
          <h3 className="text-sm leading-snug font-medium text-ink-strong">{finding.title}</h3>
          <div className="flex flex-wrap items-center gap-1.5">
            <Badge variant="outline" className={cn("px-1.5 py-0 text-2xs", SEVERITY_TEXT[finding.severity])}>
              {SEVERITY_LABEL[finding.severity]}
            </Badge>
            {finding.verified && (
              <Badge variant="outline" className="px-1.5 py-0 text-2xs text-ok">
                반증 통과
              </Badge>
            )}
            <button
              type="button"
              onClick={() => onNavigate(finding.primary.file, finding.primary.startLine)}
              className="ml-auto truncate font-mono text-2xs text-ink-faint hover:text-accent-ink"
            >
              {finding.primary.file}:{finding.primary.startLine}
            </button>
          </div>
        </header>

        <section className="space-y-1">
          <div className="flex items-baseline justify-between text-2xs text-ink-faint">
            <span>확신도</span>
            <span className="font-mono">{confidence}%</span>
          </div>
          {/* A meter, not a progress bar: it is a measurement, not a task. */}
          <div
            role="meter"
            aria-valuenow={confidence}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-label="확신도"
            className="h-1 overflow-hidden rounded-full bg-surface-3"
          >
            <div className="h-full rounded-full bg-accent-solid" style={{ width: `${confidence}%` }} />
          </div>
        </section>

        <p className="text-xs leading-relaxed whitespace-pre-wrap text-ink-muted">{finding.explanation}</p>

        {finding.evidence.length > 0 && (
          <section className="space-y-1.5">
            <h4 className="text-2xs font-semibold tracking-wide text-ink-faint uppercase">근거</h4>
            <ol className="space-y-1">
              {finding.evidence.map((step, index) => (
                <li key={`${step.span.file}:${step.span.startLine}:${index}`}>
                  <button
                    type="button"
                    onClick={() => onNavigate(step.span.file, step.span.startLine)}
                    className={cn(
                      "w-full border-l-2 py-1 pl-2 text-left transition-colors hover:bg-surface-2",
                      ROLE_TONE[step.role] ?? "border-l-line-2",
                    )}
                  >
                    <span className="flex items-center gap-1.5 text-2xs text-ink-faint">
                      <span className="text-ink-muted">{ROLE_LABEL[step.role]}</span>
                      {step.span.startLine > 0 && (
                        <span className="font-mono">
                          {step.span.file}:{step.span.startLine}
                        </span>
                      )}
                    </span>
                    <span className="mt-0.5 block text-xs leading-snug text-ink">{step.note}</span>
                  </button>
                </li>
              ))}
            </ol>
          </section>
        )}

        {finding.remediation && (
          <section className="space-y-1.5">
            <h4 className="flex items-center gap-1 text-2xs font-semibold tracking-wide text-ink-faint uppercase">
              <ArrowRight className="size-3" />
              고치는 방법
            </h4>
            {/* Shown, never applied: a suggested patch from a model is a
                suggestion, and the diff is for a person to read. */}
            <p className="text-xs leading-relaxed whitespace-pre-wrap text-ink-muted">{finding.remediation}</p>
          </section>
        )}
      </div>
    </PanelShell>
  );
}
