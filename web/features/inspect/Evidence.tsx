"use client";

import { ROLE_LABEL, ROLE_TONE, type Evidence as EvidenceStep } from "@/lib/model/finding";
import { cn } from "@/lib/utils";

export default function Evidence({ evidence }: { evidence: EvidenceStep[] }) {
  return (
    <ol className="space-y-1.5">
      {evidence.map((step, index) => (
        <li
          key={`${step.span.file}:${step.span.startLine}:${index}`}
          className={cn("border-l-2 pl-2.5", ROLE_TONE[step.role] ?? "border-l-line-2")}
        >
          <p className="flex items-baseline gap-1.5">
            <span className="shrink-0 text-2xs font-medium text-ink-muted">{ROLE_LABEL[step.role]}</span>
            {step.span.startLine > 0 && (
              <span className="min-w-0 truncate font-mono text-2xs text-ink-faint">
                {step.span.file}:{step.span.startLine}
              </span>
            )}
          </p>
          <p className="mt-0.5 text-xs leading-relaxed text-ink">{step.note}</p>
          {step.span.excerpt && (
            <pre className="mt-1 overflow-x-auto rounded border border-line bg-field px-1.5 py-1 font-mono text-2xs text-ink-muted">
              {step.span.excerpt}
            </pre>
          )}
        </li>
      ))}
    </ol>
  );
}
