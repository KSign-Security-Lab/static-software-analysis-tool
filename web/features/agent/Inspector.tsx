"use client";

import { MousePointerClick } from "lucide-react";
import { useMemo } from "react";

import { Button } from "@/components/ui/button";
import { Verdict } from "@/components/panel/verdict";
import { EmptyState, PanelShell } from "@/components/workbench/PanelShell";
import SpanInspector from "@/features/trace/SpanInspector";
import { fromAgent, standingOf, wireId } from "@/lib/model/finding";
import { useKnowledge } from "@/lib/run/knowledge-queries";
import { useApplyFix, useFindings, useProposeFix } from "@/lib/run/queries";
import { useFilter, useOpenFile, useRevealLine, useSelection } from "@/lib/run/selection";
import { useRunStream } from "@/lib/run/stream";
import { useGraphShape, usePrompts, useSpans } from "@/lib/run/trace-queries";
import { useRunId } from "@/lib/run/use-run-id";
import DecisionChain from "./DecisionChain";
import { Grounds } from "./FindingList";
import NodeCard from "./NodeCard";

/**
 * 상세: the one selected thing, in full, whatever kind it is.
 *
 * The other half of the rule the surface runs on -- the panel below is many, this
 * is one -- and the reason it is one component rather than four panes is that the
 * reader should not have to learn where a kind of thing goes. You pick something
 * anywhere in 실행 and it appears here, with the header naming what kind it is.
 *
 * It held only findings before, so it sat unused through any debugging while the
 * call record crammed a four-level tree into the panel. Now the record is a list
 * of rows down there and their contents are up here, which is what stops either
 * pane being the densest thing on screen.
 *
 * Three kinds. There was a fourth -- a paused run's checkpoint, with lanes to
 * fork and re-run from -- and it went with the feature: it was a debug tool that
 * meant nothing except at a breakpoint, reachable only through a button that
 * only existed then.
 */
export default function Inspector() {
  const [runId] = useRunId();
  const { selection, clear } = useSelection();

  if (!selection) {
    return (
      <PanelShell title="상세">
        {/* Naming both halves of the rule, because the rule is what makes the
            screen learnable: pick below, read here. */}
        <EmptyState icon={MousePointerClick} title="아래 ‘실행’에서 하나를 고르세요">
          고른 것의 전부가 여기 나옵니다 — 문제라면 판단과 근거와 고치는 방법, 호출이라면 보낸 지시와 답변, 노드라면
          그 노드가 무엇인지.
        </EmptyState>
      </PanelShell>
    );
  }

  if (selection.kind === "finding") return <FindingBody runId={runId} id={selection.id} onClose={clear} />;
  if (selection.kind === "call") return <CallBody runId={runId} id={selection.id} onClose={clear} />;
  return <NodeBody id={selection.id} onClose={clear} />;
}

/** The header every kind shares: what kind, what one, and a way out. */
function Shell({
  kind,
  name,
  actions,
  onClose,
  children,
}: {
  kind: string;
  name?: string;
  actions?: React.ReactNode;
  onClose: () => void;
  children: React.ReactNode;
}) {
  return (
    <PanelShell
      // The kind first and always. A reader who has just clicked something in a
      // list of four kinds of thing should not have to infer which one they got.
      title={
        <span className="flex min-w-0 items-baseline gap-1.5">
          <span className="shrink-0 text-ink-faint">{kind}</span>
          {name && <span className="min-w-0 truncate">{name}</span>}
        </span>
      }
      actions={
        <>
          {actions}
          <Button size="icon-xs" variant="ghost" aria-label={`${kind} 닫기`} onClick={onClose}>
            <span aria-hidden>×</span>
          </Button>
        </>
      }
    >
      {children}
    </PanelShell>
  );
}

