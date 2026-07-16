import { describe, it, expect } from "vitest";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import ResultCard from "@/components/ResultCard";
import DecisionView from "@/components/DecisionView";
import { buildDecisions } from "@/lib/decision";
import type { F2AResult, HandlerResolution } from "@/lib/types";

// createElement (not JSX) so the test file needs no JSX transform; the imported
// .tsx components still exercise the real render path.
const h = createElement;

const resolutions: HandlerResolution[] = [
  {
    action: "RemoteStartTransaction",
    status: "RESOLVED",
    chosen: { file: "u.c", function: "remote_handler", line: 15, language: "c" },
    candidates: [
      {
        function: "remote_handler",
        file: "u.c",
        line: 15,
        confidence: 0.8,
        evidence_kinds: ["REGISTRAR_CALL"],
        action_id_consistency: "PARTIAL",
        evidence: [
          {
            kind: "REGISTRAR_CALL",
            extractor: "registrar_call",
            match_strength: "EXACT_IDENTIFIER",
            action_id_consistency: "PARTIAL",
            provenance_group: "site:registrar:99",
            weight: 0.7,
            score: 0.7,
            score_pre_penalty: 0.7,
            action_id: { symbol: null, numeric_id: null, raw_expression: "ACTION_REMOTE_START" },
            dispatch_site: null,
            records: [
              { type: "DISPATCH_REGISTRAR_CALL", value: "register_handler(ACTION_REMOTE_START, remote_handler)", file: "u.c", line: 17 },
              { type: "CHAIN_CALL", value: "store_handler(0, action, callback)", file: "u.c", line: 15 },
              { type: "CHAIN_STORE", value: "handlers[slot].fn = callback", file: "u.c", line: 13 },
              { type: "HANDLER_REF", value: "remote_handler", file: "u.c", line: 15 },
            ],
          },
        ],
      },
    ],
    conflict: null,
    unresolved: null,
  },
  {
    action: "DataTransfer",
    status: "AMBIGUOUS",
    chosen: null,
    candidates: [
      {
        function: "handle_a",
        file: "u.c",
        line: 1,
        confidence: 0.56,
        evidence_kinds: ["REGISTRATION_ASSIGN"],
        action_id_consistency: "PARTIAL",
        evidence: [
          {
            kind: "REGISTRATION_ASSIGN",
            extractor: "registration_ast",
            match_strength: "HEURISTIC_SUBSTRING",
            action_id_consistency: "PARTIAL",
            provenance_group: "token:DataTransfer",
            weight: 0.8,
            score: 0.56,
            score_pre_penalty: 0.56,
            action_id: { raw_expression: "table_a[0].fn = handle_a" },
            dispatch_site: null,
            records: [
              { type: "ACTION_STORE", value: "table_a[0].action = ACTION_DATA_TRANSFER", file: "u.c", line: 20 },
              { type: "SLOT", value: "table_a[0]", file: "u.c", line: "" },
              { type: "HANDLER_REF", value: "handle_a", file: "u.c", line: 1 },
            ],
          },
        ],
      },
      {
        function: "handle_b",
        file: "u.c",
        line: 2,
        confidence: 0.56,
        evidence_kinds: ["REGISTRATION_ASSIGN"],
        action_id_consistency: "PARTIAL",
        evidence: [
          {
            kind: "REGISTRATION_ASSIGN",
            extractor: "registration_ast",
            match_strength: "HEURISTIC_SUBSTRING",
            action_id_consistency: "PARTIAL",
            provenance_group: "token:DataTransfer",
            weight: 0.8,
            score: 0.56,
            score_pre_penalty: 0.56,
            action_id: { raw_expression: "table_b[0].fn = handle_b" },
            dispatch_site: null,
            records: [
              { type: "ACTION_STORE", value: "table_b[0].action = ACTION_DATA_TRANSFER", file: "u.c", line: 30 },
              { type: "SLOT", value: "table_b[0]", file: "u.c", line: "" },
              { type: "HANDLER_REF", value: "handle_b", file: "u.c", line: 2 },
            ],
          },
        ],
      },
    ],
    conflict: { competing: [], margin: 0, note: "" },
    unresolved: null,
  },
  {
    action: "UpdateFirmware",
    status: "UNRESOLVED",
    chosen: null,
    candidates: [],
    conflict: null,
    unresolved: {
      reason: "NO_EVIDENCE",
      secondary: null,
      dispatch_site: null,
      attempted_extractors: ["name_match"],
    },
  },
];

function baseResult(overrides: Partial<F2AResult>): F2AResult {
  return {
    handler_maps: [],
    field_bindings: [],
    evidence_packages: [],
    candidate_fragments: [],
    limitations: [],
    ...overrides,
  };
}

