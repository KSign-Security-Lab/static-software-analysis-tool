import { describe, expect, it } from "vitest";

import { filesFromDrop, isArchiveDrop } from "./drop";

interface Entry {
  isFile: boolean;
  isDirectory: boolean;
  name: string;
  file?: (ok: (f: File) => void) => void;
  createReader?: () => { readEntries: (ok: (entries: Entry[]) => void) => void };
}

function file(name: string, text = ""): Entry {
  return {
    isFile: true,
    isDirectory: false,
    name,
    file: (ok) => ok(new File([text], name)),
  };
}

function dir(name: string, children: Entry[], batch = 100): Entry {
  return {
    isFile: false,
    isDirectory: true,
    name,
    createReader: () => {
      let at = 0;
      return {
        readEntries: (ok) => {
          const slice = children.slice(at, at + batch);
          at += slice.length;
          ok(slice);
        },
      };
    },
  };
}

function transfer(entries: Entry[], files: File[] = []): DataTransfer {
  return {
    items: entries.map((entry) => ({ kind: "file", webkitGetAsEntry: () => entry })),
    files,
  } as unknown as DataTransfer;
}

describe("filesFromDrop", () => {
  it("keeps the path a file had inside the dropped folder", async () => {
    const dropped = await filesFromDrop(
      transfer([dir("proj", [dir("src", [file("main.c")]), file("README.md")])]),
    );

    expect(dropped.map((each) => each.path).sort()).toEqual(["proj/README.md", "proj/src/main.c"]);
  });

  it("keeps two files of the same name apart, which is the bug it exists for", async () => {
    const dropped = await filesFromDrop(
      transfer([dir("proj", [dir("net", [file("main.c")]), dir("db", [file("main.c")])])]),
    );

    expect(dropped.map((each) => each.path).sort()).toEqual(["proj/db/main.c", "proj/net/main.c"]);
  });

  it("reads a directory past the first batch", async () => {
    const many = Array.from({ length: 250 }, (_, index) => file(`f${index}.c`));
    const dropped = await filesFromDrop(transfer([dir("big", many)]));

    expect(dropped).toHaveLength(250);
  });

  it("takes loose files dropped without a folder", async () => {
    const dropped = await filesFromDrop(transfer([file("net.c")]));
    expect(dropped.map((each) => each.path)).toEqual(["net.c"]);
  });

  it("falls back to the file list where the entries API is missing", async () => {
    const dropped = await filesFromDrop({
      items: [{ kind: "file", webkitGetAsEntry: undefined }],
      files: [new File(["x"], "solo.c"), new File(["y"], "other.c")],
    } as unknown as DataTransfer);

    expect(dropped.map((each) => each.path)).toEqual(["solo.c", "other.c"]);
  });

  it("ignores dragged text, which carries no entry", async () => {
    const dropped = await filesFromDrop({
      items: [{ kind: "string", webkitGetAsEntry: () => null }],
      files: [],
    } as unknown as DataTransfer);

    expect(dropped).toEqual([]);
  });
});

describe("what is not worth reading off somebody's disk", () => {
  it("does not descend into the directories the server discards anyway", async () => {
    const dropped = await filesFromDrop(
      transfer([
        dir("proj", [
          dir("src", [file("main.c")]),
          dir(".git", [dir("objects", [file("abcdef")])]),
          dir("node_modules", [dir("dep", [file("index.js")])]),
          dir("build", [file("out.o")]),
          dir("vendor", [file("thing.c")]),
        ]),
      ]),
    );

    expect(dropped.map((each) => each.path)).toEqual(["proj/src/main.c"]);
  });

  it("does not mistake a file for a directory of the same name", async () => {
    const dropped = await filesFromDrop(transfer([dir("proj", [file("build")])]));
    expect(dropped.map((each) => each.path)).toEqual(["proj/build"]);
  });
});

describe("isArchiveDrop", () => {
  it("recognises a bare zip, which goes to a different endpoint", async () => {
    const dropped = await filesFromDrop(transfer([file("project.zip")]));
    expect(isArchiveDrop(dropped)).toBe(true);
  });

  it("is case-insensitive, because Windows", async () => {
    const dropped = await filesFromDrop(transfer([file("Project.ZIP")]));
    expect(isArchiveDrop(dropped)).toBe(true);
  });

  it("treats a zip inside a dropped folder as a tree with one file in it", async () => {
    const dropped = await filesFromDrop(transfer([dir("proj", [file("inner.zip")])]));
    expect(dropped.map((each) => each.path)).toEqual(["proj/inner.zip"]);
    expect(isArchiveDrop(dropped)).toBe(false);
  });

  it("is not an archive when several things were dropped", async () => {
    const dropped = await filesFromDrop(transfer([file("a.zip"), file("b.zip")]));
    expect(isArchiveDrop(dropped)).toBe(false);
  });

  it("is not an archive when a folder was dropped", async () => {
    const dropped = await filesFromDrop(transfer([dir("proj", [file("main.c")])]));
    expect(isArchiveDrop(dropped)).toBe(false);
  });
});
