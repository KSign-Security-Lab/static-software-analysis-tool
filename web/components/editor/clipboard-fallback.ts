function copyWithExecCommand(text: string): boolean {
  const area = document.createElement("textarea");
  area.value = text;
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
    if (previous && selection) {
      selection.removeAllRanges();
      selection.addRange(previous);
    }
  }
}

type ItemData = Record<string, Blob | string | Promise<Blob | string>>;

class FallbackClipboardItem {
  readonly types: string[];
  constructor(private readonly data: ItemData) {
    this.types = Object.keys(data);
  }
  async getType(type: string): Promise<Blob> {
    const value = await this.data[type];
    return value instanceof Blob ? value : new Blob([String(value ?? "")], { type });
  }
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
      const text = await item.text().catch(() => null);
      if (text) copyWithExecCommand(text);
    }
  },

  async readText(): Promise<string> {
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

  const existing = (window.navigator as unknown as { clipboard?: { write?: unknown } }).clipboard;
  if (typeof existing?.write === "function") return;

  Object.defineProperty(window.navigator, "clipboard", {
    value: clipboard,
    configurable: true,
    writable: true,
  });
}
