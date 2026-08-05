"use client";

import { useEffect, useMemo, useState } from "react";

import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandShortcut,
} from "@/components/ui/command";
import { useCommandList, useCommands, useRegistry } from "@/lib/commands/provider";
import { prettyChord, type Command } from "@/lib/commands/registry";

/**
 * ⌘K.
 *
 * Registers its own open command, so the palette is reachable the same way as
 * everything else and there is no special case in the keyboard layer.
 */
export default function CommandPalette() {
  const [open, setOpen] = useState(false);
  const registry = useRegistry();
  const commands = useCommandList();

  useCommands(
    () => [
      {
        id: "workbench.commandPalette",
        title: "명령 팔레트",
        group: "보기",
        keybinding: "mod+k",
        run: () => setOpen((current) => !current),
      },
    ],
    [],
  );

  // Close on navigation away from whatever registered the command.
  useEffect(() => {
    if (!open) return;
    const onNavigate = () => setOpen(false);
    window.addEventListener("popstate", onNavigate);
    return () => window.removeEventListener("popstate", onNavigate);
  }, [open]);

  const grouped = useMemo(() => {
    const groups = new Map<string, Command[]>();
    for (const command of commands) {
      if (command.id === "workbench.commandPalette") continue;
      if (!(command.when?.() ?? true)) continue;
      const list = groups.get(command.group) ?? [];
      list.push(command);
      groups.set(command.group, list);
    }
    return [...groups.entries()];
  }, [commands]);

  return (
    <CommandDialog open={open} onOpenChange={setOpen} title="명령 팔레트" description="실행할 명령을 고르세요">
      <CommandInput placeholder="명령 검색…" />
      <CommandList>
        <CommandEmpty>일치하는 명령이 없습니다.</CommandEmpty>
        {grouped.map(([group, items]) => (
          <CommandGroup key={group} heading={group}>
            {items.map((command) => (
              <CommandItem
                key={command.id}
                // Searched text, so the id is matchable too -- typing "dock"
                // should find 하단 패널 without knowing the Korean label.
                value={`${command.title} ${command.id}`}
                onSelect={() => {
                  setOpen(false);
                  void registry.run(command.id);
                }}
              >
                {command.icon && <command.icon />}
                <span>{command.title}</span>
                {command.keybinding && <CommandShortcut>{prettyChord(command.keybinding)}</CommandShortcut>}
              </CommandItem>
            ))}
          </CommandGroup>
        ))}
      </CommandList>
    </CommandDialog>
  );
}
