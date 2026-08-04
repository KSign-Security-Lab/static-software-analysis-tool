"use client";

import {
  ENGINE_LABEL,
  SEVERITY_LABEL,
  sortFindings,
  type Engine,
  type Severity,
  type UiFinding,
} from "@/lib/model/finding";

const SEVERITIES: Severity[] = ["critical", "high", "medium", "low", "info"];

/**
 * Every finding for the target, most severe first, filterable by engine.
 *
 * The engine filter is the point of merging the two: with both on you can see
 * where structural analysis and the model agree, which is a stronger signal
 * than either alone.
 */
export default function FindingList({
  findings,
  selectedId,
  engines,
  onToggleEngine,
  onSelect,
  emptyHint,
}: {
  findings: UiFinding[];
  selectedId: string | null;
  engines: Set<Engine>;
  onToggleEngine: (engine: Engine) => void;
  onSelect: (finding: UiFinding) => void;
  emptyHint?: string;
}) {
  const visible = sortFindings(findings).filter((f) => engines.has(f.engine));
  const perEngine = (engine: Engine) => findings.filter((f) => f.engine === engine).length;

  return (
    <div className="ws-findings">
      <div className="ws-filters">
        {(["structural", "agent"] as Engine[]).map((engine) => (
          <button
            key={engine}
            type="button"
            className={`ws-chip eng-${engine} ${engines.has(engine) ? "is-on" : ""}`}
            onClick={() => onToggleEngine(engine)}
            disabled={perEngine(engine) === 0}
          >
            {ENGINE_LABEL[engine]} {perEngine(engine)}
          </button>
        ))}
      </div>

      {visible.length === 0 ? (
        <p className="ws-empty">{findings.length === 0 ? (emptyHint ?? "아직 결과가 없습니다.") : "필터에 해당하는 결과가 없습니다."}</p>
      ) : (
        <ul className="ws-list">
          {visible.map((f) => (
            <li key={f.id}>
              <button
                type="button"
                className={`ws-item ${f.id === selectedId ? "is-selected" : ""}`}
                onClick={() => onSelect(f)}
              >
                <span className={`ws-dot sev-${f.severity}`} aria-hidden />
                <span className="ws-item-title">{f.title}</span>
                <span className={`ws-tag eng-${f.engine}`}>{ENGINE_LABEL[f.engine]}</span>
                <span className="ws-item-where">
                  {f.primary.file}
                  {f.primary.startLine > 0 && `:${f.primary.startLine}`}
                </span>
                <span className="ws-item-meta">
                  {SEVERITY_LABEL[f.severity]}
                  {f.cwe && ` · ${f.cwe}`}
                  {f.verified === false && " · 미검증"}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}

      <div className="ws-tally">
        {SEVERITIES.filter((s) => visible.some((f) => f.severity === s)).map((s) => (
          <span key={s} className={`ws-tally-item sev-${s}`}>
            {SEVERITY_LABEL[s]} {visible.filter((f) => f.severity === s).length}
          </span>
        ))}
      </div>
    </div>
  );
}
