"use client";

import { ChevronRight, ShieldCheck, Wrench } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { Patch } from "@/components/panel/patch";
import { Verdict } from "@/components/panel/verdict";
import { Button } from "@/components/ui/button";
import { neighbours } from "@/lib/api/knowledge";
import type { KnowledgeGraph } from "@/lib/api/types";
import {
  ROLE_LABEL,
  ROLE_TONE,
  SEVERITY_DOT,
  SEVERITY_LABEL,
  sortFindings,
  standingOf,
  type UiFinding,
} from "@/lib/model/finding";
import { cn } from "@/lib/utils";

/**
 * What the agent concluded, and why, in one list.
 *
 * The list only. Choosing a row moves the editor to its line and fills 상세 on
 * the right with the grounds -- so choosing and reading are different panes, and
 * a row is a row rather than something that unfolds into a page.
 *
 * This has been all three arrangements. Grounds in a pane on the far right with
 * the list at the bottom (two opposite corners, and the pane empty until you
 * clicked); grounds opening inline (which pushed the row you had just clicked off
 * the top); and this. The difference from the first is that the list is wide now
 * and 상세 is one named place rather than an inspector that swapped contents
 * depending on what you last touched.
 *
 * Worst first. The severity filter that used to sit above this is gone: both
 * engines answer the same question about the same code and there has never been
 * a reason to read one and not the other.
 */

/** This run read against another one, when a comparison is on. */
export interface Comparison {
  /** Here and not in the other run. */
  fresh: Set<string>;
  /** In the other run and gone from this one. */
  fixed: UiFinding[];
}

