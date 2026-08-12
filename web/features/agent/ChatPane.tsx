"use client";

import { ChevronRight, CirclePause, Loader2, Pencil, Wrench } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Progress } from "@/components/ui/progress";
import { isTruncated } from "@/lib/api/types";
import type { AgentStep, NodeNote, PromptRow } from "@/lib/api/types";
import type { RunLive, RunPhase } from "@/lib/run/reduce";
import { type Exchange, type ToolRun, type Unit, labelOf, seconds } from "@/lib/trace/process";
import { parseReply } from "@/lib/trace/reply";
import { cn } from "@/lib/utils";

/**
 * The run, as the record of a pipeline.
 *
 * This was drawn as a chat: senders, bubbles, sent on the right and said on the
 * left. The metaphor was wrong and the pane was hard to read because of it.
 *
 * A chat's spatial grammar buys you two things -- who spoke, and turn-taking --
 * and neither is in question here. Every prompt is from the orchestrator and every
 * reply is from the step named beside it; the alternation is the pipeline, which is
 * fixed and known. What it cost was everything else: right-aligned senders and
 * 92%-width bubbles alternating sides meant nothing shared a left edge, in a pane
 * 368 pixels wide, and one step came to 4 stacked blocks -- sender, prompt bubble,
 * answer bubble, footnote -- with 14 steps in a run and no spine to hang them on.
 *
 * Worse, it put the emphasis exactly backwards. A step's prompt is a *template*:
 * `이것은 보안 전문가의 시간을 들일 만합니까?` is identical on all four units, and
 * the code inside it is already open two panes to the left, wrapped here to a width
 * that breaks its own line-number gutter. It was rendered first, and four times
 * taller than the answer, which is the one part of a step that is news.
 *
 * So: one step, one row, on a rail. The answer leads. What was sent is one
 * disclosure, because it is reference rather than reading. A unit says in its header
 * what became of it, so the run can be scanned rather than read through.
 *
 * Kept from the chat, because both were right: the order is the argument -- a tool
 * loop shows its passes one after another, not as a tally -- and nothing is rendered
 * as markdown, because a reply may contain a diff or an injected prompt and
 * formatting it is how a reader stops seeing what was actually said.
 */

/** Past this a unit is scrolled through rather than read. */
const TURN_CAP = 40;

/** Lines of a long block shown before it has to be asked for. */
const CLAMP_LINES = 6;

export default function ChatPane({
  units,
  steps,
  prompts,
  phase,
  live,
  node,
  note,
  focus,
  selected,
  onTunePrompt,
}: {
  units: Unit[];
  steps: AgentStep[];
  /** The standing briefs, so a node can show the one it runs under. */
  prompts: PromptRow[];
  phase: RunPhase;
  live: RunLive;
  /** Narrowed to one node of the graph, if anything is. */
  node: string | null;
  /** What that node is, when one is picked. */
  note?: NodeNote;
  /** The finding being read in the dock, and whether this is narrowed to it. */
  focus?: { title: string; scoped: boolean; onScoped: (next: boolean) => void } | null;
  /** The call the prompt editor is on: `?span=` in the address bar. */
  selected: string | null;
  onTunePrompt: (spanId: string) => void;
}) {
  const running = phase === "running" || phase === "starting";

  return (
    <div className="flex h-full min-h-0 flex-col bg-surface">
      <Status phase={phase} live={live} />
      {focus && <Focus focus={focus} />}

      <div className="min-h-0 flex-1 overflow-auto">
        {note && <NodeCard note={note} steps={steps} prompts={prompts} />}

        {units.length === 0 ? (
          <div className="space-y-3 p-3">
            <p className="text-xs leading-relaxed text-ink-faint">
              {focus?.scoped
                ? // Likely rather than exotic: a re-run reuses cached units, and a
                  // cached unit is not re-read, so it leaves no conversation behind
                  // in this run even though its findings are in the report.
                  "이 문제를 낸 단위의 대화가 이 실행에는 없습니다. 지난 검사 결과를 그대로 가져왔을 수 있습니다."
                : node
                  ? `${node} 에서 이뤄진 대화가 없습니다.`
                  : running
                    ? "첫 응답을 기다리고 있습니다."
                    : "‘검사 실행’을 누르면 에이전트끼리 주고받은 대화가 여기 쌓입니다."}
            </p>
            <Roster steps={steps} />
          </div>
        ) : (
          units.map((unit) => (
            <UnitBlock key={unit.id} unit={unit} selected={selected} onTunePrompt={onTunePrompt} />
          ))
        )}
      </div>
    </div>
  );
}

