import type { UiFinding } from "@/lib/model/finding";
import { claimOf, type Exchange, type Unit } from "./process";

/**
 * The run as one list.
 *
 * 문제 and 기록 were two tabs, and they were never two things. A finding is not a
 * separate artefact from the record -- it *is* the row where the pipeline decided
 * about a claim -- so reading one finding's reasoning meant hopping between two
 * lists of the same events. Here there is one list and a filter over it.
 *
 * A row is therefore one of two things, and the distinction is not cosmetic:
 *
 *   finding -- the pipeline reached a verdict about a claim. Carries the finding,
 *              and the call that reached it when this run recorded one.
 *   call    -- a model call that did not itself conclude anything reportable.
 *
 * `call` is nullable on a finding row and that is the whole reason this is not
 * simply "exchanges, some of which are findings": a re-run reuses cached units,
 * and a cached unit is not re-read, so its findings are in the report with no
 * calls behind them in *this* run. A list built from exchanges alone would drop
 * them silently -- the report would say 2건 and the panel would show one.
 */
export type Row =
  | { kind: "finding"; id: string; finding: UiFinding; call: Exchange | null }
  | { kind: "call"; id: string; call: Exchange };

export interface RowGroup {
  /** The file, or the unit's own name when the index could not place it. */
  file: string;
  units: { id: string; name: string; rows: Row[] }[];
}

/**
 * Which call reached the verdict on a claim.
 *
 * By subject, which is the join the whole trace surface uses: `call_config` names
 * a span `verify:CWE-78 main.c:6`, and `claimOf` builds the same string from the
 * finding. `verify` before `gather` because the verdict is the decision and the
 * gathering is what it was decided on; a pipeline with verification switched off
 * still has a `gather`, and a row is better than no row.
 */
function decidingCall(exchanges: Exchange[], finding: UiFinding): Exchange | null {
  const claim = claimOf(finding);
  const about = exchanges.filter((each) => each.subject === claim);
  return about.find((each) => each.step === "verify") ?? about.find((each) => each.step === "gather") ?? null;
}

/** True for the chunk holding a file's top-level declarations -- its symbol is the filename. */
function isWholeFile(unit: Unit): boolean {
  return Boolean(unit.symbol) && unit.symbol === unit.file;
}

/**
 * Every row this run produced, grouped by file and unit.
 *
 * Order is the run's own: a unit's calls in the order they were made, with the
 * call that reached a verdict replaced in place by the finding it reached. So the
 * argument reads top to bottom -- screening, the specialist, the evidence, the
 * verdict -- and the verdict row is the finding rather than a row pointing at one.
 *
 * Findings with no call in this run are appended to their unit, and findings whose
 * unit is not in this run at all get a group of their own rather than vanishing.
 */
export function rowsOf(units: Unit[], findings: UiFinding[]): RowGroup[] {
  const claimed = new Set<string>();
  const placed = new Set<string>();
  const groups: RowGroup[] = [];

  const groupFor = (file: string): RowGroup => {
    const found = groups.find((each) => each.file === file);
    if (found) return found;
    const made: RowGroup = { file, units: [] };
    groups.push(made);
    return made;
  };

  for (const unit of units) {
    const mine = findings.filter((each) => each.chunkIds.includes(unit.id));
    const rows: Row[] = [];

    for (const exchange of unit.exchanges) {
      const finding = mine.find((each) => decidingCall(unit.exchanges, each)?.id === exchange.id);
      if (finding && !placed.has(finding.id)) {
        placed.add(finding.id);
        claimed.add(exchange.id);
        rows.push({ kind: "finding", id: finding.id, finding, call: exchange });
      } else if (!claimed.has(exchange.id)) {
        rows.push({ kind: "call", id: exchange.id, call: exchange });
      }
    }

    // Reported here, decided in a run we are not looking at.
    for (const finding of mine) {
      if (placed.has(finding.id)) continue;
      placed.add(finding.id);
      rows.push({ kind: "finding", id: finding.id, finding, call: null });
    }

    const file = unit.file ?? unit.symbol ?? unit.id;
    groupFor(file).units.push({
      id: unit.id,
      // The file chunk holds the declarations above every function, and its
      // symbol *is* the filename -- which is how it came to sit in the list
      // looking like a second copy of its own file.
      name: isWholeFile(unit) ? "최상위 선언" : (unit.symbol ?? unit.id),
      rows,
    });
  }

  // Whole units missing from this run: the same cache, one level up.
  const orphans = findings.filter((each) => !placed.has(each.id));
  for (const finding of orphans) {
    const file = finding.primary.file;
    const group = groupFor(file);
    const bucket = group.units.find((each) => each.id === "__orphans");
    const row: Row = { kind: "finding", id: finding.id, finding, call: null };
    if (bucket) bucket.rows.push(row);
    else group.units.push({ id: "__orphans", name: "지난 검사에서", rows: [row] });
  }

  return groups;
}

/**
 * What each filter keeps.
 *
 * `problems` is the answer, `all` is the record, `tools` is "what did it actually
 * go and read" -- a real question whose answer is a handful of rows scattered
 * through the whole record. A finding row is not a lookup, so `tools` drops it
 * even though it is the most important kind of row: the filter means what it says.
 */
export function keeps(row: Row, filter: "problems" | "all" | "tools"): boolean {
  if (filter === "problems") return row.kind === "finding";
  if (filter === "tools") return row.kind === "call" && row.call.calls.length > 0;
  return true;
}

/** The groups with a filter applied, dropping units and files left with nothing. */
export function filterRows(groups: RowGroup[], filter: "problems" | "all" | "tools"): RowGroup[] {
  return groups
    .map((group) => ({
      ...group,
      units: group.units
        .map((unit) => ({ ...unit, rows: unit.rows.filter((row) => keeps(row, filter)) }))
        .filter((unit) => unit.rows.length > 0),
    }))
    .filter((group) => group.units.length > 0);
}

/** How many rows survive a filter, for a count beside its name. */
export function countKept(groups: RowGroup[], filter: "problems" | "all" | "tools"): number {
  return groups.reduce(
    (sum, group) =>
      sum + group.units.reduce((n, unit) => n + unit.rows.filter((row) => keeps(row, filter)).length, 0),
    0,
  );
}
