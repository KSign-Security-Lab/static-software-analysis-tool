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
      },
      {
        function: "handle_b",
        file: "u.c",
        line: 2,
        confidence: 0.56,
        evidence_kinds: ["REGISTRATION_ASSIGN"],
        action_id_consistency: "PARTIAL",
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