/**
 * Which finding the transcript is narrowed to, and the way out.
 *
 * One line, because the chain that produced the finding is on the unit's own
 * header now -- every unit states its path, and a scoped pane has exactly one
 * unit, so saying it twice was saying it twice.
 */
function Focus({ focus }: { focus: { title: string; scoped: boolean; onScoped: (next: boolean) => void } }) {
  return (
    <div className="flex shrink-0 items-center gap-2 border-b border-line bg-accent-wash px-3 py-1.5">
      <p className="min-w-0 flex-1 truncate text-2xs text-ink-muted">
        {focus.scoped ? `‘${focus.title}’ 을 찾아낸 과정` : "실행 전체의 기록"}
      </p>
      <Button
        size="xs"
        variant="ghost"
        className="shrink-0"
        onClick={() => focus.onScoped(!focus.scoped)}
        aria-pressed={focus.scoped}
      >
        {focus.scoped ? "전체 보기" : "이 문제만"}
      </Button>
    </div>
  );
}

/* -- one unit ---------------------------------------------------------------- */

/**
 * One code unit and every step taken over it.
 *
 * The header carries the path the unit took -- `선별 → memory 가 제기 → 근거 모으기
 * → 판정` -- so a run can be scanned. Four units used to be four indistinguishable
 * walls of prompt text, and which of them was screened out in one call and which
 * went the whole way was a thing you found out by reading all of both.
 */
function UnitBlock({
  unit,
  selected,
  onTunePrompt,
}: {
  unit: Unit;
  selected: string | null;
  onTunePrompt: (spanId: string) => void;
}) {
  const path = unit.exchanges.map(labelOf).filter((role, at, all) => all.indexOf(role) === at);
  // Only when it says something the symbol does not. A file chunk's symbol *is*
  // its filename, and `main.c main.c` was the header on every one of them.
  const file = unit.file && unit.file !== unit.symbol ? unit.file : null;

  return (
    <section>
      {/* Sticky, because a long unit scrolls past its own subject and "which
          function is this about" is the first thing you lose. */}
      <header className="sticky top-0 z-10 space-y-0.5 border-y border-line bg-surface-2 px-3 py-1.5">
        <div className="flex items-baseline gap-2">
          <h3 className="min-w-0 truncate font-mono text-xs font-semibold text-ink-strong">
            {unit.symbol ?? unit.id}
          </h3>
          {file && <span className="min-w-0 truncate font-mono text-2xs text-ink-faint">{file}</span>}
          {unit.tokens > 0 && (
            <span className="ml-auto shrink-0 font-mono text-2xs text-ink-faint">
              {unit.tokens.toLocaleString()} tok
            </span>
          )}
        </div>
        {path.length > 0 && <p className="text-2xs leading-snug text-accent-ink">{path.join(" → ")}</p>}
      </header>

      <ol className="px-3 py-2">
        {unit.exchanges.slice(0, TURN_CAP).map((exchange) => (
          <StepRow
            key={exchange.id}
            exchange={exchange}
            unit={unit.symbol ?? unit.id}
            highlighted={exchange.id === selected}
            onTunePrompt={() => onTunePrompt(exchange.id)}
          />
        ))}
        {unit.exchanges.length > TURN_CAP && (
          <li className="pl-4 font-mono text-2xs text-ink-faint">+{unit.exchanges.length - TURN_CAP} more</li>
        )}
      </ol>
    </section>
  );
}

