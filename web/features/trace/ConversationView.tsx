"use client";

import { useMemo } from "react";

import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import { Badge } from "@/components/ui/badge";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import type { Thread, Turn } from "@/lib/api/types";
import { seconds } from "@/lib/trace/tree";
import { Payload } from "./Payload";

/**
 * The same run, read as conversations.
 *
 * One accordion item per chunk thread. Forty chunks used to be forty open
 * walls of <pre>, which is why the collapse matters more than virtualization
 * here -- and why, with it, virtualization is not needed.
 *
 * Model output is shown literally, never through a markdown renderer. It may
 * contain a diff, or an injected prompt, and rendering that as formatting is
 * how a reader stops being able to see what the model actually said.
 */

const PRE = "max-h-64 overflow-auto rounded-sm bg-field p-2 font-mono text-2xs leading-relaxed whitespace-pre-wrap text-ink-muted";

/** Beyond this a single thread is scrolled past rather than read. */
const TURN_CAP = 50;

function TurnView({ turn }: { turn: Turn }) {
  const system = turn.messages.filter((m) => m.role === "system");
  const rest = turn.messages.filter((m) => m.role !== "system");

  return (
    <li className="border-t border-line/60 py-2 first:border-t-0">
      <div className="mb-1 flex items-center gap-2 text-2xs text-ink-faint">
        <span className="font-mono text-ink-muted">{turn.step || turn.name}</span>
        {turn.tokens ? <span>{turn.tokens} tok</span> : null}
        <span>{seconds(turn.latency_ms)}</span>
        {turn.error && <span className="text-danger">{turn.error}</span>}
      </div>

      {system.length > 0 && (
        <Collapsible>
          <CollapsibleTrigger className="mb-1 text-2xs text-ink-faint hover:text-ink-muted">
            시스템 프롬프트 보기
          </CollapsibleTrigger>
          <CollapsibleContent>
            <pre className={PRE}>{system.map((m) => m.content).join("\n\n")}</pre>
          </CollapsibleContent>
        </Collapsible>
      )}

      {rest.map((message, index) => (
        <pre key={index} className={PRE}>
          {message.content}
        </pre>
      ))}

      {turn.reply && (
        <div className="mt-1.5 border-l-2 border-accent pl-2">
          <pre className={PRE}>{turn.reply}</pre>
        </div>
      )}

      {turn.tools.length > 0 && (
        <ul className="mt-1.5 space-y-1">
          {turn.tools.map((tool, index) => (
            <li key={index} className="rounded-sm border border-line px-2 py-1">
              <div className="flex items-center gap-2 text-2xs">
                <span className="font-mono text-alt">{tool.name}</span>
                <span className="text-ink-faint">{seconds(tool.latency_ms)}</span>
                {tool.error && <span className="text-danger">{tool.error}</span>}
              </div>
              <Payload value={tool.outputs} className={PRE} />
            </li>
          ))}
        </ul>
      )}
    </li>
  );
}

export default function ConversationView({ threads, node }: { threads: Thread[]; node: string | null }) {
  const shown = useMemo(
    () => (node ? threads.filter((thread) => thread.id === node || thread.turns.some((t) => t.name.startsWith(node))) : threads),
    [threads, node],
  );

  if (shown.length === 0) {
    return <p className="p-4 text-xs text-ink-faint">모델과 주고받은 대화가 아직 없습니다. 검사를 실행하면 호출 순서대로 여기 쌓입니다.</p>;
  }

  return (
    <Accordion type="multiple" defaultValue={[shown[0].id]} className="px-2.5 py-1">
      {shown.map((thread) => (
        <AccordionItem key={thread.id} value={thread.id}>
          <AccordionTrigger className="py-2 text-xs">
            <span className="flex min-w-0 items-center gap-2">
              <span className="truncate font-medium">{thread.symbol ?? thread.id}</span>
              {thread.file && <span className="truncate font-mono text-2xs text-ink-faint">{thread.file}</span>}
              <Badge variant="outline" className="shrink-0 px-1 py-0 text-2xs font-normal">
                {thread.turns.length}턴
              </Badge>
              {thread.tokens > 0 && <span className="shrink-0 text-2xs text-ink-faint">{thread.tokens} tok</span>}
            </span>
          </AccordionTrigger>
          <AccordionContent>
            <ul>
              {thread.turns.slice(0, TURN_CAP).map((turn) => (
                <TurnView key={turn.id} turn={turn} />
              ))}
            </ul>
            {thread.turns.length > TURN_CAP && (
              <p className="py-2 text-2xs text-ink-faint">
                {thread.turns.length - TURN_CAP}턴 더 있습니다. 호출 순서 보기에서 전부 볼 수 있습니다.
              </p>
            )}
          </AccordionContent>
        </AccordionItem>
      ))}
    </Accordion>
  );
}
