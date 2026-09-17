import {
  SEVERITY_ORDER,
  livenessOf,
  sortFindings,
  standingOf,
  type Liveness,
  type Severity,
  type Standing,
  type UiFinding,
} from "@/lib/model/finding";

export interface Facets {
  severity: Set<Severity>;
  cwe: Set<string>;
  file: Set<string>;
  standing: Set<Standing>;
  liveness: Set<Liveness>;
  query: string;
}

export const NO_FACETS: Facets = {
  severity: new Set(),
  cwe: new Set(),
  file: new Set(),
  standing: new Set(),
  liveness: new Set(),
  query: "",
};

export function isEmpty(facets: Facets): boolean {
  return (
    facets.severity.size === 0 &&
    facets.cwe.size === 0 &&
    facets.file.size === 0 &&
    facets.standing.size === 0 &&
    facets.liveness.size === 0 &&
    facets.query.trim() === ""
  );
}

function matchesQuery(finding: UiFinding, query: string): boolean {
  const needle = query.trim().toLowerCase();
  if (!needle) return true;
  return (
    finding.title.toLowerCase().includes(needle) ||
    (finding.cwe ?? "").toLowerCase().includes(needle) ||
    finding.primary.file.toLowerCase().includes(needle)
  );
}

export function matches(finding: UiFinding, facets: Facets): boolean {
  if (facets.severity.size > 0 && !facets.severity.has(finding.severity)) return false;
  if (facets.cwe.size > 0 && !facets.cwe.has(finding.cwe ?? UNCLASSIFIED)) return false;
  if (facets.file.size > 0 && !facets.file.has(finding.primary.file)) return false;
  if (facets.standing.size > 0) {
    const standing = standingOf(finding);
    if (standing === null || !facets.standing.has(standing)) return false;
  }
  if (facets.liveness.size > 0) {
    const liveness = livenessOf(finding);
    if (liveness === null || !facets.liveness.has(liveness)) return false;
  }
  return matchesQuery(finding, facets.query);
}

export const UNCLASSIFIED = "미분류";

export function apply(findings: UiFinding[], facets: Facets): UiFinding[] {
  return isEmpty(facets) ? findings : findings.filter((finding) => matches(finding, facets));
}

export type SortKey = "severity" | "file" | "confidence";

export function sort(findings: UiFinding[], key: SortKey): UiFinding[] {
  if (key === "severity") return sortFindings(findings);
  const rows = [...findings];
  if (key === "file") {
    rows.sort(
      (a, b) =>
        a.primary.file.localeCompare(b.primary.file) ||
        a.primary.startLine - b.primary.startLine ||
        SEVERITY_ORDER[a.severity] - SEVERITY_ORDER[b.severity],
    );
    return rows;
  }
  rows.sort(
    (a, b) =>
      b.confidence - a.confidence ||
      SEVERITY_ORDER[a.severity] - SEVERITY_ORDER[b.severity] ||
      a.primary.file.localeCompare(b.primary.file),
  );
  return rows;
}

export interface Tally<T extends string> {
  value: T;
  count: number;
}

export function bySeverity(findings: UiFinding[]): Tally<Severity>[] {
  const counts = new Map<Severity, number>();
  for (const finding of findings) counts.set(finding.severity, (counts.get(finding.severity) ?? 0) + 1);
  return [...counts.entries()]
    .sort((a, b) => SEVERITY_ORDER[a[0]] - SEVERITY_ORDER[b[0]])
    .map(([value, count]) => ({ value, count }));
}

export function byCwe(findings: UiFinding[]): Tally<string>[] {
  const counts = new Map<string, number>();
  for (const finding of findings) {
    const key = finding.cwe ?? UNCLASSIFIED;
    counts.set(key, (counts.get(key) ?? 0) + 1);
  }
  return [...counts.entries()]
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .map(([value, count]) => ({ value, count }));
}

export function byFile(findings: UiFinding[]): (Tally<string> & { worst: Severity })[] {
  const counts = new Map<string, { count: number; worst: Severity }>();
  for (const finding of findings) {
    const found = counts.get(finding.primary.file);
    if (!found) {
      counts.set(finding.primary.file, { count: 1, worst: finding.severity });
      continue;
    }
    found.count += 1;
    if (SEVERITY_ORDER[finding.severity] < SEVERITY_ORDER[found.worst]) found.worst = finding.severity;
  }
  return [...counts.entries()]
    .sort((a, b) => SEVERITY_ORDER[a[1].worst] - SEVERITY_ORDER[b[1].worst] || a[0].localeCompare(b[0]))
    .map(([value, { count, worst }]) => ({ value, count, worst }));
}

export function byLiveness(findings: UiFinding[]): Tally<Liveness>[] {
  const counts = new Map<Liveness, number>();
  for (const finding of findings) {
    const liveness = livenessOf(finding);
    if (liveness) counts.set(liveness, (counts.get(liveness) ?? 0) + 1);
  }
  const order: Liveness[] = ["live", "unreferenced", "unknown", "unreachable", "excluded"];
  return order.filter((each) => counts.has(each)).map((value) => ({ value, count: counts.get(value) ?? 0 }));
}

export function byStanding(findings: UiFinding[]): Tally<Standing>[] {
  const counts = new Map<Standing, number>();
  for (const finding of findings) {
    const standing = standingOf(finding);
    if (standing) counts.set(standing, (counts.get(standing) ?? 0) + 1);
  }
  const order: Standing[] = ["confirmed", "candidate"];
  return order.filter((each) => counts.has(each)).map((value) => ({ value, count: counts.get(value) ?? 0 }));
}

export function isFixable(finding: UiFinding): boolean {
  return Boolean(finding.replacement && finding.replacement.trim());
}

export function fixableCount(findings: UiFinding[], ids: Iterable<string>): number {
  const wanted = ids instanceof Set ? ids : new Set(ids);
  return findings.filter((finding) => wanted.has(finding.id) && isFixable(finding)).length;
}
