import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Patch } from "./patch";
import { Verdict } from "./verdict";

const DIFF = `--- a/main.c
+++ b/main.c
@@ -3,6 +3,6 @@
 void handle(const char *name) {
-    shorten(name, label, 64);
+    shorten(name, label, sizeof(label));
 }
`;

describe("Patch", () => {
  it("drops the file headers and keeps the hunk", () => {
    // They name a file the reader is looking at, in a pane attached to that file,
    // above a hunk header that gives the line. Three lines of a five-line patch
    // spent on where it applies, which was never in doubt.
    render(<Patch diff={DIFF} />);

    expect(screen.queryByText(/--- a\/main\.c/)).toBeNull();
    expect(screen.queryByText(/\+\+\+ b\/main\.c/)).toBeNull();
    expect(screen.getByText("@@ -3,6 +3,6 @@")).toBeTruthy();
  });

  it("colours the change and leaves the context alone", () => {
    // Whitespace is significant in a patch, so match on the raw text rather than
    // through testing-library's normalisation.
    const { container } = render(<Patch diff={DIFF} />);
    const lines = [...container.querySelectorAll("span")];
    const find = (starts: string) => lines.find((line) => line.textContent?.startsWith(starts))!;

    expect(find("-").className).toContain("text-danger");
    expect(find("+").className).toContain("text-ok");
    expect(find(" void").className).not.toMatch(/text-(ok|danger)/);
  });
});

describe("Verdict", () => {
  it("says which of the three states a claim is in", () => {
    // The state that used to be invisible: a finding over the verify cap was
    // never put to a verifier and read exactly like one that had been checked.
    const { rerender } = render(<Verdict standing="confirmed" confidence={0.95} />);
    expect(screen.getByText(/취약 확인 · 95%/)).toBeTruthy();

    rerender(<Verdict standing="candidate" />);
    expect(screen.getByText("취약 후보")).toBeTruthy();
  });

  it("leaves the colour to the severity beside it", () => {
    // Two marks competing to be the one that says how alarmed to be is how the
    // dock and the run record ended up showing one fact in opposite colours.
    render(<Verdict standing="confirmed" />);
    const badge = screen.getByText("취약 확인");
    expect(badge.className).not.toMatch(/text-(ok|danger)/);
  });
})
