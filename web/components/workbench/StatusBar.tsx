"use client";

import { usePathname } from "next/navigation";

import { perspectiveFor } from "@/lib/workbench/perspectives";

/**
 * The 22px strip along the bottom.
 *
 * A flex sibling of the panel group like the activity bar, for the same
 * reason: it is a fixed height, and a percentage panel cannot promise that.
 * It fills with run state once the stream lands.
 */
export default function StatusBar() {
  const pathname = usePathname();
  const current = perspectiveFor(pathname);

  return (
    <footer className="flex h-[22px] shrink-0 items-center gap-3 border-t border-line bg-surface px-2.5 text-2xs text-ink-faint">
      <span className="text-ink-muted">{current?.label ?? "SSAT"}</span>
      <span className="truncate">{current?.note}</span>
      <span className="ml-auto">로컬 기록 · 외부 전송 없음</span>
    </footer>
  );
}
