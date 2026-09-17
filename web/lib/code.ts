export type CodeTone = "source" | "sink" | "check-ok" | "check-weak" | "call" | "neutral";

export interface CodeRef {
  line: number;
  caption: string;
  tone: CodeTone;
  raw?: string;
}

export interface CodeGroup {
  start: number;
  end: number;
  refs: Map<number, { caption: string; tone: CodeTone }>;
}

export function sourceLines(source: string): string[] {
  return source.split(/\r?\n/);
}

export function buildGroups(refs: CodeRef[], lineCount: number, context = 2): CodeGroup[] {
  const valid = refs
    .filter((r) => Number.isFinite(r.line) && r.line >= 1 && r.line <= lineCount)
    .sort((a, b) => a.line - b.line);

  const groups: CodeGroup[] = [];
  for (const r of valid) {
    const last = groups[groups.length - 1];
    if (last && r.line - last.end <= context + 1) {
      last.end = Math.min(lineCount, r.line + context);
      last.refs.set(r.line, { caption: r.caption, tone: r.tone });
    } else {
      groups.push({
        start: Math.max(1, r.line - context),
        end: Math.min(lineCount, r.line + context),
        refs: new Map([[r.line, { caption: r.caption, tone: r.tone }]]),
      });
    }
  }
  return groups;
}
