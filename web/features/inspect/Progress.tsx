"use client";

import { Loader2, Play, Square } from "lucide-react";

import FindingRow from "@/features/inspect/FindingRow";
import { Button } from "@/components/ui/button";
import { Progress as Bar } from "@/components/ui/progress";
import { phaseOf, progressOf } from "@/lib/inspect/stage";
import { sortFindings, type UiFinding } from "@/lib/model/finding";
import { useResume } from "@/lib/run/trace-queries";
import { useRunStream } from "@/lib/run/stream";
import { useRunId } from "@/lib/run/use-run-id";

/**
 * A scan in flight, and what it has found so far.
 *
 * The findings are the point of this screen, not the bar. A scan of a real
 * repository takes minutes and the first critical finding often lands in the
 * first twenty seconds, so the list is live and reading it early costs nothing --
 * the rows here are the same rows the results table shows, so nothing has to be
 * re-learned when the scan ends.
 *
 * Everything comes off the event stream (`lib/run/stream`), which patches the
 * findings query as `chunk_finished` arrives. Nothing here polls.
 */
export default function Progress({ findings }: { findings: UiFinding[] }) {
  const [runId] = useRunId();
  const { live, ensureAttached } = useRunStream();
  const resume = useResume(runId, ensureAttached);

  const phase = phaseOf(live);
  const { done, total, fraction } = progressOf(live);
  const rows = sortFindings(findings);

  return (
    <div className="min-h-0 flex-1 overflow-auto">
      <div className="mx-auto w-full max-w-3xl px-6 py-8">
        <div className="flex items-start gap-3">
          <Loader2 className="mt-0.5 size-4 shrink-0 animate-spin text-accent-ink" aria-hidden />
          <div className="min-w-0 flex-1">
            <p className="text-sm font-medium text-ink-strong">{phase ?? "검사 중"}</p>
            <p className="mt-0.5 font-mono text-2xs text-ink-faint">
              {total > 0 ? `${done.toLocaleString()} / ${total.toLocaleString()} 단위` : "범위를 정하는 중"}
              {live.scanned.size > 0 && ` · 파일 ${live.scanned.size}`}
            </p>
          </div>
          {live.interrupted ? (
            <Button size="sm" onClick={() => resume.mutate({ action: "resume" })}>
              <Play className="size-3.5" />
              이어서
            </Button>
          ) : (
            <Button size="sm" variant="outline" onClick={() => resume.mutate({ action: "abort" })}>
              <Square className="size-3.5" />
              중단
            </Button>
          )}
        </div>

        {/* Indeterminate until the total is known, rather than a bar sitting at
            zero -- which reads as stuck rather than as counting. */}
        {fraction !== null && <Bar value={fraction * 100} className="mt-4" />}

        {live.error && <p className="mt-4 text-xs text-danger">{live.error}</p>}

        <div className="mt-8">
          <h2 className="text-xs font-semibold text-ink-strong">
            지금까지 찾은 것
            <span className="ml-1.5 font-mono text-2xs font-normal text-ink-faint">{rows.length}</span>
          </h2>
          {rows.length === 0 ? (
            <p className="mt-3 text-xs text-ink-faint">
              아직 없습니다. 읽은 단위 대부분은 아무 문제가 없고, 그것도 결과입니다.
            </p>
          ) : (
            <ul className="mt-2 divide-y divide-line rounded-md border border-line bg-surface">
              {rows.map((finding) => (
                <li key={finding.id}>
                  {/* Readable, not tickable. The patch routes build from the
                      saved report, which does not exist until the run ends --
                      so a bucket assembled here could not be exported anyway,
                      and a tick that leads to a 409 is worse than no tick. */}
                  <FindingRow finding={finding} />
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
