import type * as Monaco from "monaco-editor";

/**
 * Monaco, in the SSAT palette.
 *
 * Both editors were hardcoded to `vs-dark`, so the editor stayed dark inside a
 * light page -- a dark slab in the middle of a white workbench.
 *
 * Monaco takes literal colours in a theme object; it cannot read a CSS
 * variable. And the palette is OKLCH, which Monaco's parser does not accept
 * either. So the tokens are resolved through `getComputedStyle` -- the browser
 * converts them to a form it will take -- and the theme is rebuilt whenever
 * `data-theme` changes.
 */

const THEME_NAME = "ssat";

/** A CSS custom property as something Monaco will accept. */
function resolve(styles: CSSStyleDeclaration, token: string, fallback: string): string {
  const value = styles.getPropertyValue(token).trim();
  if (!value) return fallback;
  // Monaco wants #rrggbb. getComputedStyle gives us rgb()/oklab() depending on
  // the browser, so anything that is not already hex goes through a canvas,
  // which is the one converter every browser agrees on.
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
  const line = resolve(styles, "--line-2", dark ? "#2a2f36" : "#dfe3e8");

  monaco.editor.defineTheme(THEME_NAME, {
    base: dark ? "vs-dark" : "vs",
    inherit: true,
    rules: [
      { token: "comment", foreground: faint.slice(1), fontStyle: "italic" },
      { token: "keyword", foreground: alt.slice(1) },
      { token: "string", foreground: ok.slice(1) },
      { token: "number", foreground: warn.slice(1) },
      { token: "type", foreground: accent.slice(1) },
      { token: "identifier", foreground: ink.slice(1) },
      { token: "delimiter", foreground: muted.slice(1) },
    ],
    colors: {
      "editor.background": bg,
      "editor.foreground": ink,
      "editorLineNumber.foreground": faint,
      "editorLineNumber.activeForeground": ink,
      "editorGutter.background": bg,
      "editor.lineHighlightBorder": line,
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

/**
 * Keep the theme in step with the attribute.
 *
 * next-themes flips `data-theme` on <html>; nothing tells Monaco, so it has to
 * watch. Returns a teardown.
 */
export function followTheme(monaco: typeof Monaco, apply: (name: string) => void): () => void {
  const update = () => apply(defineTheme(monaco));
  update();

  const observer = new MutationObserver(update);
  observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
  return () => observer.disconnect();
}
