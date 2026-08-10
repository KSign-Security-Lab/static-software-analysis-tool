import { afterEach, describe, expect, it, vi } from "vitest";

import { installClipboardFallback } from "./clipboard-fallback";

/**
 * The shim only matters where the real API is missing, so both halves are
 * worth pinning: that it fills the gap, and that it never touches a browser
 * that already has one.
 */

function forgetClipboard() {
  Reflect.deleteProperty(window.navigator, "clipboard");
  Reflect.deleteProperty(window, "ClipboardItem");
}

afterEach(() => {
  forgetClipboard();
  vi.restoreAllMocks();
});

describe("installClipboardFallback", () => {
  it("does nothing when the page already has a clipboard", () => {
    const real = { write: () => Promise.resolve() };
    Object.defineProperty(window.navigator, "clipboard", { value: real, configurable: true });

    installClipboardFallback();

    expect(window.navigator.clipboard).toBe(real);
  });

  it("supplies clipboard and ClipboardItem when they are absent", () => {
    forgetClipboard();

    installClipboardFallback();

    expect(typeof window.navigator.clipboard?.write).toBe("function");
    expect(typeof window.ClipboardItem).toBe("function");
  });

  it("copies the text of an item through execCommand", async () => {
    forgetClipboard();
    installClipboardFallback();
    const exec = vi.fn(() => true);
    document.execCommand = exec as unknown as typeof document.execCommand;

    const item = new window.ClipboardItem({ "text/plain": Promise.resolve("copied") });
    await window.navigator.clipboard.write([item]);

    expect(exec).toHaveBeenCalledWith("copy");
  });

  it("survives the item whose text is never provided", async () => {
    // Monaco calls write() on *every* click with a promise it settles only on
    // a real copy, and cancels on the next one. That rejection must not
    // escape: unhandled, it was one console error per click.
    forgetClipboard();
    installClipboardFallback();
    const exec = vi.fn(() => true);
    document.execCommand = exec as unknown as typeof document.execCommand;

    const item = new window.ClipboardItem({ "text/plain": Promise.reject(new Error("Canceled")) });
    await expect(window.navigator.clipboard.write([item])).resolves.toBeUndefined();

    expect(exec).not.toHaveBeenCalled();
  });

  it("reports a refused write rather than claiming success", async () => {
    forgetClipboard();
    installClipboardFallback();
    document.execCommand = (() => false) as unknown as typeof document.execCommand;

    await expect(window.navigator.clipboard.writeText("x")).rejects.toThrow(/refused/);
  });
});
