import { describe, expect, it } from "vitest";

import { applyDraft, countOf, dirtyOf, type Drafts } from "./controls";

/**
 * The rules unsaved text follows.
 *
 * These exist because the old arrangement broke two of them at once. Drafts were
 * a `useState` in `EditorPane` keyed on `${runId}:${path}`, so anything that
 * changed the path -- including clicking a finding, which navigates -- reset it
 * and the reader's code was gone with 저장되지 않음 still on screen. And 검사
 * 실행 could only reach the file that happened to be open, so a scan reported on
 * code the reader had already changed elsewhere.
 *
 * Keyed by path is the whole repair, and it is asserted here rather than only in
 * a browser probe: the point is that no *other* key exists to reset by.
 */

const empty: Drafts = new Map();

describe("applyDraft", () => {
  it("keeps one draft per path, so files cannot overwrite each other", () => {
    let drafts = applyDraft(empty, "main.c", "AAA", "orig-main");
    drafts = applyDraft(drafts, "util.c", "BBB", "orig-util");

    expect(drafts.get("main.c")?.text).toBe("AAA");
    expect(drafts.get("util.c")?.text).toBe("BBB");
    expect(dirtyOf(drafts)).toEqual(["main.c", "util.c"]);
  });

  it("leaves the other paths alone when one is edited again", () => {
    // The case that used to lose work: edit, navigate away, come back.
    let drafts = applyDraft(empty, "main.c", "AAA", "orig-main");
    drafts = applyDraft(drafts, "util.c", "BBB", "orig-util");
    drafts = applyDraft(drafts, "util.c", "BBBB", "orig-util");

    expect(drafts.get("main.c")?.text).toBe("AAA");
    expect(drafts.get("util.c")?.text).toBe("BBBB");
  });

  it("drops a draft typed back to what the server holds", () => {
    // Otherwise edit-then-undo left the file dirty for ever and 검사 실행 kept
    // writing content the server already had.
    const drafts = applyDraft(applyDraft(empty, "main.c", "AAA", "orig"), "main.c", "orig", "orig");

    expect(drafts.has("main.c")).toBe(false);
    expect(dirtyOf(drafts)).toEqual([]);
  });

  it("does not mutate the map it was given", () => {
    const before = applyDraft(empty, "main.c", "AAA", "orig");
    applyDraft(before, "util.c", "BBB", "orig");

    expect([...before.keys()]).toEqual(["main.c"]);
  });

  it("treats an empty file as text, not as nothing", () => {
    // Clearing a file is an edit. `""` is falsy, which is how this kind of thing
    // usually comes to be silently dropped.
    const drafts = applyDraft(empty, "main.c", "", "orig");
    expect(drafts.get("main.c")?.text).toBe("");
    expect(dirtyOf(drafts)).toEqual(["main.c"]);
  });
});

describe("dirtyOf", () => {
  it("names every changed file, which is what 검사 실행 has to save", () => {
    let drafts = applyDraft(empty, "z.c", "1", "0");
    drafts = applyDraft(drafts, "a.c", "1", "0");
    // Sorted, so the writes go out in a stable order rather than insertion order.
    expect(dirtyOf(drafts)).toEqual(["a.c", "z.c"]);
  });

  it("is empty for a clean tree", () => {
    expect(dirtyOf(empty)).toEqual([]);
  });
});

describe("countOf", () => {
  it("counts both sides of a node", () => {
    expect(countOf({ before: ["triage"], after: ["verify", "gather"] })).toBe(3);
    expect(countOf({ before: [], after: [] })).toBe(0);
  });
});
