import { describe, expect, it, vi } from "vitest";

import { CommandRegistry, chordOf, prettyChord, type Command } from "./registry";

const command = (over: Partial<Command> = {}): Command => ({
  id: "test.one",
  title: "하나",
  group: "보기",
  run: () => {},
  ...over,
});

/** Enough of a KeyboardEvent for chordOf, which only reads five fields. */
const key = (over: Partial<KeyboardEvent>) =>
  ({ key: "a", metaKey: false, ctrlKey: false, altKey: false, shiftKey: false, ...over }) as KeyboardEvent;

describe("chordOf", () => {
  it("collapses meta and ctrl into one modifier, so bindings are written once", () => {
    expect(chordOf(key({ key: "s", metaKey: true }))).toBe("mod+s");
    expect(chordOf(key({ key: "s", ctrlKey: true }))).toBe("mod+s");
  });

  it("orders modifiers so the string can be compared to a literal", () => {
    expect(chordOf(key({ key: "m", metaKey: true, shiftKey: true, altKey: true }))).toBe("mod+alt+shift+m");
  });

  it("lower-cases the key, so shift+M is not a different binding from shift+m", () => {
    expect(chordOf(key({ key: "M", metaKey: true, shiftKey: true }))).toBe("mod+shift+m");
  });

  it("handles named keys", () => {
    expect(chordOf(key({ key: "Enter", metaKey: true }))).toBe("mod+enter");
    expect(chordOf(key({ key: "F8" }))).toBe("f8");
  });
});

describe("prettyChord", () => {
  it("renders the symbols a person recognises", () => {
    expect(prettyChord("mod+shift+m")).toBe("⌘⇧M");
    expect(prettyChord("mod+alt+b")).toBe("⌘⌥B");
    expect(prettyChord("mod+enter")).toBe("⌘↵");
  });

  it("spells the modifiers out away from Apple keyboards", () => {
    expect(prettyChord("mod+s", false)).toBe("Ctrl+S");
  });
});

describe("CommandRegistry", () => {
  it("lists what is registered and forgets it on unregister", () => {
    const registry = new CommandRegistry();
    const off = registry.register([command()]);
    expect(registry.getSnapshot()).toHaveLength(1);
    off();
    expect(registry.getSnapshot()).toHaveLength(0);
  });

  it("notifies subscribers when the set changes", () => {
    const registry = new CommandRegistry();
    const listener = vi.fn();
    registry.subscribe(listener);
    const off = registry.register([command()]);
    off();
    expect(listener).toHaveBeenCalledTimes(2);
  });

  it("keeps a stable snapshot between changes, for useSyncExternalStore", () => {
    // A new array on every read would make the store re-render forever.
    const registry = new CommandRegistry();
    registry.register([command()]);
    expect(registry.getSnapshot()).toBe(registry.getSnapshot());
  });

  it("hides a command whose `when` says it does not apply", () => {
    const registry = new CommandRegistry();
    registry.register([command({ when: () => false })]);
    expect(registry.getSnapshot()).toHaveLength(1);
    expect(registry.enabled()).toHaveLength(0);
  });

  it("matches a chord to the first enabled command bound to it", () => {
    // Three surfaces bind mod+enter to different things; whichever registered
    // later and is currently applicable wins.
    const registry = new CommandRegistry();
    registry.register([command({ id: "a", keybinding: "mod+enter", when: () => false })]);
    registry.register([command({ id: "b", keybinding: "mod+enter" })]);
    expect(registry.match("mod+enter")?.id).toBe("b");
  });

  it("does not match a chord nothing is bound to", () => {
    const registry = new CommandRegistry();
    registry.register([command({ keybinding: "mod+s" })]);
    expect(registry.match("mod+z")).toBeUndefined();
  });

  it("runs a command by id", async () => {
    const run = vi.fn();
    const registry = new CommandRegistry();
    registry.register([command({ id: "do.it", run })]);
    await registry.run("do.it");
    expect(run).toHaveBeenCalledOnce();
  });

  it("refuses to run a disabled command, even by id", () => {
    const run = vi.fn();
    const registry = new CommandRegistry();
    registry.register([command({ id: "do.it", run, when: () => false })]);
    void registry.run("do.it");
    expect(run).not.toHaveBeenCalled();
  });

  it("ignores an unknown id rather than throwing", async () => {
    await expect(new CommandRegistry().run("nope")).resolves.toBeUndefined();
  });
});
