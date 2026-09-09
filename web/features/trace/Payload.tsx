"use client";

import { Badge } from "@/components/ui/badge";
import { isTruncated } from "@/lib/api/types";

export function Payload({ value, className }: { value: unknown; className?: string }) {
  if (value === null || value === undefined) return <p className="text-2xs text-ink-faint">없음</p>;

  if (isTruncated(value)) {
    return (
      <div className="space-y-1">
        <Badge variant="outline" className="px-1.5 py-0 text-2xs font-normal text-warn">
          잘림 · 20,000 / {value._chars.toLocaleString()}자
        </Badge>
        <pre className={className}>{value.preview}</pre>
      </div>
    );
  }

  const text = typeof value === "string" ? value : JSON.stringify(value, null, 2);
  return <pre className={className}>{text}</pre>;
}

export function promptOf(inputs: unknown): { system: string; user: string } {
  if (!inputs || typeof inputs !== "object") return { system: "", user: "" };
  const record = inputs as { messages?: { role?: string; content?: string }[]; prompts?: string[] };

  if (Array.isArray(record.messages)) {
    const system = record.messages.filter((m) => m.role === "system").map((m) => m.content ?? "");
    const rest = record.messages.filter((m) => m.role !== "system").map((m) => m.content ?? "");
    return { system: system.join("\n\n"), user: rest.join("\n\n") };
  }
  if (Array.isArray(record.prompts)) return { system: "", user: record.prompts.join("\n\n") };
  return { system: "", user: "" };
}
