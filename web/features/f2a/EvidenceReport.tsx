"use client";

import { AlertTriangle, ArrowDown } from "lucide-react";
import { useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { buildDecisions, type Decision } from "@/lib/decision";
import type { F2AResult } from "@/lib/types";
import { cn } from "@/lib/utils";

/**
 * F2-A's verdicts, with the evidence for each.
 *
 * `lib/decision.ts` is unchanged -- it already turns the pipeline's ten lists
 * into something a person can read, in Korean, from controlled enums. This is
 * only the rendering.
 */

const TONE: Record<string, string> = {
  suspect: "text-danger",
  warn: "text-warn",
  ok: "text-ok",
  info: "text-ink-muted",
  none: "text-ink-faint",
};

const ROLE_TONE: Record<string, string> = {
  source: "border-l-warn",
  sink: "border-l-danger",
  propagation: "border-l-line-3",
};

function DecisionCard({ decision }: { decision: Decision }) {
  const confidence = Math.round(decision.confidence * 100);

  return (
    <article className="space-y-3 rounded-md border border-line bg-surface-2 p-3">
      <header className="space-y-1">
        {decision.eyebrow && <p className="text-2xs text-ink-faint">{decision.eyebrow}</p>}
        <div className="flex flex-wrap items-baseline gap-2">
          <h3 className="text-sm font-medium text-ink-strong">{decision.title}</h3>
          <Badge variant="outline" className={cn("px-1.5 py-0 text-2xs", TONE[decision.tone])}>
            {decision.verdict}
          </Badge>
          {decision.cwe.map((cwe) => (
            <Badge key={cwe} variant="outline" className="px-1 py-0 text-2xs font-normal">
              {cwe}
            </Badge>
          ))}
        </div>
        <p className="font-mono text-2xs text-ink-faint">{decision.subtitle}</p>
      </header>

      {decision.overview && <p className="text-xs leading-relaxed text-ink-muted">{decision.overview}</p>}

      {decision.meta.length > 0 && (
        <dl className="flex flex-wrap gap-x-4 gap-y-1 text-2xs">
          {decision.meta.map(([key, value]) => (
            <div key={key} className="flex gap-1.5">
              <dt className="text-ink-faint">{key}</dt>
              <dd className="font-mono text-ink-muted">{value}</dd>
            </div>
          ))}
        </dl>
      )}

      {decision.trace.length > 0 && (
        <section className="space-y-1">
          <h4 className="text-2xs font-semibold tracking-wide text-ink-faint uppercase">{decision.traceLabel}</h4>
          {decision.traceNote.map((note, index) => (
            <p key={index} className="text-2xs text-ink-faint">
              {typeof note === "string" ? note : JSON.stringify(note)}
            </p>
          ))}
          <ol className="space-y-0.5">
            {decision.trace.map((step, index) => (
              <li key={index} className={cn("border-l-2 py-1 pl-2", ROLE_TONE[step.role] ?? "border-l-line-2")}>
                <p className="flex items-center gap-1.5 text-2xs text-ink-faint">
                  <span className="text-ink-muted">{step.role}</span>
                  {step.line > 0 && (
                    <span className="font-mono">
                      {step.file}:{step.line}
                    </span>
                  )}
                </p>
                <p className="text-xs leading-snug text-ink">{step.note}</p>
                {index < decision.trace.length - 1 && (
                  <ArrowDown className="mt-0.5 size-3 text-line-3" aria-hidden />
                )}
              </li>
            ))}
          </ol>
        </section>
      )}

      {decision.hasFinding && decision.checks.length > 0 && (
        <section className="space-y-1">
          <h4 className="text-2xs font-semibold tracking-wide text-ink-faint uppercase">검사</h4>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="h-6 text-2xs">검사</TableHead>
                <TableHead className="h-6 text-2xs">상태</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {decision.checks.map((check) => (
                <TableRow key={check.id}>
                  <TableCell className="py-1 font-mono text-2xs" title={check.id}>
                    {check.id}
                  </TableCell>
                  <TableCell className={cn("py-1 text-2xs", check.observed ? "text-ok" : "text-danger")}>
                    {check.observed ?? check.status}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </section>
      )}

      {decision.hasFinding && (
        <section className="space-y-1">
          <div className="flex items-baseline justify-between text-2xs">
            <span className="text-ink-faint">{decision.confidenceLabel}</span>
            <span className="font-mono text-ink-muted">{confidence}%</span>
          </div>
          <div
            role="meter"
            aria-valuenow={confidence}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-label={decision.confidenceLabel}
            className="h-1 overflow-hidden rounded-full bg-surface-3"
          >
            <div className="h-full rounded-full bg-accent-solid" style={{ width: `${confidence}%` }} />
          </div>
          {decision.confidenceFactors.length > 0 && (
            <ul className="mt-1 space-y-0.5">
              {decision.confidenceFactors.map(([label, weight]) => (
                <li key={label} className="flex justify-between gap-2 text-2xs">
                  <span className="truncate text-ink-faint">{label}</span>
                  <span className="font-mono text-ink-muted">{weight > 0 ? `+${weight}` : weight}</span>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}

      {decision.remediation.length > 0 && (
        <section className="space-y-1">
          <h4 className="text-2xs font-semibold tracking-wide text-ink-faint uppercase">고치는 방법</h4>
          <ul className="space-y-0.5 text-xs leading-relaxed text-ink-muted">
            {decision.remediation.map((line, index) => (
              <li key={index}>{line}</li>
            ))}
          </ul>
        </section>
      )}
    </article>
  );
}

export default function EvidenceReport({ result }: { result: F2AResult }) {
  const decisions = useMemo(() => buildDecisions(result), [result]);
  const [kind, setKind] = useState<"all" | "vuln" | "handler">("all");

  const shown = kind === "all" ? decisions : decisions.filter((each) => each.kind === kind);

  return (
    <div className="space-y-3 p-3">
      <div className="flex items-center gap-2">
        <ToggleGroup
          type="single"
          size="sm"
          variant="outline"
          value={kind}
          onValueChange={(next) => next && setKind(next as typeof kind)}
        >
          <ToggleGroupItem value="all" className="h-7 px-2 text-2xs">
            전체 {decisions.length}
          </ToggleGroupItem>
          <ToggleGroupItem value="vuln" className="h-7 px-2 text-2xs">
            취약 후보
          </ToggleGroupItem>
          <ToggleGroupItem value="handler" className="h-7 px-2 text-2xs">
            핸들러
          </ToggleGroupItem>
        </ToggleGroup>
      </div>

      {shown.length === 0 ? (
        <p className="p-4 text-xs text-ink-faint">해당하는 결과가 없습니다.</p>
      ) : (
        shown.map((decision) => <DecisionCard key={decision.id} decision={decision} />)
      )}

      {result.limitations?.length > 0 && (
        <section className="space-y-1 rounded-md border border-warn/40 bg-warn-wash p-2.5">
          <h4 className="flex items-center gap-1.5 text-2xs font-semibold text-warn">
            <AlertTriangle className="size-3" />
            이 분석의 한계
          </h4>
          {/* Stated, not hidden: the pipeline knows what it could not see, and
              a verdict read without them is read wrong. */}
          <ul className="space-y-0.5 text-2xs leading-relaxed text-ink-muted">
            {result.limitations.map((limitation, index) => (
              <li key={index}>{limitation}</li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
