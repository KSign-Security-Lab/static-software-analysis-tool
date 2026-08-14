/**
 * What a tool answered, as the facts it answered rather than as its transport.
 *
 * `find_definition("shorten")` returns 295 characters of pretty-printed JSON to
 * say two things: shorten is at util.c:2-6, and here is its body. The reader was
 * shown all 295, indented, with a `chunk_id` at the top -- a hash that joins two
 * tables on the server and means nothing to anybody looking at it. Six lines of
 * screen for one fact, in the pane where screen is scarcest.
 *
 * The whole tool surface answers in two shapes. The index tools -- definition,
 * callers, callees, neighbours, semantic search -- return a list of units. The
 * rest -- read_source, search_text, run_in_sandbox -- return text. So this is two
 * renderers, not ten, and it is keyed off the *shape* rather than off the tool's
 * name: a tool added later that answers in units gets the unit rendering without
 * anyone remembering to come back here.
 *
 * Anything else is returned as it arrived. A shape this does not recognise is not
 * licence to hide what it contains -- the same rule `unwrapToolOutput` follows,
 * and for the same reason: this pane is the audit trail.
 */

export interface ToolUnit {
  file: string;
  symbol: string;
  kind: string;
  startLine: number | null;
  endLine: number | null;
  /** Present on `find_definition`, which is the one that carries source. */
  body: string | null;
}

export type ToolResult =
  | { kind: "units"; units: ToolUnit[] }
  | { kind: "text"; text: string }
  /** The tool ran and refused. See `failure` for why this is not `call.error`. */
  | { kind: "failed"; message: string }
  | { kind: "empty" };

/**
 * A tool that answered with a complaint.
 *
 * `call.error` is for a tool that *threw*; a tool that ran and could not do what
 * it was asked returns a string, and the string is all the reader gets. So
 * `search_text` with a regex the model got wrong came back as
 * `error: invalid pattern: missing ), unterminated subpattern at position 6`,
 * rendered as the tool's answer at the same weight as an answer -- three lines of
 * red parser diagnostics standing where a result should be, on four calls in one
 * run.
 *
 * A prefix sniff, because there is no field for this on the wire. Source that
 * genuinely begins `error:` would be misread; it is still shown in full, one
 * click away, so the cost of being wrong is a fold rather than a lost fact.
 */
function failure(text: string): string | null {
  const match = /^(?:error|Error|ERROR)\s*:\s*(.+)/s.exec(text);
  return match ? match[1].trim() : null;
}

function str(value: unknown): string | null {
  return typeof value === "string" ? value : null;
}

function num(value: unknown): number | null {
  return typeof value === "number" ? value : null;
}

/** A unit, or null if this object is not one. Requires the two fields that name it. */
function unitOf(value: unknown): ToolUnit | null {
  if (value === null || typeof value !== "object" || Array.isArray(value)) return null;
  const row = value as Record<string, unknown>;
  const file = str(row.file);
  const symbol = str(row.symbol);
  if (file === null || symbol === null) return null;
  return {
    file,
    symbol,
    kind: str(row.kind) ?? "",
    startLine: num(row.start_line),
    endLine: num(row.end_line),
    body: str(row.body),
  };
}

export function toolResult(outputs: unknown): ToolResult {
  const text = typeof outputs === "string" ? outputs.trim() : null;
  if (text === null) return outputs === null || outputs === undefined ? { kind: "empty" } : { kind: "text", text: String(outputs) };
  if (!text) return { kind: "empty" };

  if (text.startsWith("[")) {
    try {
      const value: unknown = JSON.parse(text);
      if (Array.isArray(value)) {
        // Empty is an answer, and a common one: "nothing calls this" is exactly
        // what a specialist wanted to know.
        if (value.length === 0) return { kind: "empty" };
        const units = value.map(unitOf);
        if (units.every((each): each is ToolUnit => each !== null)) return { kind: "units", units };
      }
    } catch {
      // Truncated by the store, most likely. Still the answer it gave.
    }
  }

  const failed = failure(text);
  if (failed !== null) return { kind: "failed", message: failed };

  return { kind: "text", text };
}

/** `util.c:2-6`, or `util.c:2`, or `util.c`. */
export function whereOf(unit: ToolUnit): string {
  if (unit.startLine === null) return unit.file;
  if (unit.endLine === null || unit.endLine === unit.startLine) return `${unit.file}:${unit.startLine}`;
  return `${unit.file}:${unit.startLine}-${unit.endLine}`;
}
