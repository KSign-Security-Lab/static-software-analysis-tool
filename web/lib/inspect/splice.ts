import type { UiFinding } from "@/lib/model/finding";

export function splice(source: string, finding: UiFinding): string {
  const replacement = finding.replacement;
  if (!replacement) return source;

  const lines = source.split("\n");
  const start = finding.primary.startLine;
  const end = finding.primary.endLine;
  if (start < 1 || end > lines.length || end < start) return source;

  return [...lines.slice(0, start - 1), ...replacement.replace(/^\n+|\n+$/g, "").split("\n"), ...lines.slice(end)].join(
    "\n",
  );
}
