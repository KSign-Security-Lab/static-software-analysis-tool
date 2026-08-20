import type { UiFinding } from "@/lib/model/finding";

/**
 * The file with a finding's replacement over the lines it points at.
 *
 * **For display only.** The patch that anybody downloads, applies or pushes is
 * spliced server-side by `agent.remediate.splice`, which checks the excerpt
 * still matches and refuses when it does not. This is the same arithmetic
 * without the refusal, because the worst it can do is render a confusing diff.
 *
 * Deliberately not shared with the server's version and deliberately not the
 * source of anything: two implementations of splicing would be a problem if
 * either could write a file, and only one of them can.
 *
 * The span is 1-based and inclusive, matching `Span` on the wire.
 */
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