/**
 * One step: what it concluded, what it ran to get there, and what it was asked.
 *
 * In that order, which is the whole of the change. The conclusion is the news; the
 * calls are the working; the brief is reference, and a template besides.
 *
 * On a rail rather than in boxes. Fourteen steps need to read as a sequence, and a
 * 1px line with a dot per step does that in no horizontal space at all -- where
 * bubbles cost an indent, a max-width and an alignment each.
 */
function StepRow({
  exchange,
  unit,
  highlighted,
  onTunePrompt,
}: {
  exchange: Exchange;
  /** The unit's own name, so a step does not repeat it as its subject. */
  unit: string;
  highlighted: boolean;
  onTunePrompt: () => void;
}) {
  const answer = parseReply(exchange.reply);
  const subject = exchange.subject === unit ? "" : exchange.subject;

  return (
    <li
      className={cn(
        "group/step relative border-l border-line pb-3 pl-4 last:border-transparent last:pb-0",
        highlighted && "bg-accent-wash",
      )}
    >
      <span
        className={cn(
          "absolute top-[7px] -left-[3.5px] size-[7px] rounded-full",
          exchange.error ? "bg-danger" : "bg-accent",
        )}
        aria-hidden
      />

      <div className="flex items-baseline gap-1.5">
        <h4 className="shrink-0 text-xs font-semibold text-ink-strong">{labelOf(exchange)}</h4>
        <span className="min-w-0 truncate font-mono text-2xs text-ink-faint">{subject || exchange.step}</span>
        <Button
          size="icon-xs"
          variant="ghost"
          title="프롬프트 고쳐 다시 실행"
          aria-label="프롬프트 고쳐 다시 실행"
          onClick={onTunePrompt}
          className="ml-auto shrink-0 opacity-0 transition-opacity group-hover/step:opacity-100 focus-visible:opacity-100"
        >
          <Pencil className="text-ink-faint" />
        </Button>
      </div>

      <div className="mt-1 space-y-1.5">
        <Answer answer={answer} rounds={exchange.rounds} />
        {exchange.error && <p className="font-mono text-2xs text-danger">{exchange.error}</p>}
        <Meta exchange={exchange} />
        <Sent exchange={exchange} />
      </div>
    </li>
  );
}

/**
 * What the step concluded.
 *
 * A tool loop concluded it over several passes and the passes are the argument --
 * wanted the definition, read it, wanted the caller -- so those are shown in order
 * rather than folded into one reply and a list of calls. Everything else said one
 * thing once, and its rounds would be one message repeating the answer.
 */
function Answer({ answer, rounds }: { answer: ReturnType<typeof parseReply>; rounds: Exchange["rounds"] }) {
  const looped = rounds.some((round) => round.calls.length > 0);

  if (looped) {
    return (
      <div className="space-y-1.5">
        {rounds.map((round, index) => (
          <div key={index} className="space-y-1.5">
            {round.said && <Clamp text={round.said} />}
            {round.calls.map((call, at) => (
              <ToolCall key={at} call={call} />
            ))}
          </div>
        ))}
      </div>
    );
  }

  if (answer.kind === "empty") return <p className="font-mono text-2xs text-ink-faint">(no reply)</p>;
  if (answer.kind === "blank") return <p className="font-mono text-2xs text-ink-muted">{answer.text}</p>;
  if (answer.kind === "text") return <Clamp text={answer.text} />;

  return (
    <dl className="space-y-1">
      {answer.fields.map((field) => (
        // Wrapping rather than a fixed key column: `worth_analysing` is 15
        // characters of mono and used to squeeze the value it labelled into
        // nothing. A long key now takes the line and the value gets the next one.
        <div key={field.key} className="flex flex-wrap items-baseline gap-x-2">
          <dt className="shrink-0 font-mono text-2xs text-ink-faint">{field.key}</dt>
          <dd className="min-w-0 flex-1 text-xs leading-relaxed text-ink">
            {field.value !== undefined ? (
              <span className="whitespace-pre-wrap">{field.value}</span>
            ) : (
              <Fold label={field.nested?.summary ?? ""}>
                <Clamp text={field.nested?.json ?? ""} mono />
              </Fold>
            )}
          </dd>
        </div>
      ))}
    </dl>
  );
}

