"use client";

import { MousePointerClick } from "lucide-react";

import { CodeBlock } from "@/components/panel/code-block";
import { LivenessBadge } from "@/components/panel/liveness";
import { Verdict } from "@/components/panel/verdict";
import { EmptyState } from "@/components/workbench/PanelShell";
import Evidence from "@/features/inspect/Evidence";
import FixPatch from "@/features/inspect/FixPatch";
import Reasoning from "@/features/inspect/Reasoning";
import { Badge } from "@/components/ui/badge";
import {
  SEVERITY_DOT,
  SEVERITY_LABEL,
  livenessOf,
  standingOf,
  type UiFinding,
} from "@/lib/model/finding";
import { cn } from "@/lib/utils";

export default function FindingDetail({ finding }: { finding: UiFinding | undefined }) {
  if (!finding) {
    return (
      <section className="min-h-0 overflow-auto bg-surface">
        <EmptyState icon={MousePointerClick} title="왼쪽에서 하나를 고르세요">
          고른 항목의 판단과 근거, 고치는 방법과 패치가 여기에 나옵니다. 왜 그렇게 판단했는지도 펼쳐 볼 수 있습니다.
        </EmptyState>
      </section>
    );
  }

  const standing = standingOf(finding);
  const liveness = livenessOf(finding);

  return (
    <section className="min-h-0 overflow-auto bg-surface">
      <div className="space-y-5 px-4 py-4">
        <header className="space-y-2">
          <div className="flex items-start gap-2">
            <span
              className={cn("mt-1.5 size-2 shrink-0 rounded-full", SEVERITY_DOT[finding.severity])}
              aria-hidden
            />
            <h2 className="min-w-0 flex-1 text-sm leading-snug font-semibold text-ink-strong">
              {finding.title}
            </h2>
          </div>
          <div className="flex flex-wrap items-center gap-1.5">
            <Badge variant="outline" className="font-normal text-ink-muted">
              {SEVERITY_LABEL[finding.severity]}
            </Badge>
            {finding.cwe && (
              <Badge variant="outline" className="font-mono font-normal text-ink-muted">
                {finding.cwe}
              </Badge>
            )}
            {standing && <Verdict standing={standing} confidence={finding.confidence} />}
            {liveness && <LivenessBadge liveness={liveness} why={finding.reach?.why ?? []} />}
          </div>
          <p className="font-mono text-2xs text-ink-faint">
            {finding.primary.file}:{finding.primary.startLine}
            {finding.primary.endLine > finding.primary.startLine && `-${finding.primary.endLine}`}
          </p>
        </header>

        {finding.primary.excerpt && (
          <Section title="문제의 코드">
            <pre className="overflow-x-auto rounded-md border border-line bg-field p-2 font-mono text-2xs leading-relaxed text-ink">
              {finding.primary.excerpt}
            </pre>
          </Section>
        )}

        <Section title="설명">
          <CodeBlock text={finding.explanation} mono={false} />
        </Section>

        {finding.evidence.length > 0 && (
          <Section title="근거">
            <Evidence evidence={finding.evidence} />
          </Section>
        )}

        {finding.remediation && (
          <Section title="고치는 방법">
            <CodeBlock text={finding.remediation} mono={false} />
          </Section>
        )}

        <Section title="패치">
          <FixPatch finding={finding} />
        </Section>

        <Reasoning finding={finding} />
      </div>
    </section>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="space-y-1.5">
      <h3 className="text-2xs font-semibold tracking-wide text-ink-faint">{title}</h3>
      {children}
    </section>
  );
}
