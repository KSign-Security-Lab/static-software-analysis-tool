/**
 * A clipboard for pages that are not a secure context.
 *
 * `navigator.clipboard` only exists on HTTPS and on localhost. Reach this dev
 * server on the machine's LAN or tailnet address instead -- which is what a
 * browser on another machine has to do -- and it is `undefined`.
 *
 * That would be a footnote if Monaco only touched it when copying. It does
 * not: `BrowserClipboardService` registers a Safari workaround on `click` and
 * `keydown` over the whole editor container, and that handler calls
 * `navigator.clipboard.write(...)` with no guard at all (the try/catch further
 * down the file covers `writeText`, not this). So every click and every
 * keystroke in the editor threw
 *
 *     undefined is not an object (evaluating '…navigator.clipboard.write')
 *
 * and each one also left the DeferredPromise it had just cancelled without a
 * handler, which is the `unhandledRejection: Canceled` beside it.
 *
 * So: install one. `write` and `writeText` go through a hidden textarea and
 * `document.execCommand("copy")`, which still works without a secure context
 * and inside the user gesture these are called from. Reading is not offered --
 * no browser permits a silent read here -- and ⌘V never needed it, because a
 * real paste arrives as a native event carrying its own data.
 *
 * Installed only when the real thing is absent, so a normal https:// or
 * localhost page is untouched.
 */

/** Copy via the pre-async-clipboard mechanism. Must run inside a user gesture. */
function copyWithExecCommand(text: string): boolean {
  const area = document.createElement("textarea");
  area.value = text;
  // Off-screen rather than hidden: `display:none` cannot hold a selection.
  area.setAttribute("aria-hidden", "true");
  area.style.cssText = "position:fixed;top:-9999px;left:-9999px;opacity:0";
  document.body.appendChild(area);

  const selection = document.getSelection();
  const previous = selection && selection.rangeCount > 0 ? selection.getRangeAt(0) : null;

  try {
    area.select();
    return document.execCommand("copy");
  } catch {
    return false;
  } finally {
    area.remove();
    // Put the caret back: the editor's own selection is what the user sees,
    // and stealing it to copy would leave it stolen.
    if (previous && selection) {
      selection.removeAllRanges();
      selection.addRange(previous);
    }
  }
}

type ItemData = Record<string, Blob | string | Promise<Blob | string>>;

/** Enough of `ClipboardItem` for the one caller that constructs them. */
class FallbackClipboardItem {
  readonly types: string[];
  constructor(private readonly data: ItemData) {
    this.types = Object.keys(data);
  }
  async getType(type: string): Promise<Blob> {
    const value = await this.data[type];
    return value instanceof Blob ? value : new Blob([String(value ?? "")], { type });
  }
  /** Not part of the DOM interface; the shim below reads text back out. */
  async text(): Promise<string> {
    const value = await this.data["text/plain"];
    return value instanceof Blob ? value.text() : String(value ?? "");
  }
}

const clipboard = {
  async writeText(text: string): Promise<void> {
    if (!copyWithExecCommand(text)) throw new Error("clipboard write was refused");
  },

  async write(items: FallbackClipboardItem[]): Promise<void> {
    for (const item of items) {
      // The text is a promise that Monaco settles later -- on a real copy --
      // or cancels on the next click. Awaiting it here is what attaches the
      // handler its cancellation needs; without one it surfaces as an
      // unhandled rejection on every click.
      const text = await item.text().catch(() => null);
      if (text) copyWithExecCommand(text);
    }
  },

  async readText(): Promise<string> {
    // No browser allows a silent read outside a secure context. Empty rather
    // than thrown: Monaco guards this one, and pasting by keyboard or menu
    // does not come through here.
    return "";
  },

  async read(): Promise<FallbackClipboardItem[]> {
    return [];
  },
};

export function installClipboardFallback(): void {
  if (typeof window === "undefined") return;

  if (typeof window.ClipboardItem === "undefined") {
    Object.defineProperty(window, "ClipboardItem", {
      value: FallbackClipboardItem,
      configurable: true,
      writable: true,
    });
  }

  // Read through `unknown`: the DOM types declare `navigator.clipboard` as
  // always present, which is the very assumption this file exists to survive.
  const existing = (window.navigator as unknown as { clipboard?: { write?: unknown } }).clipboard;
  if (typeof existing?.write === "function") return;

  // `navigator.clipboard` has no setter and no prototype descriptor to shadow
  // when the API is absent, so it is defined onto the instance.
  Object.defineProperty(window.navigator, "clipboard", {
    value: clipboard,
    configurable: true,
    writable: true,
  });
}
