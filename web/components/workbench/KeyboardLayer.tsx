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
 * Registered on the capture phase, which is what makes "always" true. Monaco
 * treats ⌘K as the opening of one of its own two-key chords and stops the
 * event dead; a bubble-phase listener is simply never called, so the palette
 * could not be opened from the editor at all -- the one place a person is
 * most likely to reach for it. Save survived only because the editor
 * component registers it inside Monaco as well.
 */
// `mod+p` used to be here too, for a go-to-file that was never built. An
// exemption for a chord nothing binds reads as a feature when it is a no-op.
const ALWAYS = new Set(["mod+s", "mod+k"]);

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
      // Only where something else would otherwise act on it too: the editor
      // has its own binding for save, and would run it a second time.
      if (typing) event.stopPropagation();
      void command.run();
    };

    window.addEventListener("keydown", onKeyDown, true);
    return () => window.removeEventListener("keydown", onKeyDown, true);
  }, [registry]);

  return null;
}
