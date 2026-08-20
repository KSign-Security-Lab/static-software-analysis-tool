import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { UiFinding } from "@/lib/model/finding";
import FindingRow from "./FindingRow";

/**
 * What a row says, and what it does not.
 *
 * The row is the densest thing on the surface -- severity, title, CWE, location,
 * standing, fixability and a tick, in about forty pixels -- so the decisions
 * about what earns space are worth pinning. Two in particular: `패치 없음` appears
 * only where it is true, because a badge on every row is a badge nobody reads;
 * and a finding with no code can still be ticked, because the patch dialog offers
 * to write some and refusing the tick would hide that door.
 */

afterEach(cleanup);

function finding(over: Partial<UiFinding> = {}): UiFinding {
  return {
    id: "agent:f1",
    engine: "agent",
    chunkId: "c1",
    severity: "critical",
    title: "셸로 넘어가는 입력",
    cwe: "CWE-78",
    primary: { file: "src/app.c", startLine: 42, startColumn: 1, endLine: 42, endColumn: 1, excerpt: "" },
    explanation: "",
    evidence: [],
    remediation: null,
    replacement: "int safe = 1;",
    diff: null,
    chunkIds: ["c1"],
    mergedIds: [],
    confidence: 0.9,
    verified: true,
    raw: {} as UiFinding["raw"],
    ...over,
  };
}

describe("what the row shows", () => {
  it("names the severity for a screen reader, since the dot is only a colour", () => {
    render(<FindingRow finding={finding()} />);
    expect(screen.getByText("치명적")).toBeInTheDocument();
  });

  it("shows the title, the cwe and the location", () => {
    render(<FindingRow finding={finding()} />);
    expect(screen.getByText("셸로 넘어가는 입력")).toBeInTheDocument();
    expect(screen.getByText("CWE-78")).toBeInTheDocument();
    expect(screen.getByText("src/app.c:42")).toBeInTheDocument();
  });

  it("says nothing about a patch when there is one", () => {
    render(<FindingRow finding={finding()} />);
    expect(screen.queryByText("패치 없음")).toBeNull();
  });

  it("marks a finding that carries advice and no code", () => {
    render(<FindingRow finding={finding({ replacement: null })} />);
    expect(screen.getByText("패치 없음")).toBeInTheDocument();
  });

  it("treats whitespace as no code", () => {
    render(<FindingRow finding={finding({ replacement: "  \n " })} />);
    expect(screen.getByText("패치 없음")).toBeInTheDocument();
  });

  it("says when one claim was reported by more than one unit", () => {
    // The chunker makes a unit of a file and a unit of each function in it, so a
    // problem inside a function is read twice and reported twice. Merged into
    // one row -- and the row says so rather than looking like a lone reading.
    render(<FindingRow finding={finding({ chunkIds: ["c1", "c2"] })} />);
    expect(screen.getByText("2회 보고")).toBeInTheDocument();
  });

  it("badges the standing, and omits it where the notion does not apply", () => {
    render(<FindingRow finding={finding({ verified: true })} />);
    expect(screen.getByText(/취약 확인/)).toBeInTheDocument();
    cleanup();
    // F2-A findings never go near a verifier, so `null` is no state rather than
    // a third one, and a badge would invent a step that did not happen.
    render(<FindingRow finding={finding({ verified: null })} />);
    expect(screen.queryByText(/취약 확인|취약 후보/)).toBeNull();
  });
});

describe("the tick", () => {
  it("is absent unless the row can be put in the bucket", () => {
    render(<FindingRow finding={finding()} />);
    expect(screen.queryByRole("checkbox")).toBeNull();
  });

  it("is offered even for a finding with no code, because one can be asked for", () => {
    const onTick = vi.fn();
    render(<FindingRow finding={finding({ replacement: null })} ticked={false} onTick={onTick} />);
    expect(screen.getByRole("checkbox")).toBeInTheDocument();
  });

  it("reports a tick without opening the row", async () => {
    // The checkbox stops propagation: ticking forty rows should not drag the
    // detail panel through forty findings on the way.
    const onTick = vi.fn();
    const onOpen = vi.fn();
    render(<FindingRow finding={finding()} ticked={false} onTick={onTick} onOpen={onOpen} />);

    await userEvent.click(screen.getByRole("checkbox"));

    expect(onTick).toHaveBeenCalledOnce();
    expect(onOpen).not.toHaveBeenCalled();
  });

  it("opens the row when the title is pressed", async () => {
    const onOpen = vi.fn();
    render(<FindingRow finding={finding()} onOpen={onOpen} />);
    await userEvent.click(screen.getByText("셸로 넘어가는 입력"));
    expect(onOpen).toHaveBeenCalledOnce();
  });

  it("is not a button at all when there is nothing to open", async () => {
    // The live list during a scan renders rows that cannot be opened yet.
    render(<FindingRow finding={finding()} />);
    expect(screen.getByRole("button")).toBeDisabled();
  });
});
