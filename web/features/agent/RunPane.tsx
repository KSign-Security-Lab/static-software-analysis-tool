"use client";

import { ChevronRight, CirclePause, Loader2, Pencil, Wrench, X } from "lucide-react";
import { useCallback, useMemo, useState } from "react";

import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Progress } from "@/components/ui/progress";
import type { AgentStep, NodeNote, PromptRow } from "@/lib/api/types";
import type { RunLive, RunPhase } from "@/lib/run/reduce";
import { type Outcome, byFile, isWholeFile, outcomeOf, unitOutcome, worst } from "@/lib/trace/outcome";
import { type Exchange, type ToolRun, type Unit, labelOf, seconds } from "@/lib/trace/process";
import { parseReply } from "@/lib/trace/reply";
import { toolResult, whereOf } from "@/lib/trace/tool-result";
import { cn } from "@/lib/utils";
import type { PaneMode } from "../trace/state";

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
  mode,
  onMode,
  phase,
  live,
  node,
  onClearNode,
  note,
  focus,
  selected,
  onTunePrompt,
}: {
  units: Unit[];
  steps: AgentStep[];
  /** The standing briefs, so a node can show the one it runs under. */
  prompts: PromptRow[];
  /** Which question the pane is answering. */
  mode: PaneMode;
  onMode: (next: PaneMode) => void;
  phase: RunPhase;
  live: RunLive;
  /** Narrowed to one node of the graph, if anything is. */
  node: string | null;
  onClearNode: () => void;
  /** What that node is, when one is picked. */
  note?: NodeNote;
  /** The finding being read in the dock, and whether this is narrowed to it. */
  focus?: { title: string; scoped: boolean; onScoped: (next: boolean) => void } | null;
  /** The call the prompt editor is on: `?span=` in the address bar. */
  selected: string | null;
  onTunePrompt: (spanId: string) => void;
}) {
  const running = phase === "running" || phase === "starting";
  // Only the steps that reached for something. The question is "what did it
  // actually go and read", and in the record that is a handful of rows scattered
  // through the whole run.
  const shown = useMemo(
    () =>
      mode === "tools"
        ? units
            .map((unit) => ({ ...unit, exchanges: unit.exchanges.filter((each) => each.calls.length > 0) }))
            .filter((unit) => unit.exchanges.length > 0)
        : units,
    [units, mode],
  );

  /**
   * Which rows are open.
   *
   * Owned here, and that is the whole repair. Every `Collapsible` below used to
   * take `defaultOpen`, which is Radix's *initial* state -- so nothing remounted
   * when the mode changed and the rows kept whatever they had opened with.
   * Loading `?pane=map` gave a folded tree; switching to 요약 gave the same URL
   * and an unfolded one. A control that does nothing is bad; a control that does
   * something only depending on how you arrived is worse.
   *
   * It also collapses the four separate answers to "why is this row open" --
   * mode, the finding scope, a lone unit, `?span=` -- into one: it is open if it
   * is in this set. Mode sets the baseline, a click overrides one row, changing
   * mode starts again.
   */
  const [open, setOpen] = useState<Set<string>>(() => baseline(shown, mode, selected));
  // Adjusted during render rather than in an effect, as `InspectorPane` does for
  // its own scope: React re-runs this immediately, before the browser paints the
  // stale tree. Keyed on everything the baseline is derived from, so a new run's
  // units reset it as surely as a new mode does.
  const signature = `${mode}|${selected ?? ""}|${shown.map((unit) => unit.id).join(",")}`;
  const [madeFor, setMadeFor] = useState(signature);
  if (madeFor !== signature) {
    setMadeFor(signature);
    setOpen(baseline(shown, mode, selected));
  }

  const toggle = useCallback((id: string, next: boolean) => {
    setOpen((current) => {
      const updated = new Set(current);
      if (next) updated.add(id);
      else updated.delete(id);
      return updated;
    });
  }, []);

  return (
    <div className="flex h-full min-h-0 flex-col bg-surface">
      <Status phase={phase} live={live} />
      <Modes mode={mode} onMode={onMode} />
      <Scope node={node} onClearNode={onClearNode} focus={focus} />

      <div className="min-h-0 flex-1 overflow-auto">
        {note && <NodeCard note={note} steps={steps} prompts={prompts} />}

        {shown.length === 0 ? (
          <div className="space-y-3 p-3">
            <p className="text-xs leading-relaxed text-ink-faint">
              {focus?.scoped
                ? // Likely rather than exotic: a re-run reuses cached units, and a
                  // cached unit is not re-read, so it leaves no conversation behind
                  // in this run even though its findings are in the report.
                  "이 문제를 낸 단위의 대화가 이 실행에는 없습니다. 지난 검사 결과를 그대로 가져왔을 수 있습니다."
                : mode === "tools"
                  ? "이 실행에서 도구를 쓴 단계가 없습니다."
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
            <Tally units={shown} />
            <ul>
              {byFile(shown).map((group) => (
                <FileRow
                  key={group.file}
                  group={group}
                  open={open}
                  onToggle={toggle}
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

/** Row ids. Stable across renders, and distinct per level so the three cannot collide. */
const fileId = (file: string) => `f:${file}`;
const unitId = (id: string) => `u:${id}`;
const stepId = (id: string) => `s:${id}`;

/**
 * What each mode opens.
 *
 * 기록 opens everything, because it is the record and was not behaving like one:
 * it opened to step *rows* and left every reply, tool call and result behind a
 * click. `Clamp` caps any one block at six lines and `받은 지시` stays folded, so
 * "everything" is the whole argument rather than the whole prompt.
 *
 * 요약 is one row per unit. 조회 has already discarded every step that did not
 * reach for something, so there is nothing left there to hide.
 */
function baseline(units: Unit[], mode: PaneMode, selected: string | null): Set<string> {
  const open = new Set<string>();
  for (const unit of units) {
    // Files always: the group is a heading, and a run whose files were shut would
    // open on nothing at all.
    open.add(fileId(unit.file ?? unit.symbol ?? unit.id));
    if (mode === "map") continue;
    open.add(unitId(unit.id));
    for (const exchange of unit.exchanges) open.add(stepId(exchange.id));
  }
  // The call the prompt editor is on, whatever the mode -- seeded here rather
  // than read again three levels down, which is what made "why is this open" a
  // question with four answers.
  if (selected) {
    open.add(stepId(selected));
    const owner = units.find((unit) => unit.exchanges.some((each) => each.id === selected));
    if (owner) {
      open.add(unitId(owner.id));
      open.add(fileId(owner.file ?? owner.symbol ?? owner.id));
    }
  }
  return open;
}

const MODES: { id: PaneMode; label: string; hint: string }[] = [
  { id: "log", label: "기록", hint: "일어난 일 전부" },
  { id: "map", label: "요약", hint: "한 줄씩, 접은 채로" },
  { id: "tools", label: "조회", hint: "도구를 쓴 단계만" },
];

/**
 * Which question the pane is answering.
 *
 * Three, and they are not densities of one view -- they are different readings.
 * `기록` is the record and is what this opens as, because a pane whose first job
 * is to be the record should not ask you to guess where to click before it has
 * said anything. `요약` is every unit on one screen for when the question is what
 * happened rather than what was said. `조회` throws away everything that is not a
 * lookup, because "what did it actually go and read" is a real question and the
 * answer is nine rows scattered through twelve screens of the other two.
 */
function Modes({ mode, onMode }: { mode: PaneMode; onMode: (next: PaneMode) => void }) {
  return (
    <div className="flex shrink-0 gap-0.5 border-b border-line px-2 py-1">
      {MODES.map((each) => (
        <button
          key={each.id}
          type="button"
          title={each.hint}
          aria-pressed={mode === each.id}
          onClick={() => onMode(each.id)}
          className={cn(
            "rounded-sm px-2 py-0.5 text-2xs transition-colors",
            mode === each.id ? "bg-accent-wash text-accent-ink" : "text-ink-faint hover:text-ink-muted",
          )}
        >
          {each.label}
        </button>
      ))}
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
 * What the pane is narrowed to, and how to stop.
 *
 * One strip, because there are two narrowings and only one of them ever said so.
 * Clicking `verify` on the canvas filtered this pane from twelve steps to two
 * and announced it nowhere: no name, no count, and no way back that did not
 * involve going to the other pane and finding the chip there. The finding scope
 * had a strip of its own, so the pane's answer to "why am I seeing less" depended
 * on which of the two had caused it.
 *
 * A chip each, each with its own way out, and nothing at all when the pane is
 * showing the whole run.
 */
function Scope({
  node,
  onClearNode,
  focus,
}: {
  node: string | null;
  onClearNode: () => void;
  focus?: { title: string; scoped: boolean; onScoped: (next: boolean) => void } | null;
}) {
  const narrowed = focus?.scoped ? focus : null;
  if (!node && !narrowed) return null;

  return (
    <div className="flex shrink-0 flex-wrap items-center gap-1 border-b border-line bg-accent-wash px-2 py-1">
      {node && <Chip label={`${node} 만 보는 중`} onClear={onClearNode} mono />}
      {narrowed && <Chip label={`‘${narrowed.title}’ 만 보는 중`} onClear={() => narrowed.onScoped(false)} />}
    </div>
  );
}

function Chip({ label, onClear, mono }: { label: string; onClear: () => void; mono?: boolean }) {
  return (
    <span className="flex min-w-0 max-w-full items-center gap-1 rounded-sm bg-surface-2 py-0.5 pr-0.5 pl-1.5 text-2xs text-ink-muted">
      <span className={cn("min-w-0 truncate", mono && "font-mono")}>{label}</span>
      <button
        type="button"
        onClick={onClear}
        aria-label={`${label} 그만두기`}
        className="shrink-0 rounded-sm p-0.5 text-ink-faint hover:bg-surface-3 hover:text-ink"
      >
        <X className="size-3" />
      </button>
    </span>
  );
}

/* -- file -------------------------------------------------------------------- */

/**
 * One file, and the units the run made of it.
 *
 * The list used to read `main.c`, `util.c`, `shorten`, `handle`: two files and
 * two functions side by side, with nothing saying which was which, or that
 * `handle` lives in `main.c`. That was the chunker showing through -- it makes a
 * unit of each file's top-level declarations *and* a unit of each function -- as
 * one flat list of things that are not the same kind of thing.
 *
 * So the file is the outer level and its units sit inside it, the file's own
 * chunk among them under the only name that distinguishes it: 최상위 선언, which
 * is what it holds. A file whose units all came out quiet says so on one line and
 * never has to be opened.
 */
function FileRow({
  group,
  open,
  onToggle,
  selected,
  onTunePrompt,
}: {
  group: { file: string; units: Unit[] };
  open: Set<string>;
  onToggle: (id: string, next: boolean) => void;
  selected: string | null;
  onTunePrompt: (spanId: string) => void;
}) {
  // The loudest, not the last: a file with a surviving claim in its second
  // function is a file with a problem, whatever its third concluded after.
  const outcome = worst(group.units.map((unit) => unitOutcome(unit.exchanges)));
  const tokens = group.units.reduce((sum, unit) => sum + unit.tokens, 0);
  // One unit is not a list. Showing `main.c` over `최상위 선언` and nothing else
  // is a level of hierarchy carrying no information.
  const only = group.units.length === 1 ? group.units[0] : null;

  if (only) {
    return (
      <li className="border-b border-line">
        <UnitRow unit={only} open={open} onToggle={onToggle} selected={selected} onTunePrompt={onTunePrompt} />
      </li>
    );
  }

  return (
    <li className="border-b border-line">
      <Collapsible open={open.has(fileId(group.file))} onOpenChange={(next) => onToggle(fileId(group.file), next)}>
        <CollapsibleTrigger className="group/file flex w-full items-baseline gap-2 px-3 py-2 text-left hover:bg-surface-2">
          <ChevronRight
            className="size-3 shrink-0 self-center text-ink-faint transition-transform group-data-[state=open]/file:rotate-90"
            aria-hidden
          />
          <span className="min-w-0 truncate font-mono text-xs font-semibold text-ink-strong">{group.file}</span>
          <span className="shrink-0 text-2xs text-ink-faint">단위 {group.units.length}</span>
          <span className="ml-auto flex shrink-0 items-baseline gap-2">
            {outcome && <span className={cn("text-2xs", TONE[outcome.tone])}>{outcome.text}</span>}
            {tokens > 0 && <span className="font-mono text-2xs text-ink-faint">{tokens.toLocaleString()}</span>}
          </span>
        </CollapsibleTrigger>

        <CollapsibleContent>
          <ul className="pl-3">
            {group.units.map((unit) => (
              <UnitRow
                key={unit.id}
                unit={unit}
                open={open}
                onToggle={onToggle}
                selected={selected}
                onTunePrompt={onTunePrompt}
                nested
              />
            ))}
          </ul>
        </CollapsibleContent>
      </Collapsible>
    </li>
  );
}

/* -- unit -------------------------------------------------------------------- */

/** One code unit: a row that says what became of it, and its steps when opened. */
function UnitRow({
  unit,
  open,
  onToggle,
  selected,
  onTunePrompt,
  nested,
}: {
  unit: Unit;
  open: Set<string>;
  onToggle: (id: string, next: boolean) => void;
  selected: string | null;
  onTunePrompt: (spanId: string) => void;
  /** Inside a file group, which already carries the filename. */
  nested?: boolean;
}) {
  const outcome = unitOutcome(unit.exchanges);
  // The file chunk holds the declarations above every function -- includes,
  // prototypes, globals -- and its symbol *is* the filename, which is how it came
  // to sit in the list looking like a second copy of its own file.
  const name = isWholeFile(unit) ? "최상위 선언" : (unit.symbol ?? unit.id);
  // Only when the group above is not already saying it.
  const file = !nested && unit.file && unit.file !== unit.symbol ? unit.file : null;

  return (
    <Collapsible open={open.has(unitId(unit.id))} onOpenChange={(next) => onToggle(unitId(unit.id), next)}>
      <CollapsibleTrigger className="group/unit flex w-full items-baseline gap-2 px-3 py-2 text-left hover:bg-surface-2">
        <ChevronRight
          className="size-3 shrink-0 self-center text-ink-faint transition-transform group-data-[state=open]/unit:rotate-90"
          aria-hidden
        />
        <span
          className={cn(
            "min-w-0 truncate font-mono text-xs",
            isWholeFile(unit) ? "text-ink-muted" : "font-semibold text-ink-strong",
          )}
        >
          {name}
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
              open={open.has(stepId(exchange.id))}
              onToggle={(next) => onToggle(stepId(exchange.id), next)}
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
  );
}

/* -- step -------------------------------------------------------------------- */

/** One step: a row that says what it decided, and the whole of it when opened. */
function StepRow({
  exchange,
  unit,
  highlighted,
  open,
  onToggle,
  onTunePrompt,
}: {
  exchange: Exchange;
  /** The unit's own name, so a step does not repeat it as its subject. */
  unit: string;
  highlighted: boolean;
  open: boolean;
  onToggle: (next: boolean) => void;
  onTunePrompt: () => void;
}) {
  const outcome = outcomeOf(exchange);
  const subject = exchange.subject === unit ? "" : exchange.subject;

  return (
    <li className={cn(highlighted && "bg-accent-wash")}>
      {/* One target. The prompt-edit pencil used to sit here on hover, a second
          control on the same line as the row's own, appearing under the pointer
          on the way to the thing you meant to click. It acts on the brief, so it
          is beside the brief now. */}
      <Collapsible open={open} onOpenChange={onToggle}>
        <CollapsibleTrigger className="group/row flex w-full min-w-0 items-baseline gap-2 py-1 pr-3 pl-3 text-left hover:bg-surface-2">
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

        <CollapsibleContent>
          <div className="space-y-2 border-l border-line py-2 pr-3 pl-3 ml-[22px]">
            {/* The agent's own id for this call, which the closed row has no width
                for and which is what a prompt is filed under and a breakpoint set
                on. With the subject when there is one: `gather · CWE-122 main.c:6`. */}
            <p className="font-mono text-2xs text-ink-faint">{[exchange.step, subject].filter(Boolean).join(" · ")}</p>
            <Detail exchange={exchange} />
            {exchange.error && <p className="font-mono text-2xs text-danger">{exchange.error}</p>}
            <Meta exchange={exchange} />
            <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
              <Sent exchange={exchange} />
              {/* Sized to its neighbour, not to itself. At the button's own scale
                  it was the loudest thing in a step whose subject is the step. */}
              <button
                type="button"
                onClick={onTunePrompt}
                className="flex shrink-0 items-center gap-0.5 font-mono text-2xs text-ink-faint hover:text-ink-muted"
              >
                <Pencil className="size-3 shrink-0" aria-hidden />
                고쳐서 다시 실행
              </button>
            </div>
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
