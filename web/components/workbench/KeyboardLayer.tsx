"use client";

import { useEffect } from "react";

import { useRegistry } from "@/lib/commands/provider";
import { chordOf } from "@/lib/commands/registry";

/**
 * The one `window` keydown listener.
 *
 * Two chords are always allowed through, even from inside a text field or the
 * editor, because they are about the application rather than the text: save,
 * and the palette. Everything else defers -- ⌘F belongs to Monaco's find, and
 * a page-level binding that stole it would be worse than not having one.
 *
 * Save is *also* registered inside Monaco by the editor component, because a
 * window listener sees the key during bubble but the editor may have already
 * handled and stopped it.
 */
const ALWAYS = new Set(["mod+s", "mod+k", "mod+p"]);

const TEXT_ENTRY = "input, textarea, select, [contenteditable='true'], .monaco-editor";

export default function KeyboardLayer() {
  const registry = useRegistry();

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      // Let a chord in progress finish; IME composition swallows keys.
      if (event.isComposing) return;

      const chord = chordOf(event);
      const command = registry.match(chord);
      if (!command) return;

      const target = event.target as Element | null;
      const typing = target?.closest?.(TEXT_ENTRY);
      if (typing && !ALWAYS.has(chord)) return;

      event.preventDefault();
      void command.run();
    };

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [registry]);

  return null;
}
