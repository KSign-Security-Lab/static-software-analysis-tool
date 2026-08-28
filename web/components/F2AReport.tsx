"use client";

import type { EvidencePackage, F2AResult } from "@/lib/types";
import { buildDecisions } from "@/lib/decision";
import ResultCard from "@/components/ResultCard";

function strengthTag(s: string): string {
  if (s === "STRONG") return "strong";
  if (s === "WEAK" || s === "PARTIAL") return "weak";
  return "unv";
}

function statusTag(basis: string): { cls: string; label: string } {
  switch (basis) {
    case "NEGATIVE_EVIDENCE_FOUND":
      return { cls: "neg", label: "부정 근거" };
    case "WEAKLY_RELATED":
      return { cls: "weak", label: "약하게 관련" };
    case "UNVERIFIED":
      return { cls: "unv", label: "미확인" };
    default:
      return { cls: "sat", label: "충족" };
  }
}

function confRow(label: string, value: number) {
  const pct = Math.round(value * 100);
  return (
    <div className="conf" key={label}>
      <span className="lab">{label}</span>
      <span className="bar">
        <span style={{ width: `${pct}%` }} />
      </span>
      <span>{value.toFixed(2)}</span>
    </div>
  );
}

function PackageCard({ pkg }: { pkg: EvidencePackage }) {
  const ctx = pkg.ocpp_context;
  const flow = pkg.code_evidence.flow;
  const sink = pkg.code_evidence.sink;
  const src = pkg.code_evidence.source;
  const missingByCheck = new Map(
    pkg.check_evidence.missing_check_candidates.map((m) => [m.check_id, m.basis]),
  );
  const c = pkg.confidence;

  return (
    <div className="card">
      <div className="row" style={{ justifyContent: "space-between" }}>
        <h3 style={{ margin: 0 }}>
          {ctx.action}.{ctx.field}{" "}
          <span className="status mono">({ctx.field_semantic})</span>
        </h3>
        <span className="overall">
          <span className="num">{pkg.static_confidence.toFixed(2)}</span>
          <span className="status">정적 신뢰도</span>
        </span>
      </div>
      <div className="row">
        <span className="badge">{pkg.evidence_id}</span>
        <span className="badge">{ctx.ocpp_version}</span>
        <span className="badge">신뢰수준: {ctx.trust_level}</span>
        <span className="badge">{pkg.component_type}</span>
      </div>

      <p className="status" style={{ marginTop: 10 }}>
        {pkg.security_interpretation.summary}
      </p>

      <h4 className="mono" style={{ margin: "14px 0 6px", color: "var(--muted)" }}>
        소스 → 싱크 흐름
      </h4>
      <div className="flowline">
        <span className="pill src">
          {src.binding} @ {src.file}:{String(src.line)}
        </span>
        {flow.map((s) => (
          <span key={s.step} style={{ display: "contents" }}>
            <span className="arrow">→</span>
            <span className="pill step" title={`${s.function} @ ${s.file}:${s.line}`}>
              {s.operation}
            </span>
          </span>
        ))}
        <span className="arrow">→</span>
        <span className="pill sink">
          {sink.api} · {sink.sink_domain} @ {sink.file}:{String(sink.line)}
        </span>
      </div>

      <h4 className="mono" style={{ margin: "16px 0 6px", color: "var(--muted)" }}>
        검사 (관찰 vs 기대)
      </h4>
      <table className="checks">
        <thead>
          <tr>
            <th>기대 검사</th>
            <th>상태</th>
            <th>관찰</th>
            <th>근거</th>
          </tr>
        </thead>
        <tbody>
          {pkg.check_evidence.expected_checks.map((ec) => {
            const basis = missingByCheck.get(ec) ?? "SATISFIED";
            const st = statusTag(basis);
            const obs = pkg.check_evidence.observed_checks.find(
              (o) => o.matched_expected_check === ec,
            );
            return (
              <tr key={ec}>
                <td className="mono">{ec}</td>
                <td>
                  <span className={`tag ${st.cls}`}>{st.label}</span>
                </td>
                <td>
                  {obs ? (
                    <span className={`tag ${strengthTag(obs.check_strength)}`}>
                      {obs.check_type} · {obs.check_strength}
                    </span>
                  ) : (
                    <span className="status">—</span>
                  )}
                </td>
                <td className="mono status">{obs?.evidence ?? ""}</td>
              </tr>
            );
          })}
        </tbody>
      </table>

      {pkg.check_evidence.observed_checks.length > 0 && (
        <div className="row" style={{ marginTop: 10 }}>
          <span className="status">관찰된 모든 검사:</span>
          {pkg.check_evidence.observed_checks.map((o) => (
            <span key={o.observed_check_id} className={`tag ${strengthTag(o.check_strength)}`}>
              {o.check_type} · {o.check_strength}
            </span>
          ))}
        </div>
      )}

      <h4 className="mono" style={{ margin: "16px 0 6px", color: "var(--muted)" }}>
        신뢰도 분해 (연결 품질, 심각도 아님)
      </h4>
      {confRow("handler_mapping", c.handler_mapping)}
      {confRow("field_binding", c.field_binding)}
      {confRow("semantic_binding", c.semantic_binding)}
      {confRow("source_sink_flow", c.source_sink_flow)}
      {confRow("sink_mapping", c.sink_mapping)}
      {confRow("check_detection", c.check_detection)}
      {confRow("traceability", c.traceability)}

      <div className="row" style={{ marginTop: 12 }}>
        {pkg.related_cwe.map((w) => (
          <span key={w} className="badge">
            {w}
          </span>
        ))}
        {pkg.security_interpretation.root_cause_candidates.map((r) => (
          <span key={r} className="badge">
            {r}
          </span>
        ))}
      </div>

      {pkg.limitations.length > 0 && (
        <ul className="limits">
          {pkg.limitations.map((l, i) => (
            <li key={i}>{l}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default function F2AReport({ result }: { result: F2AResult }) {
  const hasPackages = result.evidence_packages.length > 0;
  const resolutions = result.handler_resolutions ?? [];

  return (
    <div className="report">
      <h2>F2-A 근거</h2>
      <p className="lead">
        확정된 취약점이 아니라 후보입니다 — 모든 항목은 파일/줄로 추적되어 F6로 전달됩니다.
        패키지 {result.evidence_packages.length}건 · 핸들러 판정 {resolutions.length}건.
      </p>

      {hasPackages && result.evidence_packages.map((pkg) => (
        <PackageCard key={pkg.evidence_id} pkg={pkg} />
      ))}

      {/* Handler-resolution is a first-class result: when there is no source→sink
          finding, show the per-action resolution through the SAME result card as
          vulnerability findings, not a parallel layout. */}
      {!hasPackages &&
        resolutions.length > 0 &&
        buildDecisions(result).map((d) => <ResultCard key={d.id} d={d} source="" />)}

      {!hasPackages && resolutions.length === 0 && (
        <div className="card">
          <h3>근거 패키지 없음</h3>
          <p className="status">
            이 CPG에서 소스→싱크 후보를 찾지 못했습니다. 알려진 OCPP 액션 핸들러가 위험한 싱크에
            도달하지 않는 한 정상입니다.
          </p>
          {result.handler_maps.length > 0 && (
            <div className="row">
              <span className="status">발견된 핸들러:</span>
              {result.handler_maps.map((h) => (
                <span key={h.handler_map_id} className="badge">
                  {h.action} → {h.handler.function}
                </span>
              ))}
            </div>
          )}
        </div>
      )}

      {result.limitations.length > 0 && (
        <div className="card">
          <h3>실행 한계</h3>
          <ul className="limits">
            {result.limitations.map((l, i) => (
              <li key={i}>{l}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
