"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useTheme } from "next-themes";
import { Contrast, PanelBottom, PanelLeft, PanelRight, RotateCcw } from "lucide-react";

import { useCommands } from "@/lib/commands/provider";
import type { Command } from "@/lib/commands/registry";
import { LAYOUT_COOKIE } from "@/lib/workbench/layout-cookie";
import { PERSPECTIVES, hrefFor } from "@/lib/workbench/perspectives";
import { PANE_LABEL, type PaneId } from "@/lib/workbench/store";
import { useWorkbench } from "@/lib/workbench/store-provider";

const PANE_BINDING: Record<PaneId, { key: string; icon: typeof PanelLeft }> = {
  side: { key: "mod+b", icon: PanelLeft },
  dock: { key: "mod+j", icon: PanelBottom },
  inspector: { key: "mod+alt+b", icon: PanelRight },
};

/**
 * The commands that belong to the shell rather than to any one surface.
 *
 * Registered once, high up, so every perspective inherits them; surfaces add
 * their own from their own components.
 */
export default function BuiltinCommands() {
  const router = useRouter();
  const params = useSearchParams();
  const { setTheme } = useTheme();
  const togglePane = useWorkbench((s) => s.togglePane);

  useCommands(() => {
    const panes: Command[] = (Object.keys(PANE_BINDING) as PaneId[]).map((id) => ({
      id: `workbench.toggle.${id}`,
      title: `${PANE_LABEL[id]} 접기/펼치기`,
      group: "패널",
      keybinding: PANE_BINDING[id].key,
      icon: PANE_BINDING[id].icon,
      run: () => togglePane(id),
    }));

    const navigation: Command[] = PERSPECTIVES.map((perspective, index) => ({
      id: `go.${perspective.id}`,
      title: perspective.label,
      group: "이동",
      keybinding: `mod+${index + 1}`,
      icon: perspective.icon,
      run: () => router.push(hrefFor(perspective.id, params)),
    }));

    return [
      ...panes,
      ...navigation,
      {
        id: "workbench.toggleTheme",
        title: "테마 전환",
        group: "보기",
        icon: Contrast,
        run: () => setTheme(document.documentElement.dataset.theme === "light" ? "dark" : "light"),
      },
      {
        id: "workbench.resetLayout",
        title: "레이아웃 초기화",
        group: "패널",
        icon: RotateCcw,
        run: () => {
          // Expiring the cookie and reloading is the whole reset: the layout
          // is server-rendered from it, so the next paint is the default.
          document.cookie = `${LAYOUT_COOKIE}=; Path=/; Max-Age=0; SameSite=Lax`;
          window.location.reload();
        },
      },
    ];
  }, [router, params, setTheme, togglePane]);

  return null;
}
