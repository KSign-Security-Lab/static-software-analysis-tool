"use client";

import { ChevronRight, CirclePause, Loader2, Pencil, Wrench } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Progress } from "@/components/ui/progress";
import type { AgentStep, NodeNote, PromptRow } from "@/lib/api/types";
import type { RunLive, RunPhase } from "@/lib/run/reduce";
import { type Outcome, outcomeOf, unitOutcome } from "@/lib/trace/outcome";
import { type Exchange, type ToolRun, type Unit, labelOf, seconds } from "@/lib/trace/process";
import { parseReply } from "@/lib/trace/reply";
import { toolResult, whereOf } from "@/lib/trace/tool-result";
import { cn } from "@/lib/utils";

/**
 * The run.
 *
 * Rewritten twice. It was a chat -- senders, bubbles, sent on the right and said
 * on the left -- which spent a 368px pane on a spatial grammar answering questions
 * nobody had, since every prompt is from the orchestrator and the alternation is a
 * pipeline drawn on a canvas one pane over. Replacing the bubbles with a rail fixed
 * the alignment and left the real problem untouched: it was still one scroll of
 * everything, and a run is 4 units × 5 steps × (a schema reply, a tool loop, a
 * 2,000-character brief). Nothing could be seen without reading all of it.
 *
 * Three levels now, each one line until asked:
 *
 *   run    -- what it did, in a strip
 *   unit   -- one row: name, what became of it, cost
 *   step   -- one row: what it is, what it decided
 *   detail -- the reply in full, what it ran, what it was asked
 *
 * The rows are worth not opening, which is the whole bet. `분석 안 함`,
 * `1건 제기`, `반박을 견딤 · 95%` -- see `outcome.ts`, and note that it is the one
 * place the schema's vocabulary is translated. The record keeps the schema's own
 * field names, because the record is the record.
 *
 * Opening a finding scopes this to the chain that produced it -- see `trailOf` --
 * and it is the same tree, filtered: one unit, its steps, opened, because a
 * question that specific has already asked to be let in.
 */

/** Past this a unit is scrolled through rather than read. */
const TURN_CAP = 40;

/** Lines of a long block shown before it has to be asked for. */
const CLAMP_LINES = 6;

const TONE: Record<Outcome["tone"], string> = {
  plain: "text-ink",
  quiet: "text-ink-faint",
  ok: "text-ok",
  danger: "text-danger",
};

export default function RunPane({
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
  // Scoped to a finding, or down to a single unit by any other route: there is
  // nothing to choose between, so the choosing step is skipped.
  const opened = Boolean(focus?.scoped) || units.length === 1;

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
                    : "‘검사 실행’을 누르면 에이전트가 무엇을 했는지 여기 쌓입니다."}
            </p>
            <Roster steps={steps} />
          </div>
        ) : (
          <>
            {!opened && <Tally units={units} />}
            <ul>
              {units.map((unit) => (
                <UnitRow
                  key={unit.id}
                  unit={unit}
                  open={opened}
                  selected={selected}
                  onTunePrompt={onTunePrompt}
                />
              ))}
            </ul>
          </>
        )}
      </div>
    </div>
  );
}

/**
 * What the run came to, over every unit on screen.
 *
 * Counted here rather than read off `RunStats`, because it has to agree with the
 * rows underneath it: narrowed to a node, this is that node's tally and not the
 * run's, and a strip that disagreed with the list it heads would be worse than
 * no strip.
 */
function Tally({ units }: { units: Unit[] }) {
  const calls = units.reduce((sum, unit) => sum + unit.exchanges.length, 0);
  const tokens = units.reduce((sum, unit) => sum + unit.tokens, 0);
  const tools = units.reduce(
    (sum, unit) => sum + unit.exchanges.reduce((n, each) => n + each.calls.length, 0),
    0,
  );

  const bits = [`단위 ${units.length}`, `호출 ${calls}`];
  if (tools > 0) bits.push(`도구 ${tools}`);
  if (tokens > 0) bits.push(`${tokens.toLocaleString()} tok`);

  return <p className="border-b border-line px-3 py-1.5 font-mono text-2xs text-ink-faint">{bits.join(" · ")}</p>;
}

/**
 * Which finding the record is narrowed to, and the way out.
 *
 * One line: the chain that produced the finding is the unit's own row and its
 * steps, right underneath, so stating it here as well was stating it twice.
 */
