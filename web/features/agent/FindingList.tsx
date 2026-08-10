"use client";

import { ChevronRight, ShieldCheck } from "lucide-react";

import { neighbours } from "@/lib/api/knowledge";
import type { KnowledgeGraph } from "@/lib/api/types";
import { ROLE_LABEL, SEVERITY_LABEL, sortFindings, type UiFinding } from "@/lib/model/finding";
import { cn } from "@/lib/utils";

/**
 * What the agent concluded, and why, in one list.
 *
 * These were two panels: a list at the bottom of the window and the reasoning
 * behind the selected row in a pane on the far right. Reading one finding meant
 * looking at opposite corners of the screen, and the pane was empty until you
 * had clicked something -- so a third of the window was reserved for nothing.
 * Opening a row in place puts the claim and its grounds in one column.
 *
 * Worst first. The severity filter that used to sit above this is gone: both
 * engines answer the same question about the same code and there has never been
 * a reason to read one and not the other.
 */

const SEVERITY_DOT: Record<string, string> = {
  critical: "bg-sev-critical",
  high: "bg-sev-high",
  medium: "bg-sev-medium",
  low: "bg-sev-low",
  info: "bg-sev-info",
};

const ROLE_TONE: Record<string, string> = {
  source: "border-l-warn",
  propagation: "border-l-line-3",
  sink: "border-l-danger",
  missing_check: "border-l-alt",
  context: "border-l-line-2",
};

export default function FindingList({
  findings,
  knowledge,
  openId,
  onOpen,
  onNavigate,
  emptyHint,
}: {
  findings: UiFinding[];
  knowledge?: KnowledgeGraph;
  /** The finding whose grounds are showing; also what the editor is marking. */
  openId: string | null;
  onOpen: (finding: UiFinding | null) => void;
  onNavigate: (file: string, line: number) => void;
  emptyHint: string;
}) {
  if (findings.length === 0) {
    return (
      <div className="flex items-start gap-2.5 px-3 py-4">
        <ShieldCheck className="mt-0.5 size-4 shrink-0 text-ink-faint" />
        <p className="text-xs leading-relaxed text-ink-faint">{emptyHint}</p>
      </div>
    );
  }

  return (
    <ul>
      {sortFindings(findings).map((finding) => {
        const open = finding.id === openId;
        return (
          <li key={finding.id} className="border-b border-line/60 last:border-b-0">
            <button
              type="button"
              aria-expanded={open}
              onClick={() => {
                onOpen(open ? null : finding);
                // A finding is a claim about a line, so opening it shows the line.
                if (!open) onNavigate(finding.primary.file, finding.primary.startLine);
              }}
              className={cn(
                "flex w-full items-start gap-2 px-3 py-2 text-left transition-colors hover:bg-surface-2",
                open && "bg-surface-2",
              )}
            >
              <ChevronRight
                className={cn("mt-0.5 size-3 shrink-0 text-ink-faint transition-transform", open && "rotate-90")}
              />
              {/* The dot is the severity. It was also spelled out in the line
                  below, which is the same fact twice on every row; the label is
                  the dot's accessible name now. */}
              <span
                title={SEVERITY_LABEL[finding.severity]}
                aria-label={SEVERITY_LABEL[finding.severity]}
                className={cn("mt-1 size-1.5 shrink-0 rounded-full", SEVERITY_DOT[finding.severity])}
              />
              <span className="min-w-0 flex-1">
                <span className="block text-xs leading-snug font-medium text-ink-strong">{finding.title}</span>
                <span className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-2xs text-ink-faint">
                  {finding.cwe && <span className="font-mono">{finding.cwe}</span>}
                  <span className="font-mono">
                    {finding.primary.file}:{finding.primary.startLine}
                  </span>
                  {finding.verified && <span className="text-ok">반박을 견딤</span>}
                </span>
              </span>
            </button>

            {open && <Grounds finding={finding} knowledge={knowledge} onNavigate={onNavigate} />}
          </li>
        );
      })}
    </ul>
  );
}

/** Why the agent said it: the explanation, the trail, the neighbours, the fix. */
function Grounds({
  finding,
  knowledge,
  onNavigate,
}: {
  finding: UiFinding;
  knowledge?: KnowledgeGraph;
  onNavigate: (file: string, line: number) => void;
}) {
  const confidence = Math.round(finding.confidence * 100);
  // The callers and callees of the unit this sits in. Computed here because the
  // whole graph is already in the cache -- the server can do it and does not
  // expose it, and a walk beats a round trip per opened finding.
  const related = knowledge && finding.chunkId ? neighbours(knowledge, finding.chunkId, 1) : [];

  return (
    <div className="space-y-3 px-3 pb-3 pl-8">
      <p className="text-xs leading-relaxed whitespace-pre-wrap text-ink-muted">{finding.explanation}</p>

      <div className="flex items-center gap-2">
        <span className="text-2xs text-ink-faint">확신도</span>
        {/* A meter, not a progress bar: it is a measurement, not a task. */}
        <div
          role="meter"
          aria-valuenow={confidence}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label="확신도"
          className="h-1 w-24 overflow-hidden rounded-full bg-surface-3"
        >
          <div className="h-full rounded-full bg-accent-solid" style={{ width: `${confidence}%` }} />
        </div>
        <span className="font-mono text-2xs text-ink-faint">{confidence}%</span>
      </div>

      {finding.evidence.length > 0 && (
        <section className="space-y-1">
          <h4 className="text-2xs text-ink-muted">근거</h4>
          <ol>
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
        <section className="space-y-1">
          <h4 className="text-2xs text-ink-muted">고치는 방법</h4>
          {/* Shown, never applied: a suggested patch from a model is a
              suggestion, and it is for a person to read. */}
          <p className="text-xs leading-relaxed whitespace-pre-wrap text-ink-muted">{finding.remediation}</p>
        </section>
      )}

      {related.length > 0 && (
        <section className="space-y-1">
          <h4 className="text-2xs text-ink-muted">관련 코드</h4>
          <ul className="flex flex-wrap gap-1">
            {related.slice(0, 12).map((node) => (
              <li key={node.id}>
                <button
                  type="button"
                  onClick={() => onNavigate(node.file, node.attrs?.start_line ?? 0)}
                  className="rounded-sm border border-line px-1.5 py-0.5 font-mono text-2xs text-ink-muted transition-colors hover:border-line-3 hover:text-ink"
                  title={`${node.file}${node.attrs ? `:${node.attrs.start_line}` : ""}`}
                >
                  {node.label}
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
