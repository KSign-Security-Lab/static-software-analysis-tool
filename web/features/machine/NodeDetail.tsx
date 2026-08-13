"use client";

import { Workflow } from "lucide-react";
import { useMemo } from "react";

import { CodeBlock } from "@/components/panel/code-block";
import { Disclosure } from "@/components/panel/disclosure";
import { Badge } from "@/components/ui/badge";
import { EmptyState, PanelShell } from "@/components/workbench/PanelShell";
import { useGraphShape, usePrompts } from "@/lib/run/trace-queries";
import { useScopedNode } from "@/features/trace/state";
import { cn } from "@/lib/utils";

/**
 * What one node of the pipeline is.
 *
 * Under the graph, because it is the graph's detail: you click a box and this
 * says what that box is made of. It used to be the top of a pane that also held
 * the entire run record, so a question about one node arrived with forty
 * conversations attached.
 *
 * The 지시문 is the point of it. A node's identity is the text it is run under --
 * more than its edges, more than its channels -- and that was the one thing the
 * old card left out.
 */
export default function NodeDetail() {
  const [node] = useScopedNode();
  const shape = useGraphShape();
  const prompts = usePrompts();

  const note = useMemo(
    () => (node ? shape.data?.node_notes?.find((each) => each.node === node) : undefined),
    [shape.data, node],
  );
  const steps = useMemo(
    () => (node ? (shape.data?.steps ?? []).filter((step) => step.node === node) : []),
    [shape.data, node],
  );

  if (!note) {
    return (
      <PanelShell title="노드">
        <EmptyState icon={Workflow} title="위 그래프에서 노드를 고르세요">
          그 노드의 지시문과 쓸 수 있는 도구, 그리고 이번 실행에서 무엇을 했는지가 여기 나옵니다.
        </EmptyState>
      </PanelShell>
    );
  }

  const tools = steps
    .flatMap((step) => step.tools)
    .filter((tool, at, all) => all.findIndex((other) => other.name === tool.name) === at);

  return (
    <PanelShell
      title={note.node}
      note={note.does ?? undefined}
      actions={
        <Badge variant={note.agent ? "secondary" : "outline"} className="font-normal">
          {note.agent ? `모델 호출 ${note.calls}` : "코드"}
        </Badge>
      }
    >
      <div className="space-y-3 px-3 py-3">
        <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 font-mono text-2xs">
          {steps.length > 0 && <Fact term="단계" value={steps.map((step) => step.step).join(" · ")} />}
          {steps.some((step) => step.schema) && (
            <Fact
              term="답변 형식"
              value={steps
                .filter((step) => step.schema)
                .map((step) => `${step.schema}(${step.schema_fields.join(", ")})`)
                .join(" · ")}
            />
          )}
          {note.routes.length > 0 && <Fact term="다음" value={note.routes.join(", ")} />}
          {note.rule && <Fact term={note.router ?? "조건"} value={note.rule} />}
        </dl>

        {steps.map((step) => {
          const row = prompts.data?.find((each) => each.name === step.prompt);
          if (!row) return null;
          return (
            <Disclosure
              key={step.step}
              tone="aside"
              label={`${step.step} 의 지시문 · ${row.override ? "수정됨" : "기본"}`}
            >
              <div className="mt-1 rounded-sm bg-field p-2">
                <CodeBlock text={row.override ?? row.default} />
              </div>
            </Disclosure>
          );
        })}

        {tools.length > 0 && (
          <section className="space-y-1">
            <h3 className="text-2xs text-ink-muted">쓸 수 있는 도구</h3>
            <ul className="space-y-1">
              {tools.map((tool) => (
                <li key={tool.name} className="flex flex-wrap items-baseline gap-x-1.5">
                  <span className="font-mono text-2xs text-alt">{tool.name}</span>
                  {tool.name === "search_semantic" && (
                    <span className="rounded-sm bg-alt-wash px-1 font-mono text-2xs text-alt">RAG</span>
                  )}
                  {tool.summary && <span className="min-w-0 flex-1 text-2xs text-ink-faint">{tool.summary}</span>}
                </li>
              ))}
            </ul>
          </section>
        )}
      </div>
    </PanelShell>
  );
}

function Fact({ term, value }: { term: string; value: string }) {
  return (
    <>
      <dt className="text-ink-faint">{term}</dt>
      <dd className={cn("min-w-0 break-words text-ink-muted")}>{value}</dd>
    </>
  );
}
