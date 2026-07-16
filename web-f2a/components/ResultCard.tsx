"use client";

import { useMemo } from "react";
import { koStatus, type Decision, type TraceStep } from "@/lib/decision";
import { buildGroups, sourceLines, type CodeTone } from "@/lib/code";

// One result model, two result types (vuln finding / handler resolution). The
// visual language — header, card container, numbered code-evidence trace, and
// sections — is shared so the page reads as one coherent report, not two.

function statusClass(status: string): string {
  switch (status) {
    case "SATISFIED":
      return "sat";
    case "NEGATIVE":
    case "NEGATIVE_EVIDENCE_FOUND":
      return "neg";
    case "WEAKLY_RELATED":
      return "weak";
    default:
      return "unv";
  }
}

function Section({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <section className="section">
      <div className="section-title">{label}</div>
      {children}
    </section>
  );
}

function roleTone(role: TraceStep["role"]): CodeTone {
  return role === "source" ? "source" : role === "sink" ? "sink" : "call";
}

function StepSnippet({ step, lines }: { step: TraceStep; lines: string[] }) {
  const tone = roleTone(step.role);
  const groups = useMemo(
    () => buildGroups([{ line: step.line, caption: step.note, tone }], lines.length, 3),
    [step.line, step.note, tone, lines.length],
  );
  const g = groups[0];
  return (
    <div className="codeblock">
      <div className="codeblock-bar">
        <span className="dots">
          <i />
          <i />
          <i />
        </span>
        <span className="cb-label">
          {step.fn} · {step.file}:{step.line}
        </span>
      </div>
      <pre className="snip">
        {g ? (
          Array.from({ length: g.end - g.start + 1 }, (_, k) => {
            const n = g.start + k;
            const ref = g.refs.get(n);
            return (
              <div key={n} className={`cline ${ref ? "hl tone-" + ref.tone : ""}`}>
                <span className="ln">{n}</span>
                <span className="ct">{lines[n - 1] || " "}</span>
                {ref && <span className="cap">{ref.caption}</span>}
              </div>
            );
          })
        ) : (
          <div className="cline hl">
            <span className="ct">{step.note}</span>
          </div>
        )}
      </pre>
    </div>
  );
}

function Trace({
  steps,
  lines,
  label,
  onInspect,
}: {
  steps: TraceStep[];
  lines: string[];
  label: string;
  onInspect?: (fn: string) => void;
}) {
  return (
    <ol className="trace">
      {steps.map((s) => (
        <li className={`trace-step ${s.role}`} key={s.n}>
          <span className="tnum">{s.n}</span>
          <div className="tmain">
            <StepSnippet step={s} lines={lines} />
          </div>
        </li>
      ))}
      {onInspect && steps[0] && (
        <button className="tblink" onClick={() => onInspect(steps[steps.length - 1].fn)}>
          그래프 탐색기에서 {label} 보기 ▸
        </button>
      )}
    </ol>
  );
}

export default function ResultCard({
  d,
  source,
  onInspect,
}: {
  d: Decision;
  source: string;
  onInspect?: (fn: string) => void;
}) {
  const lines = useMemo(() => (source ? sourceLines(source) : []), [source]);
  const showConf = d.confidenceLabel !== "";
  const showTrace = d.trace.length > 0;

  return (
    <article className={`finding tone-${d.tone}`}>
      <header className="finding-head">
        <div className="fh-top">
          <span className={`vbadge ${d.tone}`}>{d.verdict}</span>
          {showConf && (
            <div className="fh-conf">
              <span className="fh-conf-num">{d.confidence.toFixed(2)}</span>
              <span className="cbar" style={{ width: 84 }}>
                <span style={{ width: `${Math.round(d.confidence * 100)}%` }} />
              </span>
              <span className="muted small">신뢰도 {d.confidenceLabel}</span>
            </div>
          )}
        </div>
        <h1 className="fh-title">{d.title}</h1>
        {d.subtitle && <div className="fh-sub mono">{d.subtitle}</div>}
        <div className="fh-meta">
          {d.kind === "vuln" && d.hasFinding && (
            <>
              {d.component && <span className="badge mono">component · {d.component}</span>}
              {d.ocppVersion && <span className="badge mono">{d.ocppVersion}</span>}
              {d.cwe.map((w) => (
                <span key={w} className="badge">
                  {w}
                </span>
              ))}
            </>
          )}
          {d.kind === "handler" &&
            d.meta.map(([k, v], i) => (
              <span key={k + i} className="badge mono">
                {k} · {v}
              </span>
            ))}
          {d.location && <span className="badge mono">{d.location}</span>}
        </div>
      </header>

      <Section label="개요">
        <p className="prose">{d.overview}</p>
      </Section>

      {showTrace && (
        <Section label={d.traceLabel}>
          <Trace steps={d.trace} lines={lines} label={d.traceLabel} onInspect={onInspect} />
        </Section>
      )}

      {d.kind === "vuln" && d.hasFinding && (
        <>
          <Section label="검사">
            <table className="checks">
              <thead>
                <tr>
                  <th>필요한 검사</th>
                  <th>상태</th>
                  <th>관찰된 근거</th>
                </tr>
              </thead>
              <tbody>
                {d.checks.map((c, i) => (
                  <tr key={c.id + i}>
                    <td className="mono">{c.id}</td>
                    <td>
                      <span className={`tag ${statusClass(c.status)}`}>{koStatus(c.status)}</span>
                    </td>
                    <td className="mono muted small">{c.evidence ?? c.observed ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Section>

          {d.remediation.length > 0 && (
            <Section label="권고">
              <ul className="remedy">
                {d.remediation.map((r, i) => (
                  <li key={i}>{r}</li>
                ))}
              </ul>
            </Section>
          )}

          <Section label="신뢰도 근거">
            <p className="muted small" style={{ margin: "0 0 10px" }}>
              근거가 얼마나 잘 연결되는지를 나타낼 뿐, 실제 악용 가능 여부는 아닙니다. F2-A는
              취약점을 확정하지 않습니다.
            </p>
            <div className="confgrid">
              {d.confidenceFactors.map(([k, v]) => (
                <div className="confrow" key={k}>
                  <span className="muted mono small">{k}</span>
                  <span className="cbar">
                    <span style={{ width: `${Math.round(v * 100)}%` }} />
                  </span>
                </div>
              ))}
            </div>
          </Section>
        </>
      )}

      {d.kind === "vuln" && !d.hasFinding && d.handlers.length > 0 && (
        <Section label="발견된 핸들러">
          <div className="chiprow">
            {d.handlers.map((h, i) => (
              <span key={i} className="badge">
                {h.action} → {h.fn}
              </span>
            ))}
          </div>
        </Section>
      )}

      {d.limitations.length > 0 && (
        <details className="limdetails">
          <summary className="muted small">한계 및 범위 ({d.limitations.length})</summary>
          <ul className="limits">
            {d.limitations.map((l, i) => (
              <li key={i}>{l}</li>
            ))}
          </ul>
        </details>
      )}
    </article>
  );
}
