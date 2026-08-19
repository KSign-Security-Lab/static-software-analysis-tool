"use client";

import { useEffect, useRef, useState } from "react";
import { Play, Square, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { useStartSweep, useStopSweep, useSweep } from "@/lib/bench/queries";
import { clear, useSelection } from "@/lib/bench/selection";
import type { Dataset, Instance } from "@/lib/bench/types";
import { describeError } from "@/lib/api/client";
import { cn } from "@/lib/utils";

/**
 * Starting a long job from a web page, and coming back to it.
 *
 * The run is a detached process on the server with its own session and its own
 * log, so closing the tab, restarting the API and losing the network all leave
 * it running. Everything shown here is read off that log, which is why the
 * panel says the same thing in a browser opened tomorrow as in the one that
 * pressed the button.
 *
 * It does not survive the machine rebooting, and the panel says so rather than
 * implying a durability it does not have.
 */
export default function Sweep({ dataset, instances }: { dataset: Dataset; instances: Instance[] }) {
  const status = useSweep();
  const start = useStartSweep();
  const stop = useStopSweep();
  const chosen = useSelection(dataset.id);
  const [force, setForce] = useState(false);

  if (!status.data) return null;
  const { running, position, of, instance, started_at, log, chose, split } = status.data;
  // One log, one machine: what it holds is the last run of either split. Saying
  // so beats a panel on the OSS page quietly showing two hundred CVE instances.
  const elsewhere = !running && split && split !== dataset.split;
  const busy = start.isPending || stop.isPending;
  const failed = start.error || stop.error;

  // Ticking instances that are already done is how you ask for them again, so
  // the offer to redo them only appears when there are some.
  const done = new Set(instances.filter((i) => i.outcome !== "not_run").map((i) => i.id));
  const redoing = chosen.filter((id) => done.has(id)).length;

  return (
    <section className="rounded-md border border-line bg-surface-2">
      <header className="flex items-center justify-between gap-4 p-3">
        <div className="min-w-0">
          <h2 className="flex items-center gap-2 text-2xs font-medium text-ink-muted">
            {running && <span className="size-1.5 shrink-0 animate-pulse rounded-full bg-accent" />}
            {running ? "돌고 있습니다" : "멈춰 있습니다"}
          </h2>
          <p className="truncate pt-1 text-xs text-ink">
            {running ? (
              <>
                {position && of && (
                  <span className="font-mono text-ink-strong">
                    {position}/{of}
                  </span>
                )}
                <span className="pl-2 font-mono text-ink-muted">{instance ?? "준비 중"}</span>
                {chose.length > 0 && <span className="pl-2 text-ink-faint">· 고른 {chose.length}건</span>}
                {started_at && <span className="pl-2 text-ink-faint">· {elapsed(started_at)} 경과</span>}
              </>
            ) : (
              <span className="text-ink-muted">
                브라우저를 닫아도 계속 돕니다. 이미 끝난 건은 건너뛰므로 중단해도 이어서 진행됩니다.
              </span>
            )}
          </p>
        </div>
        {running ? (
          <Button variant="outline" size="xs" disabled={busy} onClick={() => stop.mutate()}>
            <Square /> 중지
          </Button>
        ) : (
          <Button
            size="xs"
            disabled={busy}
            onClick={() => start.mutate({ instances: chosen, split: dataset.split, force })}
          >
            <Play />
            {chosen.length > 0 ? `고른 ${chosen.length}건 실행` : `${dataset.total}건 전부 실행`}
          </Button>
        )}
      </header>

      {!running && chosen.length > 0 && (
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-line px-3 py-2">
          <button
            type="button"
            className="flex items-center gap-1 text-2xs text-ink-faint hover:text-ink"
            onClick={() => clear(dataset.id)}
          >
            <X className="size-3" /> 선택 해제
          </button>
          {redoing > 0 && (
            <label className="flex items-center gap-1.5 text-2xs text-ink-muted">
              <Checkbox checked={force} onCheckedChange={(value) => setForce(value === true)} />
              이미 끝난 {redoing}건도 다시 돌리기
              <span className="text-ink-faint">— 이미지를 다시 받습니다</span>
            </label>
          )}
        </div>
      )}

      {failed && <p className="px-3 pb-2 text-2xs text-warn">{describeError(failed)}</p>}
      {elsewhere && (
        <p className="border-t border-line px-3 py-1.5 text-2xs text-ink-faint">
          아래 기록은 다른 쪽({split}) 실행입니다 — 로그는 둘이 함께 씁니다.
        </p>
      )}
      {log.length > 0 && <Log lines={log} running={running} />}
    </section>
  );
}

/**
 * The tail of the sweep's log.
 *
 * The one thing a long run owes whoever left it: some sign it is alive and
 * some idea of what went wrong when it is not. Follows the bottom while it is
 * running and stops following once it stops, so a finished run can be read
 * without the view yanking back down.
 */
function Log({ lines, running }: { lines: string[]; running: boolean }) {
  const box = useRef<HTMLPreElement>(null);

  useEffect(() => {
    if (running && box.current) box.current.scrollTop = box.current.scrollHeight;
  }, [lines, running]);

  return (
    <pre
      ref={box}
      className="max-h-52 overflow-auto border-t border-line px-3 py-2 font-mono text-2xs leading-relaxed whitespace-pre-wrap text-ink-faint"
    >
      {lines.map((line, index) => (
        <span key={index} className={cn("block", tone(line))}>
          {line}
        </span>
      ))}
    </pre>
  );
}

/** The lines worth finding by eye in a wall of INFO. */
function tone(line: string): string {
  if (/^(red|ERROR|.*refusing to start)/.test(line) || line.includes("ERROR")) return "text-warn";
  if (line.startsWith("== ") || /bench: \[\d+\//.test(line)) return "text-ink";
  return "";
}

function elapsed(since: number): string {
  const seconds = Math.max(0, Math.floor(Date.now() / 1000 - since));
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  return hours > 0 ? `${hours}시간 ${minutes}분` : `${minutes}분`;
}