function FindingBody({ runId, id, onClose }: { runId: string | null; id: string; onClose: () => void }) {
  const [, setPath] = useOpenFile();
  const [, setLine] = useRevealLine();
  const { phase } = useRunStream();
  const findings = useFindings(runId);
  const knowledge = useKnowledge(runId);
  const apply = useApplyFix(runId);
  const propose = useProposeFix(runId);

  const finding = useMemo(() => {
    const all = fromAgent(findings.data?.findings);
    return all.find((each) => each.id === id) ?? all.find((each) => each.mergedIds.includes(id));
  }, [findings.data, id]);

  if (!finding) {
    return (
      <Shell kind="문제" onClose={onClose}>
        <p className="px-3 py-2.5 text-2xs text-ink-faint">이 실행의 보고서에 그 문제가 없습니다.</p>
      </Shell>
    );
  }

  const standing = standingOf(finding);
  // Never while a run is in flight: the inspection is reading these files.
  const running = phase === "running" || phase === "starting";

  return (
    <Shell
      kind="문제"
      name={finding.title}
      onClose={onClose}
      actions={standing && <Verdict standing={standing} confidence={finding.confidence ?? undefined} />}
    >
      <button
        type="button"
        onClick={() => {
          void setPath(finding.primary.file);
          void setLine(finding.primary.startLine > 0 ? finding.primary.startLine : null);
        }}
        className="flex w-full items-center gap-2 px-3 pt-2.5 text-left font-mono text-2xs text-ink-faint hover:text-ink-muted"
      >
        {finding.cwe && <span className="shrink-0">{finding.cwe}</span>}
        <span className="min-w-0 truncate">
          {finding.primary.file}:{finding.primary.startLine}
        </span>
      </button>

      <Grounds
        finding={finding}
        knowledge={knowledge.data}
        onNavigate={(file, line) => {
          void setPath(file);
          void setLine(line > 0 ? line : null);
        }}
        onApply={runId && !running ? (each) => apply.mutate(wireId(each.id)) : undefined}
        applying={apply.isPending}
        onPropose={runId && !running ? (each) => propose.mutate(wireId(each.id)) : undefined}
        proposing={propose.isPending}
      />
      <DecisionChain finding={finding} />
    </Shell>
  );
}

function CallBody({ runId, id, onClose }: { runId: string | null; id: string; onClose: () => void }) {
  const spans = useSpans(runId);
  const prompts = usePrompts();
  const span = useMemo(() => spans.data?.spans.find((each) => each.id === id) ?? null, [spans.data, id]);

  return (
    <Shell kind="호출" name={span?.name ?? id} onClose={onClose}>
      {/* Already written, and it is the whole of what a call is: the two prompts,
          the reply, the tools, and running it again with an edited brief. It was
          reachable only through a sheet over the top of the old transcript. */}
      <SpanInspector runId={runId} span={span} prompts={prompts.data ?? []} />
    </Shell>
  );
}

function NodeBody({ id, onClose }: { id: string; onClose: () => void }) {
  const shape = useGraphShape();
  const prompts = usePrompts();
  const [, setFilter] = useFilter();
  const { select } = useSelection();

  const note = shape.data?.node_notes?.find((each) => each.node === id);
  const steps = shape.data?.steps ?? [];

  return (
    <Shell
      kind="노드"
      name={id}
      onClose={onClose}
      actions={
        // Offered rather than done. Clicking a stage used to silently filter a
        // pane somewhere else; this asks first, and says which list it will change.
        <Button
          size="xs"
          variant="ghost"
          className="text-2xs text-accent-ink"
          onClick={() => {
            void setFilter("all");
            select(null);
          }}
        >
          이 노드의 호출 보기
        </Button>
      }
    >
      {note ? (
        <NodeCard note={note} steps={steps} prompts={prompts.data ?? []} />
      ) : (
        <p className="px-3 py-2.5 text-2xs text-ink-faint">이 노드에 대한 설명이 아직 없습니다.</p>
      )}
    </Shell>
  );
}

