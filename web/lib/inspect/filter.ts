import {
  SEVERITY_ORDER,
  sortFindings,
  standingOf,
  type Severity,
  type Standing,
  type UiFinding,
} from "@/lib/model/finding";

/**
 * Narrowing a report down to the rows worth reading.
 *
 * A scan of a real repository produces hundreds of findings, and the first
 * question is never "show me all of them" -- it is "the critical ones", "the
 * ones in this file", "the ones that survived verification". So the table
 * filters, and the filtering is here: pure functions over `UiFinding[]`, tested
 * without a browser, because an off-by-one in a severity comparison silently
 * hides a critical row.
 *
 * Every facet is a set of accepted values, and an empty set means "no opinion"
 * rather than "nothing". That is what makes the controls composable: a filter
 * nobody has touched cannot exclude anything.
 */

export interface Facets {
  severity: Set<Severity>;
  cwe: Set<string>;
  file: Set<string>;
  standing: Set<Standing>;
  /** Matched against the title, the CWE and the path. Case-insensitive. */
  query: string;
}

export const NO_FACETS: Facets = {
  severity: new Set(),
  cwe: new Set(),
  file: new Set(),
  standing: new Set(),
  query: "",
};

export function isEmpty(facets: Facets): boolean {
  return (
    facets.severity.size === 0 &&
    facets.cwe.size === 0 &&
    facets.file.size === 0 &&
    facets.standing.size === 0 &&
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
  return matchesQuery(finding, facets.query);
}

/** The CWE bucket for a finding the agent could not classify. */
export const UNCLASSIFIED = "미분류";

export function apply(findings: UiFinding[], facets: Facets): UiFinding[] {
  return isEmpty(facets) ? findings : findings.filter((finding) => matches(finding, facets));
}

export type SortKey = "severity" | "file" | "confidence";

/**
 * Row order.
 *
 * `severity` delegates to `sortFindings`, which is the report's own order and
 * already the shared definition of worst-first. The other two exist because a
 * reader working through one file wants that file's rows together, and a reader
 * deciding what to trust wants the confident ones first -- neither of which is
 * derivable from severity.
 */
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

/**
 * How many findings each severity has, worst first.
 *
 * Counted over the *unfiltered* report on purpose: these double as the filter
 * controls, and a control whose count changes when you press it cannot tell you
 * what pressing it would do.
 */
export function bySeverity(findings: UiFinding[]): Tally<Severity>[] {
  const counts = new Map<Severity, number>();
  for (const finding of findings) counts.set(finding.severity, (counts.get(finding.severity) ?? 0) + 1);
  return [...counts.entries()]
    .sort((a, b) => SEVERITY_ORDER[a[0]] - SEVERITY_ORDER[b[0]])
    .map(([value, count]) => ({ value, count }));
}

/** CWEs present, most frequent first, then by name so ties do not shuffle. */
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

/** Files with findings, worst first -- which is the order to open them in. */
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

export function byStanding(findings: UiFinding[]): Tally<Standing>[] {
  const counts = new Map<Standing, number>();
  for (const finding of findings) {
    const standing = standingOf(finding);
    if (standing) counts.set(standing, (counts.get(standing) ?? 0) + 1);
  }
  // Confirmed first: it is the half a reader acts on.
  const order: Standing[] = ["confirmed", "candidate"];
  return order.filter((each) => counts.has(each)).map((value) => ({ value, count: counts.get(value) ?? 0 }));
}

/**
 * Whether a finding carries code that can actually be applied.
 *
 * The tray and the patch dialog both need this: a bucket of ten where three
 * have no `replacement` produces a patch of seven, and saying so before the
 * download is the difference between a preview and a surprise.
 */
export function isFixable(finding: UiFinding): boolean {
  return Boolean(finding.replacement && finding.replacement.trim());
}

export function fixableCount(findings: UiFinding[], ids: Iterable<string>): number {
  const wanted = ids instanceof Set ? ids : new Set(ids);
  return findings.filter((finding) => wanted.has(finding.id) && isFixable(finding)).length;
}
