"use client";

import { CirclePause, Loader2, Pencil, Wrench } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Progress } from "@/components/ui/progress";
import { isTruncated } from "@/lib/api/types";
import type { AgentStep, NodeNote } from "@/lib/api/types";
import type { RunLive, RunPhase } from "@/lib/run/reduce";
import { type Exchange, type ToolRun, type Unit, seconds } from "@/lib/trace/process";
import { parseReply } from "@/lib/trace/reply";
import { cn } from "@/lib/utils";

/**
 * The run as a chat thread.
 *
 * Messages, from named senders, in the order they were sent. The orchestrator
 * hands a unit of code to an agent; the agent answers, or asks a tool something
 * and answers once it has the reply. Every bubble on the right was sent *to* an
 * agent and every bubble on the left came *from* one, which is the whole of the
 * reading instruction.
 *
 * Two things this is not, both of which it was. Not a table: a row of metadata
 * with the payload folded away is a log, and the message is the point. And not a
 * summary: a tool loop's passes are shown one after another -- wanted the
 * definition, read it, wanted the caller -- rather than as one reply and a list of
 * three calls, because the order is what makes it an argument rather than a tally.
 *
 * Senders are named by the id the agent uses for itself. `lens:injection` is what
 * the span metadata says, what the prompt is filed under and what a breakpoint is
 * set on; a translated name would be a second name for one agent.
 *
 * No markdown renderer anywhere. A message may contain a diff or an injected
 * prompt, and rendering that as formatting is how a reader stops being able to see
 * what was actually said.
 */

/** Past this a thread is scrolled through rather than read. */
const TURN_CAP = 40;

/** Lines of a long message shown before it has to be asked for. */
const CLAMP_LINES = 8;

export default function ChatPane({
  units,
  steps,
  phase,
  live,
  node,
  note,
  selected,
  onTunePrompt,
}: {
  units: Unit[];
  steps: AgentStep[];
  phase: RunPhase;
  live: RunLive;
  /** Narrowed to one node of the graph, if anything is. */
  node: string | null;
  /** What that node is, when one is picked. */
  note?: NodeNote;
  /** The call the prompt editor is on: `?span=` in the address bar. */
  selected: string | null;
  onTunePrompt: (spanId: string) => void;
}) {
  const running = phase === "running" || phase === "starting";

  return (
    <div className="flex h-full min-h-0 flex-col bg-surface">
      <Status phase={phase} live={live} />

      <div className="min-h-0 flex-1 overflow-auto">
        {note && <NodeCard note={note} />}

        {units.length === 0 ? (
          <div className="space-y-3 p-3">
            <p className="text-xs leading-relaxed text-ink-faint">
              {node
                ? `${node} 에서 이뤄진 대화가 없습니다.`
                : running
                  ? "첫 응답을 기다리고 있습니다."
                  : "‘검사 실행’을 누르면 에이전트끼리 주고받은 대화가 여기 쌓입니다."}
            </p>
            <Roster steps={steps} />
          </div>
        ) : (
          units.map((unit) => (
            <Thread key={unit.id} unit={unit} selected={selected} onTunePrompt={onTunePrompt} />
          ))
        )}
      </div>
    </div>
  );
}

/**
 * What one node of the graph is.
 *
 * Shown when the drawing is narrowed to a node, and it is the whole answer for five
 * of them: `plan`, `context`, `skip`, `locate` and `reduce` call no model, so they
 * have no prompt, no reply and no tools, and nothing of them reaches a trace. They
 * looked like agents that had done nothing.
 *
 * `routes` is read off the compiled graph on the server, so it is the edges that
 * actually exist rather than a description of them.
 */