/** An agent asking a tool something, and the tool answering. */
function ToolCall({ call }: { call: ToolRun }) {
  return (
    <div className="space-y-1 rounded-sm bg-field px-2 py-1.5">
      <div className="flex items-baseline gap-1.5 font-mono text-2xs">
        <Wrench className="size-3 shrink-0 self-center text-alt" aria-hidden />
        <span className="min-w-0 truncate text-alt">{call.name}</span>
        <span className="min-w-0 flex-1 truncate text-ink-faint">{argsOf(call.args)}</span>
        {call.latency_ms !== null && (
          <span className="shrink-0 text-ink-faint">{seconds(call.latency_ms)}</span>
        )}
      </div>
      {call.error ? (
        <p className="font-mono text-2xs text-danger">{call.error}</p>
      ) : (
        // The tool's answer is the evidence, so it stays on screen rather than
        // going behind a fold -- clamped, which is the same bargain the prompts
        // get and the reason `step → tool` and `tool → step` labels are gone: in
        // a box under the call there was only ever one direction it could be.
        <Clamp text={resultText(call.outputs)} mono />
      )}
    </div>
  );
}

/**
 * Where this step went, and what it spent.
 *
 * One line of numbers. `← triage` is not among them: every step already says what
 * fed it by sitting under it on the rail, and the unit's header names the whole
 * path in order.
 */
function Meta({ exchange }: { exchange: Exchange }) {
  const bits: string[] = [];
  if (exchange.attempts > 1) bits.push(`${exchange.attempts} calls`);
  if (exchange.retried > 0) bits.push(`${exchange.retried} retried`);
  if (exchange.tokens) bits.push(`${exchange.tokens.toLocaleString()} tok`);
  const time = seconds(exchange.latency_ms);
  if (time) bits.push(time);
  if (exchange.offered.length > 0) bits.push(`도구 ${exchange.calls.length}/${exchange.offered.length}`);

  if (bits.length === 0 && exchange.to.length === 0) return null;

  return (
    <p className="flex flex-wrap items-baseline gap-x-2 font-mono text-2xs text-ink-faint">
      {exchange.to.length > 0 && <span className="text-alt">→ {exchange.to.join(", ")}</span>}
      {bits.join(" · ")}
    </p>
  );
}

/**
 * The brief, folded.
 *
 * Both halves in one disclosure. They were two -- a bubble for the message and a
 * fold inside it for the standing instructions -- and the standing half is per
 * *step kind*, not per call: the same 1,461 characters on every unit, and it is on
 * the node card now, in full, where it is a fact about the node rather than the
 * fourteenth copy of one.
 */
function Sent({ exchange }: { exchange: Exchange }) {
  const size = (exchange.user.length + exchange.system.length).toLocaleString();

  return (
    <Fold label={`받은 지시 · ${size} chars`}>
      <div className="mt-1 space-y-1.5 rounded-sm bg-field p-2">
        <Clamp text={exchange.user} mono />
        {exchange.system && (
          <div className="border-t border-line pt-1.5">
            <p className="mb-1 font-mono text-2xs text-ink-faint">지시문</p>
            <Clamp text={exchange.system} mono />
          </div>
        )}
      </div>
    </Fold>
  );
}

/**
 * A block long enough to bury what comes after it.
 *
 * Clamped, not folded: the first lines are on screen and the rest is one click
 * away. Six lines rather than eight, because a step now shows its answer, its
 * calls and its brief in one column and each of them is bidding for the same
 * screen.
 */
