"use client";

import { useState } from "react";

import { cn } from "@/lib/utils";

/** Lines shown before the rest has to be asked for. */
const CLAMP_LINES = 6;
const CLAMP_CHARS = 400;

/**
 * A block of text long enough to bury what comes after it.
 *
 * Clamped rather than folded: the first lines are on screen and the rest is one
 * click away. There were three of these -- a prompt, a tool result, a patch --
 * with three thresholds and three ways of saying how much was left.
 */
export function CodeBlock({
  text,
  mono = true,
  className,
}: {
  text: string;
  /** Off for prose: an explanation in a monospace column reads as data. */
  mono?: boolean;
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  const lines = text.split("\n");
  const long = lines.length > CLAMP_LINES || text.length > CLAMP_CHARS;
  const shown = open || !long ? text : lines.slice(0, CLAMP_LINES).join("\n").slice(0, CLAMP_CHARS);

  return (
    <div className={cn("space-y-0.5", className)}>
      <pre
        className={cn(
          "overflow-x-auto leading-relaxed whitespace-pre-wrap",
          mono ? "font-mono text-2xs text-ink-muted" : "font-sans text-xs text-ink",
        )}
      >
        {shown || "(비어 있음)"}
      </pre>
      {long && (
        <button
          type="button"
          onClick={() => setOpen(!open)}
          className="font-mono text-2xs text-ink-faint hover:text-ink-muted"
        >
          {open ? "접기" : `더 보기 · ${text.length.toLocaleString()}자`}
        </button>
      )}
    </div>
  );
}

/**
 * A line of numbers about something, in the one shape they take everywhere.
 *
 * The run tally, a step's cost and a unit's total were three renderings of "some
 * facts, separated by dots, quiet".
 */
export function Meta({ parts, className }: { parts: (string | false | null | undefined)[]; className?: string }) {
  const kept = parts.filter(Boolean) as string[];
  if (kept.length === 0) return null;
  return <p className={cn("font-mono text-2xs text-ink-faint", className)}>{kept.join(" · ")}</p>;
}
