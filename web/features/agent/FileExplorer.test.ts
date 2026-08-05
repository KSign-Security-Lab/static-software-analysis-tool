import { describe, expect, it } from "vitest";

import { validateName } from "./FileExplorer";

/**
 * The old flow was `window.prompt`, and its result went straight into
 * `PUT /file` unchecked -- so the UI accepted `../../etc/passwd` and only the
 * server's path resolver refused it, with a 400 and no explanation. These are
 * the cases that used to reach the network.
 */
describe("validateName", () => {
  const existing = ["main.c", "src/app.c"];

  it("accepts an ordinary name", () => {
    expect(validateName("util.c", existing)).toBeNull();
  });

  it("accepts a nested path, since directories are created on write", () => {
    expect(validateName("src/net/http.c", existing)).toBeNull();
  });

  it("trims before judging", () => {
    expect(validateName("  util.c  ", existing)).toBeNull();
  });

  it("refuses an empty name", () => {
    expect(validateName("", existing)).toMatch(/입력/);
    expect(validateName("   ", existing)).toMatch(/입력/);
  });

  it("refuses an absolute path", () => {
    expect(validateName("/etc/passwd", existing)).toMatch(/절대 경로/);
  });

  it.each(["../secrets", "../../etc/passwd", "src/../../out", "a/../../b"])("refuses traversal via %s", (name) => {
    expect(validateName(name, existing)).toMatch(/상위 디렉터리/);
  });

  it("allows a name that merely contains dots", () => {
    expect(validateName("a..b.c", existing)).toBeNull();
    expect(validateName("...hidden.c", existing)).toBeNull();
  });

  it("refuses characters a path should not carry", () => {
    for (const name of ["a:b.c", "a*b.c", 'a"b.c', "a<b.c", "a|b.c", "a\\b.c"]) {
      expect(validateName(name, existing)).toMatch(/쓸 수 없습니다/);
    }
  });

  it("refuses a directory", () => {
    expect(validateName("src/", existing)).toMatch(/파일 이름/);
  });

  it("refuses a duplicate, rather than silently overwriting", () => {
    expect(validateName("main.c", existing)).toMatch(/이미 있습니다/);
    expect(validateName("src/app.c", existing)).toMatch(/이미 있습니다/);
  });
});