function Focus({ focus }: { focus: { title: string; scoped: boolean; onScoped: (next: boolean) => void } }) {
  return (
    <div className="flex shrink-0 items-center gap-2 border-b border-line bg-accent-wash px-3 py-1.5">
      <p className="min-w-0 flex-1 truncate text-2xs text-ink-muted">
        {focus.scoped ? `‘${focus.title}’ 을 찾아낸 과정` : "실행 전체"}
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

/* -- unit -------------------------------------------------------------------- */

/** One code unit: a row that says what became of it, and its steps when opened. */
function UnitRow({
  unit,
  open,
  selected,
  onTunePrompt,
}: {
  unit: Unit;
  open: boolean;
  selected: string | null;
  onTunePrompt: (spanId: string) => void;
}) {
  const outcome = unitOutcome(unit.exchanges);
  // Only when it says something the symbol does not. A file chunk's symbol *is*
  // its filename, and `main.c main.c` was the header on every one of them.
  const file = unit.file && unit.file !== unit.symbol ? unit.file : null;

  return (
    <li className="border-b border-line">
      <Collapsible defaultOpen={open}>
        <CollapsibleTrigger className="group/unit flex w-full items-baseline gap-2 px-3 py-2 text-left hover:bg-surface-2">
          <ChevronRight
            className="size-3 shrink-0 self-center text-ink-faint transition-transform group-data-[state=open]/unit:rotate-90"
            aria-hidden
          />
          <span className="min-w-0 truncate font-mono text-xs font-semibold text-ink-strong">
            {unit.symbol ?? unit.id}
          </span>
          {file && <span className="min-w-0 shrink truncate font-mono text-2xs text-ink-faint">{file}</span>}
          <span className="ml-auto flex shrink-0 items-baseline gap-2">
            {outcome && <span className={cn("text-2xs", TONE[outcome.tone])}>{outcome.text}</span>}
            {unit.tokens > 0 && (
              <span className="font-mono text-2xs text-ink-faint">{unit.tokens.toLocaleString()}</span>
            )}
          </span>
        </CollapsibleTrigger>

        <CollapsibleContent>
          <ul className="pb-1">
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
              <li className="px-3 py-1 pl-8 font-mono text-2xs text-ink-faint">
                +{unit.exchanges.length - TURN_CAP} more
              </li>
            )}
          </ul>
        </CollapsibleContent>
      </Collapsible>
    </li>
  );
}

/* -- step -------------------------------------------------------------------- */

/** One step: a row that says what it decided, and the whole of it when opened. */
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
  const outcome = outcomeOf(exchange);
  const subject = exchange.subject === unit ? "" : exchange.subject;

  return (
    <li className={cn(highlighted && "bg-accent-wash")}>
      <Collapsible defaultOpen={highlighted}>
        <div className="group/step flex items-baseline">
          <CollapsibleTrigger className="group/row flex min-w-0 flex-1 items-baseline gap-2 py-1 pr-2 pl-3 text-left hover:bg-surface-2">
            <ChevronRight
              className="size-3 shrink-0 self-center text-ink-faint transition-transform group-data-[state=open]/row:rotate-90"
              aria-hidden
            />
            <span className="shrink-0 text-xs text-ink-muted">{labelOf(exchange)}</span>
            <span className="ml-auto min-w-0 truncate text-right text-2xs">
              {exchange.error ? (
                <span className="text-danger">실패</span>
              ) : outcome ? (
                <span className={TONE[outcome.tone]}>{outcome.text}</span>
              ) : (
                <span className="font-mono text-ink-faint">{subject}</span>
              )}
            </span>
          </CollapsibleTrigger>
          <Button
            size="icon-xs"
            variant="ghost"
            title="프롬프트 고쳐 다시 실행"
            aria-label="프롬프트 고쳐 다시 실행"
            onClick={onTunePrompt}
            className="mr-1 shrink-0 self-center opacity-0 transition-opacity group-hover/step:opacity-100 focus-visible:opacity-100"
          >
            <Pencil className="text-ink-faint" />
          </Button>
        </div>

        <CollapsibleContent>
          <div className="space-y-2 border-l border-line py-2 pr-3 pl-3 ml-[22px]">
            {/* The agent's own id for this call, which the closed row has no width
                for and which is what a prompt is filed under and a breakpoint set
                on. With the subject when there is one: `gather · CWE-122 main.c:6`. */}
            <p className="font-mono text-2xs text-ink-faint">{[exchange.step, subject].filter(Boolean).join(" · ")}</p>
            <Detail exchange={exchange} />
            {exchange.error && <p className="font-mono text-2xs text-danger">{exchange.error}</p>}
            <Meta exchange={exchange} />
            <Sent exchange={exchange} />
          </div>
        </CollapsibleContent>
      </Collapsible>
    </li>
  );
}

/**
 * What the step actually said.
 *
 * A tool loop said it over several passes and the passes are the argument --
 * wanted the definition, read it, wanted the caller -- so those stay in order
 * rather than folding into one reply and a tally of calls. Everything else said
 * one thing once.
 */
