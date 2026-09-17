"use client";

import { useState } from "react";

import { cn } from "@/lib/utils";

const CLAMP_LINES = 6;
const CLAMP_CHARS = 400;

export function CodeBlock({
  text,
  mono = true,
  className,
}: {
  text: string;
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

export function Meta({ parts, className }: { parts: (string | false | null | undefined)[]; className?: string }) {
  const kept = parts.filter(Boolean) as string[];
  if (kept.length === 0) return null;
  return <p className={cn("font-mono text-2xs text-ink-faint", className)}>{kept.join(" · ")}</p>;
}
