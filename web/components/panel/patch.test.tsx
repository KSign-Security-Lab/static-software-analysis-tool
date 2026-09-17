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
    render(<Patch diff={DIFF} />);

    expect(screen.queryByText(/--- a\/main\.c/)).toBeNull();
    expect(screen.queryByText(/\+\+\+ b\/main\.c/)).toBeNull();
    expect(screen.getByText("@@ -3,6 +3,6 @@")).toBeTruthy();
  });

  it("colours the change and leaves the context alone", () => {
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
    const { rerender } = render(<Verdict standing="confirmed" confidence={0.95} />);
    expect(screen.getByText(/취약 확인 · 95%/)).toBeTruthy();

    rerender(<Verdict standing="candidate" />);
    expect(screen.getByText("취약 후보")).toBeTruthy();
  });

  it("leaves the colour to the severity beside it", () => {
    render(<Verdict standing="confirmed" />);
    const badge = screen.getByText("취약 확인");
    expect(badge.className).not.toMatch(/text-(ok|danger)/);
  });
})
