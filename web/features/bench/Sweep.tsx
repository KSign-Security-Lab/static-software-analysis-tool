"use client";

import { useEffect, useRef } from "react";
import { Play, Square } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useStartSweep, useStopSweep, useSweep } from "@/lib/bench/queries";
import { describeError } from "@/lib/api/client";
import { cn } from "@/lib/utils";

/**
 * Starting a two-day job from a web page, and coming back to it.
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
export default function Sweep() {
  const status = useSweep();
  const start = useStartSweep();
  const stop = useStopSweep();

  if (!status.data) return null;
  const { running, position, of, instance, started_at, log } = status.data;
  const busy = start.isPending || stop.isPending;
  const failed = start.error || stop.error;

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
          <Button size="xs" disabled={busy} onClick={() => start.mutate()}>
            <Play /> 시작
          </Button>
        )}
      </header>

      {failed && <p className="px-3 pb-2 text-2xs text-warn">{describeError(failed)}</p>}
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