function NodeCard({ note }: { note: NodeNote }) {
  return (
    <section className="space-y-1.5 border-b border-line bg-surface-2 px-3 py-2.5">
      <header className="flex items-center gap-2">
        <h3 className="font-mono text-xs font-semibold text-ink-strong">{note.node}</h3>
        <span
          className={cn(
            "rounded-sm px-1 font-mono text-2xs",
            note.agent ? "bg-accent-wash text-accent-ink" : "bg-surface-3 text-ink-faint",
          )}
        >
          {note.agent ? "agent" : "code"}
        </span>
        {note.agent && (
          <span className="font-mono text-2xs text-ink-faint">
            {note.calls} {note.calls === 1 ? "call" : "calls"}
            {note.tools > 0 ? ` · ${note.tools} tools` : ""}
          </span>
        )}
      </header>

      {note.does && <p className="text-xs leading-relaxed text-ink-muted">{note.does}</p>}

      <dl className="space-y-0.5 font-mono text-2xs">
        {note.steps.length > 0 && <Fact term="steps" value={note.steps.join(" · ")} />}
        {note.reads.length > 0 && <Fact term="reads" value={note.reads.join(", ")} />}
        {note.writes.length > 0 && <Fact term="writes" value={note.writes.join(", ")} />}
        {note.rule && <Fact term={note.router ?? "next"} value={note.rule} />}
        {note.routes.length > 0 && <Fact term="→" value={note.routes.join(", ")} />}
      </dl>
    </section>
  );
}

function Fact({ term, value }: { term: string; value: string }) {
  return (
    <div className="flex gap-2">
      <dt className="w-14 shrink-0 text-ink-faint">{term}</dt>
      <dd className="min-w-0 flex-1 break-words text-ink-muted">{value}</dd>
    </div>
  );
}

/** One code unit's thread, headed by the unit the whole conversation is about. */
function Thread({
  unit,
  selected,
  onTunePrompt,
}: {
  unit: Unit;
  selected: string | null;
  onTunePrompt: (spanId: string) => void;
}) {
  return (
    <section>
      {/* Sticky, because a long thread scrolls past its own subject and "which
          function is this about" is the first thing you lose. */}
      <header className="sticky top-0 z-10 flex items-baseline gap-2 border-y border-line bg-surface-2 px-3 py-1.5">
        <h3 className="truncate font-mono text-xs font-semibold text-ink-strong">{unit.symbol ?? unit.id}</h3>
        {unit.file && <span className="truncate font-mono text-2xs text-ink-faint">{unit.file}</span>}
        {unit.tokens > 0 && (
          <span className="ml-auto shrink-0 font-mono text-2xs text-ink-faint">{unit.tokens.toLocaleString()} tok</span>
        )}
      </header>

      <ol className="space-y-4 px-3 py-3">
        {unit.exchanges.slice(0, TURN_CAP).map((exchange) => (
          <Turn
            key={exchange.id}
            exchange={exchange}
            unit={unit.symbol ?? unit.id}
            highlighted={exchange.id === selected}
            onTunePrompt={() => onTunePrompt(exchange.id)}
          />
        ))}
        {unit.exchanges.length > TURN_CAP && (
          <li className="font-mono text-2xs text-ink-faint">+{unit.exchanges.length - TURN_CAP} more</li>
        )}
      </ol>
    </section>
  );
}

/**
 * One agent's part of the thread: what it was sent, and everything it said back.
 */
