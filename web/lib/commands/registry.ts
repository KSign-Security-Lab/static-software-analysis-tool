import type { LucideIcon } from "lucide-react";

/**
 * Every action the workbench can perform, in one registry.
 *
 * Before this there were two hand-rolled `window` keydown listeners in
 * unrelated files, each with its own idea of what counts as a modifier, and
 * nothing that could list what the app is able to do. One registry gives the
 * palette its contents, the keyboard layer its bindings, and tooltips their
 * shortcut hints -- from the same declaration.
 */

export type CommandGroup = "파일" | "실행" | "패널" | "이동" | "보기";

export interface Command {
  /** Stable, dotted, and never shown to anyone: `workbench.toggleDock`. */
  id: string;
  title: string;
  group: CommandGroup;
  /** Normalised form: `mod+s`, `mod+shift+m`, `f8`. `mod` is ⌘ or Ctrl. */
  keybinding?: string;
  icon?: LucideIcon;
  /**
   * Whether the command applies right now. Three surfaces bind `mod+enter` to
   * different things, and the dispatcher takes the first enabled match.
   */
  when?: () => boolean;
  run: () => void | Promise<void>;
}

export type Unregister = () => void;

export class CommandRegistry {
  private readonly sources = new Map<symbol, Command[]>();
  private readonly listeners = new Set<() => void>();
  private snapshot: Command[] = [];

  /** Later registrations win a keybinding conflict, so pages beat defaults. */
  register(commands: Command[]): Unregister {
    const token = Symbol("commands");
    this.sources.set(token, commands);
    this.recompute();
    return () => {
      this.sources.delete(token);
      this.recompute();
    };
  }

  private recompute(): void {
    this.snapshot = [...this.sources.values()].flat();
    for (const listener of this.listeners) listener();
  }

  subscribe = (listener: () => void): Unregister => {
    this.listeners.add(listener);
    return () => void this.listeners.delete(listener);
  };

  /** Stable identity between recomputes, for useSyncExternalStore. */
  getSnapshot = (): Command[] => this.snapshot;

  /** Enabled commands only, in registration order. */
  enabled(): Command[] {
    return this.snapshot.filter((command) => command.when?.() ?? true);
  }

  find(id: string): Command | undefined {
    return this.snapshot.find((command) => command.id === id);
  }

  async run(id: string): Promise<void> {
    const command = this.find(id);
    if (!command || !(command.when?.() ?? true)) return;
    await command.run();
  }

  /** The first *enabled* command bound to this chord. */
  match(chord: string): Command | undefined {
    return this.enabled().find((command) => command.keybinding === chord);
  }
}

/**
 * A keyboard event as a chord string.
 *
 * `mod` collapses ⌘ and Ctrl so a binding is written once. Order is fixed so
 * the produced string can be compared to a literal.
 */
export function chordOf(event: KeyboardEvent): string {
  const parts: string[] = [];
  if (event.metaKey || event.ctrlKey) parts.push("mod");
  if (event.altKey) parts.push("alt");
  if (event.shiftKey) parts.push("shift");

  const key = event.key.length === 1 ? event.key.toLowerCase() : event.key.toLowerCase();
  parts.push(key);
  return parts.join("+");
}

/** `mod+shift+m` as the symbols a person recognises. */
export function prettyChord(chord: string, apple = true): string {
  return chord
    .split("+")
    .map((part) => {
      switch (part) {
        case "mod":
          return apple ? "⌘" : "Ctrl";
        case "alt":
          return apple ? "⌥" : "Alt";
        case "shift":
          return "⇧";
        case "enter":
          return "↵";
        case "arrowup":
          return "↑";
        case "arrowdown":
          return "↓";
        default:
          return part.length === 1 ? part.toUpperCase() : part.toUpperCase();
      }
    })
    .join(apple ? "" : "+");
}