function Detail({ exchange }: { exchange: Exchange }) {
  const looped = exchange.rounds.some((round) => round.calls.length > 0);

  if (!looped) return <Reply text={exchange.reply} />;

  return (
    <div className="space-y-2">
      {exchange.rounds.map((round, index) => (
        <div key={index} className="space-y-2">
          {round.said && <Reply text={round.said} />}
          {round.calls.map((call, at) => (
            <ToolCall key={at} call={call} />
          ))}
        </div>
      ))}
    </div>
  );
}

/**
 * One thing an agent said, as the shape it said it in.
 *
 * Every reply goes through here, including the passes of a tool loop -- which is
 * the fix for `gather` ending its loop with 1,106 characters of raw JSON on
 * screen. A loop's last pass is usually the structured answer and its earlier
 * passes are prose; `parseReply` tells them apart already, and the loop branch was
 * simply not asking it.
 */
function Reply({ text }: { text: string | null }) {
  const answer = parseReply(text);

  if (answer.kind === "empty") return <p className="font-mono text-2xs text-ink-faint">(no reply)</p>;
  if (answer.kind === "blank") return <p className="font-mono text-2xs text-ink-muted">{answer.text}</p>;
  if (answer.kind === "text") return <Clamp text={answer.text} />;

  return (
    <dl className="space-y-1.5">
      {answer.fields.map((field) => {
        // Inline while it fits, stacked when it does not. `refuted` above `false`
        // is two lines to carry one word, and a paragraph of reasoning crammed
        // beside its key is the fixed-column problem all over again.
        const short = field.value !== undefined && field.value.length <= 32 && !field.value.includes("\n");
        return (
          <div key={field.key} className={cn(short && "flex flex-wrap items-baseline gap-x-2")}>
            {/* The schema's own field names, kept: a Korean gloss here would be a
                second name for what the prompt asks for and the editor edits. The
                summary on the closed row is where the translation belongs. */}
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
        );
      })}
    </dl>
  );
}

/**
 * An agent asking a tool something, and what came back.
 *
 * The answer is rendered as the facts it is. `find_definition("shorten")` replies
 * with 295 characters of indented JSON headed by a `chunk_id`, to say that shorten
 * is at util.c:2-6 and here is its body -- so that is what it says now, and the
 * body arrives as code rather than as a string with `\n` in it.
 */
function ToolCall({ call }: { call: ToolRun }) {
  const result = toolResult(call.outputs);

  return (
    <div className="space-y-1 rounded-sm bg-field px-2 py-1.5">
      <div className="flex items-baseline gap-1.5 font-mono text-2xs">
        <Wrench className="size-3 shrink-0 self-center text-alt" aria-hidden />
        <span className="shrink-0 text-alt">{call.name}</span>
        <span className="min-w-0 flex-1 truncate text-ink-faint">{argsOf(call.args)}</span>
        {call.latency_ms !== null && <span className="shrink-0 text-ink-faint">{seconds(call.latency_ms)}</span>}
      </div>

      {call.error ? (
        <p className="font-mono text-2xs text-danger">{call.error}</p>
      ) : result.kind === "empty" ? (
        <p className="font-mono text-2xs text-ink-faint">없음</p>
      ) : result.kind === "units" ? (
        <ul className="space-y-1">
          {result.units.map((found, at) => (
            <li key={at} className="space-y-0.5">
              <p className="flex flex-wrap items-baseline gap-x-1.5 font-mono text-2xs">
                <span className="text-ink">{found.symbol}</span>
                <span className="text-ink-faint">{whereOf(found)}</span>
                {found.kind && <span className="text-ink-faint">{found.kind}</span>}
              </p>
              {found.body && <Clamp text={found.body} mono />}
            </li>
          ))}
        </ul>
      ) : (
        <Clamp text={result.text} mono />
      )}
    </div>
  );
}

/** Where this step went, and what it spent. One line of numbers. */
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
 * Both halves in one disclosure. The standing half is per *step kind*, not per
 * call -- the same 1,461 characters on every unit -- and it is on the node card in
 * full, where it is a fact about the node rather than the fourteenth copy of one.
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

/** A block long enough to bury what comes after it. Clamped, not hidden. */
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
  const tools = mine
    .flatMap((step) => step.tools)
    .filter((tool, index, all) => all.findIndex((other) => other.name === tool.name) === index);
  // What it must answer in. A property of the role -- 선별 answers which
  // specialists, a specialist answers findings -- and the shape is enforced by
  // guided decoding, so it is a fact about the node rather than a hope.
  const shapes = mine
    .filter((step) => step.schema)
    .map((step) => `${step.schema}(${step.schema_fields.join(", ")})`);
  // The standing instructions: the node's role in the most literal sense
  // available, the text it is actually run under.
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
