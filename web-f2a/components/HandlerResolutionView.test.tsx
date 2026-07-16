import { describe, it, expect } from "vitest";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import HandlerResolutionView from "@/components/HandlerResolutionView";
import DecisionView from "@/components/DecisionView";
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
        evidence: [],
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

describe("HandlerResolutionView", () => {
  it("renders one card per action with chosen / competitors / reason", () => {
    const html = renderToStaticMarkup(h(HandlerResolutionView, { resolutions }));
    expect(html).toContain("핸들러 판정");
    expect(html).toContain("RESOLVED");
    expect(html).toContain("remote_handler"); // RESOLVED chosen
    expect(html).toContain("AMBIGUOUS");
    expect(html).toContain("handle_a"); // both competing candidates retained
    expect(html).toContain("handle_b");
    expect(html).toContain("UNRESOLVED");
    expect(html).toContain("NO_EVIDENCE");
  });

  it("renders the evidence trail: registrar chain + paired field stores", () => {
    const html = renderToStaticMarkup(h(HandlerResolutionView, { resolutions }));
    // registrar chain (RESOLVED candidate)
    expect(html).toContain("DISPATCH_REGISTRAR_CALL");
    expect(html).toContain("store_handler(0, action, callback)");
    expect(html).toContain("CHAIN_STORE");
    // paired field-store trail (AMBIGUOUS candidate handle_a)
    expect(html).toContain("ACTION_STORE");
    expect(html).toContain("table_a[0].action = ACTION_DATA_TRANSFER");
    expect(html).toContain("SLOT");
    // scoring / provenance surfaced
    expect(html).toContain("site:registrar:99");
    expect(html).toContain("EXACT_IDENTIFIER");
  });
});

describe("DecisionView routing (the default 판단 tab)", () => {
  it("renders the Handler Resolution view when packages are empty but resolutions exist", () => {
    const html = renderToStaticMarkup(
      h(DecisionView, { result: baseResult({ handler_resolutions: resolutions }), source: "" }),
    );
    expect(html).toContain("핸들러 판정");
    expect(html).toContain("remote_handler");
    expect(html).toContain("handle_b");
  });

  it("falls back to the no-finding card when there are no resolutions", () => {
    const html = renderToStaticMarkup(
      h(DecisionView, { result: baseResult({ handler_resolutions: [] }), source: "" }),
    );
    expect(html).toContain("발견 없음");
    expect(html).not.toContain("핸들러 판정");
  });
});
