import type { EvidencePackage, PipelineFunction } from "./types";

/**
 * Put the analysis back on the source.
 *
 * Two sources of truth, deliberately kept apart because their reliability
 * differs:
 *
 * F2-A evidence carries real line numbers from the CPG, so those markers are
 * authoritative.
 *
 * The pipeline DFG carries only each node's `code` text -- the extractor never
 * emits a line -- so a def-use edge can only be placed by finding that text in
 * the source. Text that appears on more than one line is ambiguous and is
 * dropped rather than guessed at, the same rule the agent's anchor resolution
 * uses: an edge drawn on the wrong line is worse than an edge not drawn.
 */

export type MarkerTone = "source" | "sink" | "check-ok" | "check-weak" | "flow";

export interface LineMarker {
  line: number;
  tone: MarkerTone;
  label: string;
}

export interface DfgLink {
  fromLine: number;
  toLine: number;
  label: string;
}

export interface Annotation {
  markers: LineMarker[];
  links: DfgLink[];
  /** Edges dropped because their code could not be placed on exactly one line. */
  unplaced: number;
}

function toLine(value: string | number | undefined): number | null {
  const n = typeof value === "string" ? Number.parseInt(value, 10) : value;
  return Number.isFinite(n) && (n as number) > 0 ? (n as number) : null;
}

/** F2-A markers: real line numbers, so these are never guessed. */
export function evidenceMarkers(packages: EvidencePackage[]): LineMarker[] {
  const markers: LineMarker[] = [];
  for (const pkg of packages) {
    const ev = pkg.code_evidence;
    if (!ev) continue;

    const source = toLine(ev.source?.line);
    if (source) markers.push({ line: source, tone: "source", label: `유입: ${ev.source?.binding ?? ""}` });

    const sink = toLine(ev.sink?.line);
    if (sink) markers.push({ line: sink, tone: "sink", label: `위험 지점: ${ev.sink?.api ?? ""}` });

    for (const step of ev.flow ?? []) {
      const line = toLine(step.line);
      if (line) markers.push({ line, tone: "flow", label: `전파: ${step.operation ?? ""}` });
    }

    // Checks live under check_evidence, and their strength decides the tone:
    // a weak check is the usual reason a finding stands.
    for (const check of pkg.check_evidence?.observed_checks ?? []) {
      const line = toLine(check.line);
      if (!line) continue;
      markers.push({
        line,
        tone: /strong|adequate/i.test(check.check_strength ?? "") ? "check-ok" : "check-weak",
        label: `검증(${check.check_strength}): ${check.evidence ?? ""}`,
      });
    }
  }
  return dedupe(markers);
}

function dedupe(markers: LineMarker[]): LineMarker[] {
  const seen = new Map<string, LineMarker>();
  for (const m of markers) seen.set(`${m.line}:${m.tone}:${m.label}`, m);
  return [...seen.values()].sort((a, b) => a.line - b.line);
}

const TRIVIAL = new Set(["", "{", "}", "(", ")", ";", ",", "return", "0", "1", "NULL"]);

/**
 * Line a snippet sits on, or null when that cannot be decided.
 *
 * Requires exactly one match. Short or punctuation-only text is refused
 * outright -- `}` matches everywhere and would place an edge at random.
 */
export function lineOf(snippet: string, lines: string[]): number | null {
  const needle = snippet.trim();
  if (needle.length < 3 || TRIVIAL.has(needle)) return null;

  let found: number | null = null;
  for (let i = 0; i < lines.length; i++) {
    if (!lines[i].includes(needle)) continue;
    if (found !== null) return null; // ambiguous
    found = i + 1;
  }
  return found;
}

/** Def-use edges for one function, placed on source lines where possible. */
export function dfgLinks(fn: PipelineFunction, source: string): { links: DfgLink[]; unplaced: number } {
  const lines = source.split(/\r?\n/);
  const codeBySid = new Map((fn.ast?.nodes ?? []).map((n) => [n.sid, n.code ?? ""]));

  const lineCache = new Map<number, number | null>();
  const lineForSid = (sid: number): number | null => {
    if (!lineCache.has(sid)) lineCache.set(sid, lineOf(codeBySid.get(sid) ?? "", lines));
    return lineCache.get(sid) ?? null;
  };

  const links: DfgLink[] = [];
  const seen = new Set<string>();
  let unplaced = 0;

  for (const [src, dst, attrs] of fn.dfg?.edges_dfg ?? []) {
    const fromLine = lineForSid(src);
    const toLine = lineForSid(dst);
    if (fromLine === null || toLine === null || fromLine === toLine) {
      unplaced += 1;
      continue;
    }
    const label = String((attrs?.debug as { var_key?: unknown })?.var_key ?? "");
    const key = `${fromLine}->${toLine}:${label}`;
    if (seen.has(key)) continue;
    seen.add(key);
    links.push({ fromLine, toLine, label });
  }

  return { links, unplaced };
}

export function annotate(
  packages: EvidencePackage[],
  fn: PipelineFunction | null,
  source: string,
): Annotation {
  const markers = evidenceMarkers(packages);
  if (!fn) return { markers, links: [], unplaced: 0 };
  const { links, unplaced } = dfgLinks(fn, source);
  return { markers, links, unplaced };
}
