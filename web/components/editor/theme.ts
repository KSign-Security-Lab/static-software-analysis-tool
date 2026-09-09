import type * as Monaco from "monaco-editor";

const THEME_NAME = "ssat";

function resolve(styles: CSSStyleDeclaration, token: string, fallback: string): string {
  const value = styles.getPropertyValue(token).trim();
  if (!value) return fallback;
  if (value.startsWith("#")) return value;
  return toHex(value) ?? fallback;
}

let probe: CanvasRenderingContext2D | null = null;

function toHex(colour: string): string | null {
  probe ??= document.createElement("canvas").getContext("2d");
  if (!probe) return null;
  probe.fillStyle = "#000000";
  probe.fillStyle = colour;
  const computed = probe.fillStyle;
  return typeof computed === "string" && computed.startsWith("#") ? computed : null;
}

export function defineTheme(monaco: typeof Monaco): string {
  const styles = getComputedStyle(document.documentElement);
  const dark = document.documentElement.dataset.theme !== "light";

  const bg = resolve(styles, "--field", dark ? "#0a0d12" : "#ffffff");
  const ink = resolve(styles, "--ink", dark ? "#e8eaed" : "#2b3036");
  const muted = resolve(styles, "--ink-muted", "#8a9099");
  const faint = resolve(styles, "--ink-faint", "#6b7178");
  const accent = resolve(styles, "--accent", "#4cc4b8");
  const alt = resolve(styles, "--alt", "#b08cf0");
  const warn = resolve(styles, "--warn", "#e0a33a");
  const ok = resolve(styles, "--ok", "#5cc98a");
  const danger = resolve(styles, "--danger", "#e4696b");
  const line = resolve(styles, "--line-2", dark ? "#2a2f36" : "#dfe3e8");
  const band = resolve(styles, "--surface-2", bg);

  monaco.editor.defineTheme(THEME_NAME, {
    base: dark ? "vs-dark" : "vs",
    inherit: true,
    rules: [
      { token: "comment", foreground: faint.slice(1), fontStyle: "italic" },
      { token: "keyword", foreground: alt.slice(1) },
      { token: "keyword.directive", foreground: danger.slice(1) },
      { token: "keyword.directive.include", foreground: danger.slice(1) },
      { token: "string", foreground: ok.slice(1) },
      { token: "string.include.identifier", foreground: ok.slice(1) },
      { token: "number", foreground: warn.slice(1) },
      { token: "type", foreground: accent.slice(1) },
      { token: "type.identifier", foreground: accent.slice(1) },
      { token: "identifier", foreground: ink.slice(1) },
      { token: "function", foreground: accent.slice(1) },
      { token: "operator", foreground: alt.slice(1) },
      { token: "delimiter", foreground: muted.slice(1) },
    ],
    colors: {
      "editor.background": bg,
      "editor.foreground": ink,
      "editorLineNumber.foreground": faint,
      "editorLineNumber.activeForeground": ink,
      "editorGutter.background": bg,
      "editor.lineHighlightBackground": band,
      "editor.lineHighlightBorder": "#00000000",
      "editorIndentGuide.background1": line,
      "editorWidget.background": resolve(styles, "--surface-2", bg),
      "editorWidget.border": line,
      "editorHoverWidget.background": resolve(styles, "--surface-2", bg),
      "editorHoverWidget.border": line,
      "editorSuggestWidget.background": resolve(styles, "--surface-2", bg),
      "scrollbarSlider.background": `${line}80`,
      "editorOverviewRuler.border": "#00000000",
      focusBorder: accent,
    },
  });

  return THEME_NAME;
}

export function followTheme(monaco: typeof Monaco, apply: (name: string) => void): () => void {
  const update = () => apply(defineTheme(monaco));
  update();

  const observer = new MutationObserver(update);
  observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
  return () => observer.disconnect();
}