function Turn({
  exchange,
  unit,
  highlighted,
  onTunePrompt,
}: {
  exchange: Exchange;
  /** The thread's own subject, so a message does not repeat it. */
  unit: string;
  highlighted: boolean;
  onTunePrompt: () => void;
}) {
  const subject = exchange.subject === unit ? "" : exchange.subject;
  const answer = parseReply(exchange.reply);
  // A tool loop is a conversation and is shown as one. Everything else said one
  // thing once, so its rounds would be a single message repeating the answer.
  const conversational = exchange.calls.length > 0;

  return (
    <li className={cn("group/turn space-y-2 rounded-md", highlighted && "-mx-1.5 bg-accent-wash px-1.5 py-1.5")}>
      <Bubble
        side="right"
        sender={`orchestrator → ${exchange.step}`}
        aside={subject}
        tone="sent"
        action={
          <Button
            size="icon-xs"
            variant="ghost"
            title="프롬프트 고쳐 다시 실행"
            aria-label="프롬프트 고쳐 다시 실행"
            onClick={onTunePrompt}
            className="opacity-0 transition-opacity group-hover/turn:opacity-100 focus-visible:opacity-100"
          >
            <Pencil className="text-ink-faint" />
          </Button>
        }
      >
        <Long text={exchange.user} />
        {exchange.system && <System text={exchange.system} />}
      </Bubble>

      {conversational
        ? exchange.rounds.map((round, index) => (
            <div key={index} className="space-y-2">
              {round.said && (
                <Bubble side="left" sender={exchange.step} aside={index === 0 ? senderAside(exchange) : ""}>
                  <Long text={round.said} />
                </Bubble>
              )}
              {round.calls.map((call, at) => (
                <ToolExchange key={at} step={exchange.step} call={call} />
              ))}
            </div>
          ))
        : null}

      {!conversational && (
        <Bubble side="left" sender={exchange.step} aside={senderAside(exchange)}>
          {answer.kind === "empty" && <p className="font-mono text-2xs text-ink-faint">(no reply)</p>}
          {answer.kind === "blank" && <p className="font-mono text-2xs text-ink-muted">{answer.text}</p>}
          {answer.kind === "text" && <Long text={answer.text} />}
          {answer.kind === "fields" && (
            <dl className="space-y-1">
              {answer.fields.map((field) => (
                <div key={field.key} className="flex gap-2">
                  <dt className="shrink-0 font-mono text-2xs text-ink-faint">{field.key}</dt>
                  <dd className="min-w-0 flex-1 text-xs text-ink">
                    {field.value !== undefined ? (
                      <span className="leading-relaxed whitespace-pre-wrap">{field.value}</span>
                    ) : (
                      <Fold label={field.nested?.summary ?? ""}>
                        <Long text={field.nested?.json ?? ""} mono />
                      </Fold>
                    )}
                  </dd>
                </div>
              ))}
            </dl>
          )}
        </Bubble>
      )}

      {exchange.error && (
        <p className="pl-1 font-mono text-2xs text-danger">{exchange.error}</p>
      )}

      <Footnote exchange={exchange} />
    </li>
  );
}

/** `← triage`, `← lens:injection` -- who handed this agent the work. */
function senderAside(exchange: Exchange): string {
  return exchange.from.length > 0 ? `← ${exchange.from.join(" + ")}` : "";
}

/**
 * One message.
 *
 * `sent` sits right and quiet; a reply sits left and is the thing being read. The
 * sender is above the bubble rather than inside it, so a wall of text never pushes
 * the name out of view.
 */
function Bubble({
  side,
  sender,
  aside,
  tone = "said",
  action,
  children,
}: {
  side: "left" | "right";
  sender: string;
  aside?: string;
  tone?: "sent" | "said";
  action?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div className={cn("flex flex-col gap-1", side === "right" ? "items-end" : "items-start")}>
      <div className="flex w-full items-center gap-1.5">
        {side === "left" && <span className="size-1.5 shrink-0 rounded-full bg-accent" aria-hidden />}
        <span
          className={cn(
            "min-w-0 truncate font-mono text-2xs",
            side === "left" ? "font-semibold text-accent-ink" : "ml-auto text-ink-faint",
          )}
        >
          {sender}
        </span>
        {aside && <span className="shrink-0 font-mono text-2xs text-ink-faint">{aside}</span>}
        {action}
      </div>
      <div
        className={cn(
          "max-w-[92%] min-w-0 rounded-lg px-2.5 py-2",
          tone === "sent" ? "rounded-tr-none bg-field" : "rounded-tl-none bg-surface-2",
        )}
      >
        {children}
      </div>
    </div>
  );
}

/**
 * A message long enough to bury the ones after it.
 *
 * Clamped, not folded: the first lines are on screen as a message, and the rest is
 * one click away. A context pack runs to thousands of characters, and hiding it
 * behind a row of metadata was how the sent message stopped being visible at all.
 */
