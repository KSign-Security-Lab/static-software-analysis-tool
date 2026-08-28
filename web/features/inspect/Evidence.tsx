"use client";

import { ROLE_LABEL, ROLE_TONE, type Evidence as EvidenceStep } from "@/lib/model/finding";
import { cn } from "@/lib/utils";

/**
 * The argument, in the order it was made.
 *
 * 유입 → 전파 → 위험 지점 is a path through the code, and each step is somewhere
 * else -- often in another file. The old surface answered a click on a step by
 * moving an editor to that line, which meant the argument was only ever visible
 * one step at a time. Every step carries its own excerpt, so the whole path is
 * readable at once.
 *
 * The stripe colour is the step's role, from the shared `ROLE_TONE` -- the same
 * vocabulary the finding list and F2-A's evidence report use.
 */
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
            {/* A location, when the step has one. `missing_check` steps are
                about the absence of code and carry line 0, which is not a
                place -- printing `:0` would invent one. */}
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