export default function FindingList({
  findings,
  openId,
  compare,
  onOpen,
  onNavigate,
  emptyHint,
}: {
  findings: UiFinding[];
  /** The finding whose grounds are showing; also what the editor is marking. */
  openId: string | null;
  compare?: Comparison | null;
  /** Splice the proposed fix into the file. Absent when there is no run to write to. */
  onApply?: (finding: UiFinding) => void;
  /** Ask the model for code, when the finding came without any. */
  onPropose?: (finding: UiFinding) => void;
  proposing?: boolean;
  applying?: boolean;
  onOpen: (finding: UiFinding | null) => void;
  onNavigate: (file: string, line: number) => void;
  emptyHint: React.ReactNode;
}) {
  const openRow = useRef<HTMLLIElement | null>(null);

  // Keep the chosen row on screen. It matters less than it did -- the grounds
  // used to open *inside* this list and push everything down, including the row
  // you had just clicked -- but a row selected from the editor's gutter or from
  // a link can still be below the fold.
  useEffect(() => {
    if (openId) openRow.current?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [openId]);

  const fixed = compare?.fixed ?? [];

  if (findings.length === 0 && fixed.length === 0) {
    return (
      <div className="flex items-start gap-2.5 px-3 py-4">
        <ShieldCheck className="mt-0.5 size-4 shrink-0 text-ink-faint" />
        <div className="text-xs leading-relaxed text-ink-faint">{emptyHint}</div>
      </div>
    );
  }

  return (
    <>
      {fixed.length > 0 && <Fixed findings={fixed} />}
      {findings.length === 0 && (
        <div className="flex items-start gap-2.5 px-3 py-4">
          <ShieldCheck className="mt-0.5 size-4 shrink-0 text-ink-faint" />
          <div className="text-xs leading-relaxed text-ink-faint">{emptyHint}</div>
        </div>
      )}
      <ul>
      {sortFindings(findings).map((finding) => {
        const open = finding.id === openId;
        return (
          <li
            key={finding.id}
            ref={open ? openRow : undefined}
            className="border-b border-line/60 last:border-b-0"
          >
            {/* Nothing sticky any more: the grounds are in 상세 on the right, so
                nothing expands underneath this row for it to stay above. */}
            <button
              type="button"
              // A selection, not a disclosure. Nothing unfolds here: the row
              // says which problem 상세 is showing, and `aria-expanded` on a
              // control that expands nothing tells a screen reader to wait for
              // something that never arrives.
              aria-current={open ? "true" : undefined}
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
              {/* Pointing right, and it stays there: it means "opens in 상세",
                  which is where it points. Rotating it would promise that the
                  row itself is about to unfold. */}
              <ChevronRight
                className={cn("mt-0.5 size-3 shrink-0 transition-colors", open ? "text-accent-ink" : "text-ink-faint")}
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
                  <VerdictOf finding={finding} />
                  {/* Two units reading the same code and reaching the same
                      conclusion. This was two identical rows -- same title,
                      same CWE, same line -- which reads as the tool being
                      confused rather than as two readings agreeing. */}
                  {finding.mergedIds.length > 0 && (
                    <span title="여러 단위에서 같은 문제가 보고되었습니다">
                      {finding.mergedIds.length + 1}개 단위에서 확인
                    </span>
                  )}
                  {compare &&
                    (compare.fresh.has(finding.id) ? (
                      <span className="text-accent-ink">새로</span>
                    ) : (
                      <span>그대로</span>
                    ))}
                </span>
              </span>
            </button>
          </li>
        );
      })}
      </ul>
    </>
  );
}

/**
 * What the other run had and this one does not.
 *
 * Not rows you can open: these findings are not in this run, so there are no
 * grounds to show and the lines they name have moved -- that is the point of
 * them being gone. Listed rather than counted because "3 closed" is worth
 * nothing if you cannot check which three.
 */
/** Nothing at all for an engine that has no verification step. */
function VerdictOf({ finding }: { finding: UiFinding }) {
  const standing = standingOf(finding);
  return standing ? <Verdict standing={standing} confidence={finding.confidence ?? undefined} /> : null;
}

function Fixed({ findings }: { findings: UiFinding[] }) {
  const [open, setOpen] = useState(false);

  return (
    <section className="border-b border-line bg-ok-wash/40">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
        className="flex w-full items-center gap-2 px-3 py-1.5 text-left transition-colors hover:bg-surface-2"
      >
        <ChevronRight className={cn("size-3 shrink-0 text-ink-faint transition-transform", open && "rotate-90")} />
        <span className="text-2xs font-medium text-ok">해결됨 {findings.length}건</span>
        <span className="text-2xs text-ink-faint">비교 대상 실행에는 있었고 여기에는 없습니다</span>
      </button>

      {open && (
        <ul className="pb-1.5">
          {sortFindings(findings).map((finding) => (
            <li key={finding.id} className="flex items-start gap-2 px-3 py-1 pl-8">
              <span
                title={SEVERITY_LABEL[finding.severity]}
                aria-label={SEVERITY_LABEL[finding.severity]}
                className={cn("mt-1 size-1.5 shrink-0 rounded-full opacity-50", SEVERITY_DOT[finding.severity])}
              />
              <span className="min-w-0 flex-1">
                <span className="block text-xs leading-snug text-ink-muted line-through">{finding.title}</span>
                <span className="flex flex-wrap items-center gap-x-2 text-2xs text-ink-faint">
                  {finding.cwe && <span className="font-mono">{finding.cwe}</span>}
                  <span className="font-mono">
                    {finding.primary.file}:{finding.primary.startLine}
                  </span>
                </span>
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

/**
 * How many columns the grounds get, written out.
 *
 * Tailwind scans for literal class names, so these cannot be interpolated. 근거
 * is the wide one: it is the argument, and the other two are a paragraph each.
 */
const COLUMNS = {
  1: "",
  2: "@2xl:grid-cols-[1fr_1.25fr]",
  3: "@2xl:grid-cols-[1fr_1.25fr_1fr]",
} as const;

/**
 * Why the agent said it: the explanation, the trail, the neighbours, the fix.
 *
 * Two columns where there is room for them, one where there is not, and that is
 * the whole reason this is a container query rather than a breakpoint: the same
 * component has to read in the right-hand 상세 pane, which is a few hundred
 * pixels somebody dragged, and it used to live in a dock as wide as the window.
 * `lg:` would go to two columns on a wide window with 상세 pulled in narrow,
 * which is exactly backwards.
 *
 * The patch is deliberately not one of the columns -- it scrolls inside its own
 * box, so a long diff makes this taller rather than wider.
 */
export function Grounds({
  finding,
  knowledge,
  onNavigate,
  onApply,
  onPropose,
  proposing,
  applying,
}: {
  finding: UiFinding;
  knowledge?: KnowledgeGraph;
  onNavigate: (file: string, line: number) => void;
  onApply?: (finding: UiFinding) => void;
  /** Ask the model for code, when the finding came without any. */
  onPropose?: (finding: UiFinding) => void;
  proposing?: boolean;
  applying?: boolean;
}) {
  // The callers and callees of the unit this sits in. Computed here because the
  // whole graph is already in the cache -- the server can do it and does not
  // expose it, and a walk beats a round trip per opened finding.
  const related = knowledge && finding.chunkId ? neighbours(knowledge, finding.chunkId, 1) : [];

  const hasTrail = finding.evidence.length > 0;
  const hasFix = Boolean(finding.remediation) || related.length > 0;
  const patch = finding.diff;
  // The fix is no longer one of the columns. It holds a patch, and a patch in a
  // third of the dock scrolled sideways to show a line that would have fitted
  // whole -- while 근거, two sentences long, reserved another third and left it
  // empty down to the bottom of the tallest column.
  const columns = (1 + (hasTrail ? 1 : 0)) as keyof typeof COLUMNS;

  return (
    <div className="@container space-y-4 px-3 pb-3 pl-8">
      <div className={cn("grid items-start gap-x-6 gap-y-4", COLUMNS[columns])}>
        <section className="min-w-0 space-y-2">
          <h4 className="text-2xs text-ink-muted">판단</h4>
          <p className="text-xs leading-relaxed whitespace-pre-wrap text-ink-muted">{finding.explanation}</p>

        </section>

        {hasTrail && (
          <section className="min-w-0 space-y-1">
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

      </div>

      {hasFix && (
        <section className="min-w-0 space-y-3 border-t border-line pt-3">
          {finding.remediation && (
            <div className="space-y-1">
              <h4 className="text-2xs text-ink-muted">고치는 방법</h4>
              <p className="max-w-prose text-xs leading-relaxed whitespace-pre-wrap text-ink-muted">
                {finding.remediation}
              </p>
            </div>
          )}

          {patch && (
            <div className="space-y-2">
              {/* The patch before the button, always. This writes to the reader's
                  source; offering to do that without showing what would change is
                  asking for a decision nobody can make. */}
              <Patch diff={patch} className="max-h-56" />
              {onApply && (
                <Button size="xs" variant="outline" disabled={applying} onClick={() => onApply(finding)}>
                  <Wrench />
                  {applying ? "적용하는 중…" : "이대로 고치기"}
                </Button>
              )}
            </div>
          )}

          {/* A finding whose fix did not fit the lines it is anchored to arrives
              with a paragraph and nothing to press. Telling somebody how to fix
              their code is not fixing it. */}
          {!patch && onPropose && (
            <Button size="xs" variant="outline" disabled={proposing} onClick={() => onPropose(finding)}>
              <Wrench />
              {proposing ? "만드는 중…" : "고칠 코드 만들기"}
            </Button>
          )}

          {related.length > 0 && (
              <div className="space-y-1">
                <h4 className="text-2xs text-ink-muted">관련 코드</h4>
                <ul className="flex flex-wrap gap-1">
                  {related.slice(0, 12).map((node) => (
                    <li key={node.id}>
                      <button
                        type="button"
                        // A node with no span is still worth opening; it just
                        // has no line to land on, and 0 would be a wrong one.
                        onClick={() => onNavigate(node.file, node.attrs?.start_line ?? 0)}
                        className="rounded-sm border border-line px-1.5 py-0.5 font-mono text-2xs text-ink-muted transition-colors hover:border-line-3 hover:text-ink"
                        title={`${node.file}${node.attrs ? `:${node.attrs.start_line}` : ""}`}
                      >
                        {node.label}
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
          )}
        </section>
      )}
    </div>
  );
}