function Clamp({ text, mono }: { text: string; mono?: boolean }) {
  const [open, setOpen] = useState(false);
  const lines = text.split("\n");
  const long = lines.length > CLAMP_LINES || text.length > 400;
  const shown = open || !long ? text : lines.slice(0, CLAMP_LINES).join("\n").slice(0, 400);

  return (
    <div className="space-y-0.5">
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
  return parts.length > 0 ? parts.join(", ") : "";
}

/** A disclosure, for the things that are genuinely asides. */
function Fold({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <Collapsible>
      <CollapsibleTrigger className="group/fold flex items-center gap-0.5 font-mono text-2xs text-ink-faint hover:text-ink-muted">
        <ChevronRight
          className="size-3 shrink-0 transition-transform group-data-[state=open]/fold:rotate-90"
          aria-hidden
        />
        {label}
      </CollapsibleTrigger>
      <CollapsibleContent>{children}</CollapsibleContent>
    </Collapsible>
  );
}

/* -- one node ---------------------------------------------------------------- */

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
function NodeCard({ note, steps, prompts }: { note: NodeNote; steps: AgentStep[]; prompts: PromptRow[] }) {
  const mine = steps.filter((step) => step.node === note.node);
  // Named, not counted. The drawing says `4 tools`, which cannot tell you the
  // run can search semantically -- and listing them on every box made five
  // specialists repeat one toolbox and shrank the whole canvas. Here is where
  // the drawing already says detail lives: "노드를 누르면 오른쪽에 그 노드가
  // 무엇인지 나옵니다".
  const tools = mine
    .flatMap((step) => step.tools)
    .filter((tool, index, all) => all.findIndex((other) => other.name === tool.name) === index);
  // What it must answer in. A property of the role -- 선별 answers which
  // specialists, a specialist answers findings -- and the shape is enforced by
  // guided decoding, so it is a fact about the node rather than a hope.
  const shapes = mine
    .filter((step) => step.schema)
    .map((step) => `${step.schema}(${step.schema_fields.join(", ")})`);
  // The standing instructions. This is the node's role in the most literal sense
  // available: the text it is actually run under.
  const briefs = mine
    .map((step) => ({ step: step.step, row: prompts.find((row) => row.name === step.prompt) }))
    .filter((each): each is { step: string; row: PromptRow } => Boolean(each.row));

  return (
    <section className="space-y-2 border-b border-line bg-surface-2 px-3 py-2.5">
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
        {shapes.length > 0 && <Fact term="answers" value={shapes.join(" · ")} />}
        {note.rule && <Fact term={note.router ?? "next"} value={note.rule} />}
        {note.routes.length > 0 && <Fact term="→" value={note.routes.join(", ")} />}
      </dl>

      {briefs.map((brief) => (
        <Fold
          key={brief.step}
          label={`${brief.step} 의 지시문 · ${brief.row.override ? "수정됨" : "기본"} · ${(
            brief.row.override ?? brief.row.default
          ).length.toLocaleString()} chars`}
        >
          <div className="mt-1 rounded-sm bg-field p-2">
            <Clamp text={brief.row.override ?? brief.row.default} mono />
          </div>
        </Fold>
      ))}

      {tools.length > 0 && (
        <div className="space-y-1">
          <h4 className="text-2xs text-ink-faint">쓸 수 있는 도구</h4>
          <ul className="space-y-1">
            {tools.map((tool) => (
              <li key={tool.name} className="flex flex-wrap items-baseline gap-x-1.5">
                <span className="font-mono text-2xs text-alt">{tool.name}</span>
                {/* The one tool that is not an index query. Tagged because "does
                    this thing have retrieval" is a question people ask of it, and
                    a summary in a list of ten does not answer it at a glance. */}
                {tool.name === "search_semantic" && (
                  <span className="rounded-sm bg-alt-wash px-1 font-mono text-2xs text-alt">RAG</span>
                )}
                {tool.summary && <span className="min-w-0 flex-1 text-2xs text-ink-faint">{tool.summary}</span>}
              </li>
            ))}
          </ul>
        </div>
      )}
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

/* -- where the run is -------------------------------------------------------- */

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

/** Where the run is, above the record it is producing. */
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
