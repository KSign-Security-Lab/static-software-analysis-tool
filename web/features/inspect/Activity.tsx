"use client";

import { FileCode2, Loader2, Wrench } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { activeAgents, filesInFlight, filesScanned, recentTools } from "@/lib/inspect/agents";
import { useSpans } from "@/lib/run/trace-queries";
import { useRunStream } from "@/lib/run/stream";
import { useRunId } from "@/lib/run/use-run-id";
import { cn } from "@/lib/utils";

export default function Activity() {
  const [runId] = useRunId();
  const { live } = useRunStream();
  const spans = useSpans(runId);

  const agents = activeAgents(live);
  const inflight = filesInFlight(live);
  const scanned = filesScanned(live);
  const tools = recentTools(spans.data?.spans ?? []);
  const reading = inflight.length > 0;
  const files = reading ? inflight : scanned.slice(0, 6);

  return (
    <div className="grid gap-4 sm:grid-cols-2">
      <section className="space-y-1.5">
        <h3 className="text-2xs font-semibold tracking-wide text-ink-faint">지금 일하는 에이전트</h3>
        {agents.length === 0 ? (
          <p className="text-xs text-ink-faint">다음 단위를 고르는 중입니다.</p>
        ) : (
          <ul className="space-y-1">
            {agents.map((agent) => (
              <li key={agent.node} className="flex items-baseline gap-1.5">
                <Loader2 className="mt-0.5 size-3 shrink-0 animate-spin text-accent-ink" aria-hidden />
                <span className={cn("text-xs", agent.lens ? "text-ink-strong" : "text-ink")}>{agent.label}</span>
                {agent.count > 1 && <span className="text-2xs text-ink-muted">×{agent.count}</span>}
                <span className="font-mono text-2xs text-ink-faint">{agent.node}</span>
              </li>
            ))}
          </ul>
        )}

        <h3 className="pt-2 text-2xs font-semibold tracking-wide text-ink-faint">
          {reading ? "읽고 있는 파일" : "읽은 파일"}
          {!reading && scanned.length > 0 && (
            <span className="ml-1.5 font-mono font-normal text-ink-faint">{scanned.length}</span>
          )}
        </h3>
        {files.length === 0 ? (
          <p className="text-xs text-ink-faint">—</p>
        ) : (
          <ul className="space-y-0.5">
            {files.map((file) => (
              <li key={file} className="flex items-baseline gap-1.5">
                <FileCode2 className="mt-0.5 size-3 shrink-0 text-ink-faint" aria-hidden />
                <span className="min-w-0 truncate font-mono text-2xs text-ink-muted">{file}</span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="space-y-1.5">
        <h3 className="text-2xs font-semibold tracking-wide text-ink-faint">
          부른 도구
          {spans.data && (
            <span className="ml-1.5 font-mono font-normal text-ink-faint">
              {spans.data.summary.tool_calls.toLocaleString()}
            </span>
          )}
        </h3>
        {tools.length === 0 ? (
          <p className="text-xs text-ink-faint">아직 없습니다.</p>
        ) : (
          <ul className="space-y-1">
            {tools.map((tool) => (
              <li key={tool.id} className="flex items-baseline gap-1.5">
                <Wrench
                  className={cn(
                    "mt-0.5 size-3 shrink-0",
                    tool.failed ? "text-danger" : tool.running ? "text-accent-ink" : "text-ink-faint",
                  )}
                  aria-hidden
                />
                <span className="font-mono text-2xs text-ink">{tool.name}</span>
                {tool.subject && (
                  <span className="min-w-0 flex-1 truncate font-mono text-2xs text-ink-faint">{tool.subject}</span>
                )}
                {tool.running ? (
                  <Badge variant="outline" className="shrink-0 px-1 py-0 text-2xs font-normal text-ink-faint">
                    진행 중
                  </Badge>
                ) : (
                  tool.latencyMs !== null && (
                    <span className="shrink-0 font-mono text-2xs text-ink-faint">{tool.latencyMs}ms</span>
                  )
                )}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
