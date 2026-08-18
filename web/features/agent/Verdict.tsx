"use client";

import { ChevronLeft, ChevronRight, GitCompare, Route, Wrench } from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Verdict as Standing } from "@/components/panel/verdict";
import { PanelShell } from "@/components/workbench/PanelShell";
import { ROLE_LABEL, standingOf, type UiFinding } from "@/lib/model/finding";
import { useOpenFile, useRevealLine, useSelection } from "@/lib/run/selection";
import { useCentreTab } from "@/features/agent/centre-tab";
import { cn } from "@/lib/utils";

/**
 * Is this real, and where does it hurt.
 *
 * The right column used to stack five sections into 400px -- 판단, 근거,
 * 고치는 방법 with a patch diff in it, 관련 코드, and the 판단 과정 chain -- of
 * which two were code and one was a chain. All three want width. Measured: a
 * finding's own prose is 504 to 870 characters, but its diff wraps unreadably
 * at this width and one call's prompt is 3,628 characters, which is eighty
 * lines of scrolling here against thirty-six in the centre.
 *
 * So this column keeps only what a person needs to decide whether the claim is
 * real, and hands the rest to the centre where there is room:
 *
 * - what it is, and how sure the agent is
 * - one sentence of why
 * - the evidence as a *walk* rather than a list -- one step at a time, with the
 *   editor following each ◀ ▶. Three notes stacked is a wall of prose; three
 *   steps you walk is somebody showing you round the bug.
 * - two doors: the patch, and the reasoning that produced it
 */
export default function Verdict({ finding }: { finding: UiFinding }) {
  const { clear } = useSelection();
  const [, setPath] = useOpenFile();
  const [, setLine] = useRevealLine();
  const [, setTab] = useCentreTab();

  const standing = standingOf(finding);
  const steps = finding.evidence;
  const [at, setAt] = useState(0);

  // A different finding starts its walk over. Adjusted during render rather
  // than in an effect: React re-runs this immediately, so the step counter can
  // never be a frame behind the claim it is counting.
  const [shownFor, setShownFor] = useState(finding.id);
  if (shownFor !== finding.id) {
    setShownFor(finding.id);
    setAt(0);
  }

  const step = steps[at];

  // Walking moves the editor. That is the whole point of the walk -- 유입, 전파
  // and 위험 지점 are usually three different lines and sometimes three
  // different files, and a list of them leaves the reader to do the travelling.
  useEffect(() => {
    if (!step) return;
    void setPath(step.span.file);
    void setLine(step.span.startLine > 0 ? step.span.startLine : null);
  }, [step, setPath, setLine]);

  return (
    <PanelShell
      title={<span className="font-mono text-xs">{finding.cwe ?? "문제"}</span>}
      actions={
        <Button size="icon-xs" variant="ghost" aria-label="닫기" onClick={clear}>
          <span aria-hidden>×</span>
        </Button>
      }
      bodyClassName="flex flex-col overflow-hidden"
    >
      <div className="min-h-0 flex-1 space-y-3 overflow-auto px-3 py-2.5">
        <div className="space-y-1.5">
          <h3 className="text-xs leading-snug font-medium text-ink-strong">{finding.title}</h3>
          <div className="flex items-center gap-2">
            {standing && <Standing standing={standing} confidence={finding.confidence ?? undefined} />}
            <button
              type="button"
              onClick={() => {
                void setPath(finding.primary.file);
                void setLine(finding.primary.startLine > 0 ? finding.primary.startLine : null);
              }}
              className="min-w-0 truncate font-mono text-2xs text-ink-faint hover:text-ink-muted"
            >
              {finding.primary.file}:{finding.primary.startLine}
            </button>
          </div>
        </div>

        {/* One sentence. The full explanation is two to six, and the rest of it
            is the argument the 과정 tab makes at width. */}
        <p className="text-xs leading-relaxed text-ink-muted">{firstSentence(finding.explanation)}</p>

        {steps.length > 0 && step && (
          <section className="space-y-1.5 border-t border-line pt-2.5">
            <header className="flex items-center gap-2">
              <h4 className="text-2xs text-ink-muted">근거</h4>
              <span className="font-mono text-2xs text-ink-faint">
                {at + 1}/{steps.length}
              </span>
              <span className="ml-auto flex items-center gap-0.5">
                <Button
                  size="icon-xs"
                  variant="ghost"
                  aria-label="이전 근거"
                  disabled={at === 0}
                  onClick={() => setAt((n) => Math.max(0, n - 1))}
                >
                  <ChevronLeft />
                </Button>
                <Button
                  size="icon-xs"
                  variant="ghost"
                  aria-label="다음 근거"
                  disabled={at >= steps.length - 1}
                  onClick={() => setAt((n) => Math.min(steps.length - 1, n + 1))}
                >
                  <ChevronRight />
                </Button>
              </span>
            </header>

            <p className="flex items-baseline gap-1.5">
              <span className={cn("shrink-0 text-2xs font-medium", ROLE_TONE[step.role] ?? "text-ink-muted")}>
                {ROLE_LABEL[step.role] ?? step.role}
              </span>
              <span className="min-w-0 truncate font-mono text-2xs text-ink-faint">
                {step.span.file}:{step.span.startLine}
              </span>
            </p>
            {step.note && <p className="text-2xs leading-relaxed text-ink-muted">{step.note}</p>}
          </section>
        )}
      </div>

      {/* Two doors, against the floor. Both open in the centre, because a diff
          and a chain of prompts are things that need width -- and because the
          verdict stays on screen while you read either of them. */}
      <div className="flex shrink-0 items-center gap-1 border-t border-line p-2">
        <Button size="sm" variant="outline" className="flex-1" onClick={() => void setTab("fix")}>
          {finding.diff ? <GitCompare /> : <Wrench />}
          고치기
        </Button>
        <Button size="sm" variant="outline" className="flex-1" onClick={() => void setTab("process")}>
          <Route />
          과정 보기
        </Button>
      </div>
    </PanelShell>
  );
}

/** The claim in one line. The rest is the argument, and the argument has a tab. */
function firstSentence(text: string): string {
  const end = text.search(/[.。]\s|다\.\s/);
  return end > 0 ? text.slice(0, end + 1).trim() : text;
}

/** The same five tones the evidence trail has always used. */
const ROLE_TONE: Record<string, string> = {
  source: "text-warn",
  propagation: "text-alt",
  sink: "text-danger",
  missing_check: "text-ok",
  context: "text-ink-faint",
};