function Long({ text, mono }: { text: string; mono?: boolean }) {
  const [open, setOpen] = useState(false);
  const lines = text.split("\n");
  const long = lines.length > CLAMP_LINES || text.length > 600;
  const shown = open || !long ? text : lines.slice(0, CLAMP_LINES).join("\n").slice(0, 600);

  return (
    <div className="space-y-1">
      <pre
        className={cn(
          "overflow-x-auto text-xs leading-relaxed whitespace-pre-wrap",
          mono ? "font-mono text-2xs text-ink-muted" : "font-sans text-ink",
        )}
      >
        {shown || "(empty)"}
      </pre>
      {long && (
        <button
          type="button"
          onClick={() => setOpen(!open)}
          className="font-mono text-2xs text-ink-faint hover:text-ink-muted"
        >
          {open ? "접기" : `더 보기 · ${text.length.toLocaleString()} chars`}
        </button>
      )}
    </div>
  );
}

/** The standing instructions, which are the same for every unit this agent reads. */
function System({ text }: { text: string }) {
  return (
    <Fold label={`system ${text.length.toLocaleString()} chars`}>
      <Long text={text} mono />
    </Fold>
  );
}

/** An agent asking a tool something, and the tool answering. */
function ToolExchange({ step, call }: { step: string; call: ToolRun }) {
  return (
    <div className="space-y-1 border-l-2 border-line-2 pl-2.5">
      <div className="flex items-center gap-1.5 font-mono text-2xs">
        <Wrench className="size-3 shrink-0 text-alt" />
        <span className="shrink-0 text-ink-faint">{step} →</span>
        <span className="shrink-0 text-alt">{call.name}</span>
        {call.latency_ms !== null && <span className="ml-auto shrink-0 text-ink-faint">{seconds(call.latency_ms)}</span>}
      </div>
      <pre className="overflow-x-auto rounded-sm bg-field px-2 py-1 font-mono text-2xs whitespace-pre-wrap text-ink-muted">
        {argsOf(call.args)}
      </pre>

      <div className="flex items-center gap-1.5 font-mono text-2xs text-ink-faint">
        <span>{call.name} →</span>
        <span>{step}</span>
      </div>
      {call.error ? (
        <p className="font-mono text-2xs text-danger">{call.error}</p>
      ) : (
        <div className="rounded-sm bg-field px-2 py-1">
          <Long text={resultText(call.outputs)} mono />
        </div>
      )}
    </div>
  );
}

/** Whatever the tool answered, as text. The store's truncation is kept visible. */
function resultText(outputs: unknown): string {
  if (outputs === null || outputs === undefined) return "(empty)";
  if (typeof outputs === "string") return outputs;
  if (isTruncated(outputs)) return `${outputs.preview}\n\n… ${outputs._chars.toLocaleString()} chars, truncated at 20,000`;
  return JSON.stringify(outputs, null, 2);
}

/** `path="net.c", start_line=15` -- the call as it was made. */
function argsOf(args: Record<string, unknown>): string {
  const parts = Object.entries(args).map(([key, value]) => `${key}=${JSON.stringify(value)}`);
  return parts.length > 0 ? parts.join("\n") : "(no arguments)";
}

/**
 * What became of this turn: where it went, and what it was allowed to reach for.
 *
 * Under the messages rather than in them, because it is about the exchange rather
 * than part of it.
 */
function Footnote({ exchange }: { exchange: Exchange }) {
  const bits: React.ReactNode[] = [];
  if (exchange.to.length > 0) bits.push(<span key="to" className="text-alt">→ {exchange.to.join(", ")}</span>);
  if (exchange.attempts > 1) bits.push(<span key="n">{exchange.attempts} calls</span>);
  if (exchange.retried > 0) bits.push(<span key="r">{exchange.retried} retried</span>);
  if (exchange.tokens) bits.push(<span key="t">{exchange.tokens.toLocaleString()} tok</span>);
  bits.push(<span key="ms">{seconds(exchange.latency_ms)}</span>);

  return (
    <div className="flex flex-wrap items-center gap-x-2 pl-3 font-mono text-2xs text-ink-faint">
      {bits}
      {exchange.offered.length > 0 && (
        <Fold label={`tools ${exchange.offered.length} available, ${exchange.calls.length} called`}>
          <ul className="mt-1 space-y-0.5 rounded-sm bg-field p-2">
            {exchange.offered.map((tool) => (
              <li key={tool.name} className="flex gap-2 text-2xs">
                <span className="w-28 shrink-0 font-mono text-alt">{tool.name}</span>
                <span className="min-w-0 flex-1 text-ink-faint">{tool.summary}</span>
              </li>
            ))}
          </ul>
        </Fold>
      )}
    </div>
  );
}

