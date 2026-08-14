"use client";

import { X } from "lucide-react";
import { createElement } from "react";

import { SEVERITY_DOT, SEVERITY_LABEL, type FileCount } from "@/lib/model/finding";
import { glyphForFile } from "@/lib/file-icon";
import { cn } from "@/lib/utils";

/**
 * The files this reader has open, and which one they are looking at.
 *
 * Not decoration. `?file=` is a single parameter, so every step of an evidence
 * trail *replaced* the open file: a claim whose 유입 is in `main.c`, 전파 in
 * `util.c` and 위험 지점 back in `main.c` walked the reader through three files
 * and left them no way back to the first. The trail is the best thing this app
 * does and it was one-way.
 *
 * Drawn to be found. The first version of this strip was 12px mono on a flat
 * band and read as a caption rather than as a control -- the tabs were there and
 * nobody could see them. The active one takes the editor's own background so it
 * reads as the front of a stack, the rest sit back on the darker band, and the
 * type icon carries a colour, which is what makes a row of filenames scannable
 * at a glance rather than legible on inspection.
 *
 * Sorted by nothing -- open order. A tab strip that re-sorts itself is a tab
 * strip you have to re-read every time you look at it.
 */
export default function FileTabs({
  open,
  active,
  dirty,
  counts,
  onPick,
  onClose,
}: {
  open: string[];
  active: string | null;
  dirty: string[];
  /** Per-file finding totals, from `countByFile` -- the explorer's own numbers. */
  counts: Map<string, FileCount>;
  onPick: (path: string) => void;
  onClose: (path: string) => void;
}) {
  if (open.length === 0) return null;

  const dirtySet = new Set(dirty);

  return (
    <div
      role="tablist"
      aria-label="열린 파일"
      className="flex h-9 shrink-0 items-stretch overflow-x-auto border-b border-line bg-surface-2"
    >
      {open.map((path) => {
        // The worst thing found in this file, so a tab can be triaged without
        // being opened -- the same dot and numbers the explorer shows, from the
        // same `countByFile`, so the two can never disagree.
        const count = counts.get(path);
        const glyph = glyphForFile(path);
        const current = path === active;

        return (
          <div
            key={path}
            className={cn(
              "group/tab relative flex min-w-0 shrink-0 items-center gap-2 border-r border-line pr-1.5 pl-3",
              current ? "bg-surface" : "text-ink-faint hover:bg-surface-3",
            )}
          >
            {/* The front of the stack. A background change alone is a shade
                somebody has to compare against its neighbour to notice. */}
            {current && <span aria-hidden className="absolute inset-x-0 top-0 h-0.5 bg-accent" />}

            <button
              type="button"
              role="tab"
              aria-selected={current}
              onClick={() => onPick(path)}
              className="flex min-w-0 items-center gap-2 py-1"
            >
              {createElement(glyph.icon, {
                className: cn("size-3.5 shrink-0", current ? glyph.tone : "opacity-70"),
              })}
              <span className={cn("min-w-0 truncate text-xs", current ? "text-ink-strong" : "text-ink-muted")}>
                {path.split("/").pop()}
              </span>
              {count && (
                <span
                  aria-hidden
                  title={`${SEVERITY_LABEL[count.worst ?? "info"]} · ${count.total}건`}
                  className={cn("size-1.5 shrink-0 rounded-full", SEVERITY_DOT[count.worst ?? "info"])}
                />
              )}
            </button>

            {/* A dot where the × goes until you reach for it. Two marks in one
                place would be the tab saying "unsaved" and "close" at once, and
                the reader only ever wants one of them. */}
            <span className="relative grid size-5 shrink-0 place-items-center">
              {dirtySet.has(path) && (
                <span
                  aria-hidden
                  className="size-1.5 rounded-full bg-accent-ink group-hover/tab:opacity-0"
                  title="저장되지 않음"
                />
              )}
              <button
                type="button"
                aria-label={`${path} 닫기`}
                onClick={() => onClose(path)}
                className="absolute inset-0 grid place-items-center rounded-sm text-ink-faint opacity-0 hover:bg-surface-3 hover:text-ink group-hover/tab:opacity-100 focus-visible:opacity-100"
              >
                <X className="size-3.5" />
              </button>
            </span>
          </div>
        );
      })}
    </div>
  );
}
