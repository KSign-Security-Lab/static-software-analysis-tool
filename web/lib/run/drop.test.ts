import { describe, expect, it } from "vitest";

import { filesFromDrop } from "./drop";

/**
 * A dropped tree, walked back into paths.
 *
 * The whole reason this module exists is that a `File` out of a drop has lost
 * the directory it came from -- `webkitRelativePath` is empty -- so the paths
 * asserted below are the entire point. jsdom implements neither the entries API
 * nor `DataTransfer`, so both are stood up here in the shape the spec describes:
 * entries handed over synchronously, directories read in batches, and an empty
 * batch meaning the end.
 */

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

/** Reads at most `batch` entries per call, the way a real reader does. */
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
    // `readEntries` returns at most a hundred at a time and one call would
    // silently truncate -- a bug that only appears on somebody else's repo.
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