/** A disclosure, for the things that are genuinely asides. */
function Fold({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <Collapsible>
      <CollapsibleTrigger className="font-mono text-2xs text-ink-faint underline decoration-dotted hover:text-ink-muted">
        {label}
      </CollapsibleTrigger>
      <CollapsibleContent>{children}</CollapsibleContent>
    </Collapsible>
  );
}

/** Every agent in the run and what it holds. Before a run, when that is the question. */
function Roster({ steps }: { steps: AgentStep[] }) {
  if (steps.length === 0) return null;

  return (
    <Fold label={`${steps.filter((each) => each.enabled).length} agents`}>
      <ul className="mt-1 space-y-1 rounded-sm border border-line bg-field p-2 font-mono text-2xs">
        {steps.map((step) => (
          <li key={step.step} className="flex flex-wrap items-baseline gap-x-2">
            <span className={cn("w-28 shrink-0", step.enabled ? "text-ink" : "text-ink-faint line-through")}>
              {step.step}
            </span>
            <span className="text-ink-faint">→ {step.schema ?? "text"}</span>
            {step.tools.length > 0 && (
              <span className="text-alt">
                {step.tools.length} tools, max {step.max_tool_calls}
              </span>
            )}
          </li>
        ))}
      </ul>
    </Fold>
  );
}

const PHASE_LABEL: Record<RunPhase, string | null> = {
  idle: null,
  starting: "시작하는 중",
  running: "검사 중",
  paused: "중단점에서 멈춤",
  finished: "검사 완료",
  failed: "검사 실패",
};

const PHASE_TONE: Record<RunPhase, string> = {
  idle: "",
  starting: "text-ink-muted",
  running: "text-accent-ink",
  paused: "text-warn",
  finished: "text-ok",
  failed: "text-danger",
};

/** Where the run is, above the thread it is producing. */
function Status({ phase, live }: { phase: RunPhase; live: RunLive }) {
  const label = PHASE_LABEL[phase];
  if (!label && !live.refusal) return null;

  const chunk = live.chunk;
  const done = chunk && chunk.total > 0 ? chunk.total - chunk.remaining : null;
  const busy = phase === "running" || phase === "starting";
  // The node names as the graph and the stream spell them. Deduplicated, because
  // four verifiers in flight is one activity.
  const doing = [...new Set(live.running)].join(", ");

  return (
    <div className="shrink-0 space-y-1.5 border-b border-line px-3 py-2">
      {label && (
        <div className="flex items-center gap-1.5 text-xs">
          {busy && <Loader2 className="size-3 shrink-0 animate-spin text-accent-ink" />}
          <span className={cn("font-medium", PHASE_TONE[phase])}>{label}</span>
          {busy && doing && <span className="truncate font-mono text-2xs text-ink-faint">{doing}</span>}
          {done !== null && chunk && (
            <span className="ml-auto shrink-0 font-mono text-2xs text-ink-faint">
              {done}/{chunk.total}
            </span>
          )}
        </div>
      )}
      {busy && done !== null && chunk && chunk.total > 0 && (
        <Progress value={(done / chunk.total) * 100} className="h-1" />
      )}
      {/* The one thing the deleted status strip said that nothing else did. */}
      {!live.attached && live.active && <p className="text-2xs text-warn">연결 끊김 · 다시 연결 중</p>}
      {live.refusal && (
        <p className="flex items-start gap-1.5 text-2xs text-ink">
          <CirclePause className="mt-px size-3 shrink-0 text-warn" />
          {live.refusal}
        </p>
      )}
    </div>
  );
}
