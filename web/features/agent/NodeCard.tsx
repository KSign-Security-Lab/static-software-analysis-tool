"use client";

import { CodeBlock } from "@/components/panel/code-block";
import { Disclosure } from "@/components/panel/disclosure";
import type { AgentStep, NodeNote, PromptRow } from "@/lib/api/types";
import { cn } from "@/lib/utils";

/** A disclosure, for the things that are genuinely asides. */
function Fold({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <Disclosure label={label} tone="aside">
      {children}
    </Disclosure>
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
export default function NodeCard({ note, steps, prompts }: { note: NodeNote; steps: AgentStep[]; prompts: PromptRow[] }) {
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
            <CodeBlock text={brief.row.override ?? brief.row.default} />
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
