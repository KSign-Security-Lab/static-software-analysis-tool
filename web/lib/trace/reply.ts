/**
 * What an agent said, split into the fields it said it in.
 *
 * Most replies here are not prose. Guided decoding forces them into a schema, so
 * what the trace holds is `{"worth_analysing": false, "lenses": [], "reason": …}`
 * -- correct, and in a chat it reads as a wall of braces and escapes. Split into
 * fields it reads as an answer.
 *
 * Field names are the model's own, not translations of them. `refuted` is what the
 * schema calls it, what the prompt asks for and what the prompt editor edits; a
 * Korean gloss is one more name for the same thing and one more place for the two
 * to disagree.
 *
 * Values are shown as the text they already were. A reply may contain a diff, or
 * an injected prompt, and putting it through anything that renders is how a reader
 * stops being able to see what the model actually said.
 */

export interface Field {
  key: string;
  /** A scalar, shown inline. */
  value?: string;
  /** Anything nested: a count to show, and the JSON behind it. */
  nested?: { summary: string; json: string };
}

export type Reply =
  | { kind: "text"; text: string }
  | { kind: "fields"; fields: Field[] }
  /** Answered in the required shape with nothing in it. Carries what it sent. */
  | { kind: "blank"; text: string }
  /** Did not answer at all. */
  | { kind: "empty" };

function scalar(value: unknown): string | null {
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  // An absent value is not a value. Rendered as "없음" it became a row of its own
  // on every turn, and thirteen rows of 없음 in one run is not an answer.
  if (value === null || value === undefined) return "";
  return null;
}

/**
 * A list of plain values is the values.
 *
 * `누구에게 · 2개` says nothing a reader wanted; `누구에게 · memory, injection`
 * is the answer. Only a list of scalars -- a list of objects genuinely does need
 * folding away.
 */
function flatList(value: unknown): string | null {
  if (!Array.isArray(value)) return null;
  const parts = value.map(scalar);
  return parts.every((each) => each !== null) ? parts.join(", ") : null;
}

/**
 * How much is behind a fold, without opening it.
 *
 * A count needs its unit. This was the bare number, and a specialist's whole
 * output -- the finding it raised -- sat behind a disclosure labelled `1`, which
 * says neither what it holds nor that there is anything to open.
 */
function summarise(value: unknown): string {
  if (Array.isArray(value)) return `${value.length}개`;
  return Object.keys(value as Record<string, unknown>).join(", ");
}

export function parseReply(reply: string | null): Reply {
  const text = reply?.trim();
  if (!text) return { kind: "empty" };

  // Only an object becomes fields. A bare array or scalar is not an answer with
  // parts, and a tool loop's reply is prose that happens to start with a brace
  // far less often than it starts with a word.
  if (!text.startsWith("{")) return { kind: "text", text };

  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch {
    // Truncated by the store, or cut off by max_tokens. Still the reply.
    return { kind: "text", text };
  }
  if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) {
    return { kind: "text", text };
  }

  // Empty fields are dropped rather than shown as empty. A lens that found
  // nothing used to render `찾은 것 없음` and `호출자에게 남기는 메모 비어 있음`
  // one under the other, on every one of its turns; "it found nothing" is one
  // fact and belongs in one line.
  const fields: Field[] = [];
  for (const [key, value] of Object.entries(parsed as Record<string, unknown>)) {
    const flat = scalar(value) ?? flatList(value);
    if (flat !== null) {
      if (flat.trim()) fields.push({ key, value: flat });
      continue;
    }
    if (Array.isArray(value) ? value.length > 0 : Object.keys(value as object).length > 0) {
      fields.push({ key, nested: { summary: summarise(value), json: JSON.stringify(value, null, 2) } });
    }
  }
  // Nothing in it: show the object it sent rather than a sentence about it. It is
  // one short line, and it is the fact.
  return fields.length > 0 ? { kind: "fields", fields } : { kind: "blank", text };
}