describe("buildDecisions (handler resolutions → common result model)", () => {
  const decisions = buildDecisions(baseResult({ handler_resolutions: resolutions }));

  it("emits one decision per action, per-candidate for AMBIGUOUS, sorted", () => {
    // RESOLVED(1) + AMBIGUOUS(2 candidates) + UNRESOLVED(1) = 4, in status order.
    // Verdicts use analysis-specific terms, not generic status names.
    expect(decisions.map((d) => d.verdict)).toEqual([
      "핸들러 확인",
      "복수 후보",
      "복수 후보",
      "판정 불가",
    ]);
    expect(decisions.every((d) => d.kind === "handler")).toBe(true);
    // resolved reads as a non-security "info" state, not green/red
    expect(decisions[0].tone).toBe("info");
  });

  it("builds a numbered trace from the resolution evidence records", () => {
    const resolved = decisions[0];
    expect(resolved.trace.length).toBe(4); // registrar chain
    expect(resolved.trace[0].role).toBe("source");
    expect(resolved.trace[3].role).toBe("sink"); // HANDLER_REF
    // UNRESOLVED has no candidate → no trace
    const unresolved = decisions[3];
    expect(unresolved.trace.length).toBe(0);
  });
});

describe("ResultCard (handler decision)", () => {
  const decisions = buildDecisions(baseResult({ handler_resolutions: resolutions }));

  it("leads with the conclusion, then the registrar chain and friendly detail", () => {
    const html = renderToStaticMarkup(h(ResultCard, { d: decisions[0], source: "" }));
    expect(html).toContain("핸들러 확인"); // verdict badge (analysis-specific)
    expect(html).toContain("핸들러를 확인했습니다"); // conclusion headline
    expect(html).toContain("RemoteStartTransaction"); // action as eyebrow
    expect(html).toContain("판정 근거"); // trace section label
    expect(html).toContain("등록 함수 호출"); // koRecordType(DISPATCH_REGISTRAR_CALL)
    expect(html).toContain("store_handler(0, action, callback)");
    expect(html).toContain("remote_handler");
    // implementation terms rendered user-friendly, raw term kept in the tooltip
    expect(html).toContain("식별자 정확 일치"); // koMatchStrength(EXACT_IDENTIFIER)
    expect(html).toContain('title="EXACT_IDENTIFIER"'); // raw term available on hover
  });

  it("renders each AMBIGUOUS candidate's paired field-store trail separately", () => {
    const a = renderToStaticMarkup(h(ResultCard, { d: decisions[1], source: "" }));
    expect(a).toContain("복수 후보");
    expect(a).toContain("핸들러 후보가 여러 개입니다");
    expect(a).toContain("액션 저장"); // koRecordType(ACTION_STORE)
    expect(a).toContain("table_a[0].action = ACTION_DATA_TRANSFER");
    expect(a).toContain("슬롯"); // koRecordType(SLOT)
    expect(a).toContain("handle_a");
    const b = renderToStaticMarkup(h(ResultCard, { d: decisions[2], source: "" }));
    expect(b).toContain("table_b[0].action = ACTION_DATA_TRANSFER");
    expect(b).toContain("handle_b");
  });

  it("renders 판정 불가 with a plain-language reason and no trace", () => {
    const html = renderToStaticMarkup(h(ResultCard, { d: decisions[3], source: "" }));
    expect(html).toContain("판정 불가"); // verdict badge
    expect(html).toContain("핸들러를 확정하지 못했습니다"); // conclusion headline
    expect(html).toContain("근거 없음"); // koReason(NO_EVIDENCE)
    expect(html).toContain("NO_EVIDENCE"); // raw code still shown for auditability
    expect(html).not.toContain("판정 근거"); // no trace section
  });
});

describe("DecisionView routing (the default 판단 tab)", () => {
  it("renders a handler-resolution report when packages are empty but resolutions exist", () => {
    const html = renderToStaticMarkup(
      h(DecisionView, { result: baseResult({ handler_resolutions: resolutions }), source: "" }),
    );
    // single coherent report: summary line + chip row + first result card
    expect(html).toContain("액션별 핸들러 분석을 완료했습니다");
    expect(html).toContain("핸들러 확인 1"); // per-action count
    expect(html).toContain("판정 불가 1");
    expect(html).toContain("remote_handler"); // first (RESOLVED) card
  });

  it("falls back to the no-finding card when there are no resolutions", () => {
    const html = renderToStaticMarkup(
      h(DecisionView, { result: baseResult({ handler_resolutions: [] }), source: "" }),
    );
    expect(html).toContain("발견 없음");
    expect(html).not.toContain("액션별 핸들러 분석을 완료했습니다");
  });
});
