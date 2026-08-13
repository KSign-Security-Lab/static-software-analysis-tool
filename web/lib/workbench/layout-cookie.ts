import type { PerspectiveId } from "./perspectives";

/**
 * Pane sizes, in a cookie, read on the server.
 *
 * The old pane model read localStorage in an effect and accepted a flash. At
 * one splitter that was a shrug; at four panels it is the whole screen
 * rearranging after first paint. A cookie is the only client-owned storage the
 * server can see, so the layout can be rendered correctly into the first HTML
 * and the client's first render agrees with it exactly.
 *
 * Deliberately not the library's own persistence: it reads on the client at
 * mount, which reintroduces precisely the flash this exists to remove.
 *
 * The wire format is positional rather than JSON:
 *
 *     1~agent:20_58_22_70_30~f2a:15_57_28_46_54
 *     ^ version    ^ side_main_inspector_centre_dock
 *
 * A cookie rides on every request including every asset, and JSON spends most
 * of its bytes on punctuation that then has to be percent-encoded -- braces,
 * quotes and colons roughly quadruple. Worse, JSON separates with `,`, which
 * a cookie value may not contain, so it cannot even be stored raw. Five
 * numbers in a known order need neither escaping nor a parser.
 */

export const LAYOUT_COOKIE = "ssat.layout";
export const LAYOUT_VERSION = 1;
const MAX_AGE = 60 * 60 * 24 * 365;

/** Panel id -> percentage, the shape `react-resizable-panels` takes and returns. */
export type Sizes = Record<string, number>;

export interface PaneLayout {
  /** side | main | inspector */
  h: Sizes;
  /** centre | dock */
  v: Sizes;
}

export type StoredLayout = Partial<Record<PerspectiveId, PaneLayout>>;

export const HORIZONTAL_PANELS = ["side", "main", "inspector"] as const;
export const VERTICAL_PANELS = ["centre", "dock"] as const;

/** Written and read in this order. Changing it is a version bump. */
const ORDER = [...HORIZONTAL_PANELS, ...VERTICAL_PANELS] as const;

/** A collapsible panel sits at 0, so a restored 0 restores the collapse too. */
export const DEFAULT_LAYOUT: PaneLayout = {
  h: { side: 18, main: 60, inspector: 22 },
  v: { centre: 68, dock: 32 },
};

/** 검사 leads with the code, but the record under it wants real room too. */
const PER_PERSPECTIVE: Partial<Record<PerspectiveId, PaneLayout>> = {
  agent: { h: { side: 16, main: 60, inspector: 24 }, v: { centre: 58, dock: 42 } },
  // 스테이지 is a side list and one editor over its raw response: it has
  // neither a bottom panel nor an inspector, and was showing a staging
  // placeholder in each of them.
  stages: { h: { side: 16, main: 84, inspector: 0 }, v: { centre: 100, dock: 0 } },
  // 추출 has no bottom panel of its own: the graph and the node inspector are
  // the whole surface. Collapsed rather than filled with a placeholder, which
  // is what it showed before -- a "문제" tab reading 준비 중, on a screen that
  // does not look for problems.
  extract: { h: { side: 18, main: 60, inspector: 22 }, v: { centre: 100, dock: 0 } },
};

export function defaultLayoutFor(id: PerspectiveId): PaneLayout {
  return PER_PERSPECTIVE[id] ?? DEFAULT_LAYOUT;
}

const VALID_ID = new Set<string>(["agent", "f2a", "extract", "stages"]);

function sums(values: number[], from: number, to: number): boolean {
  let total = 0;
  for (let i = from; i < to; i += 1) total += values[i];
  // Percentages that do not add up are not a layout. A little slack for the
  // rounding a drag leaves behind.
  return Math.abs(total - 100) <= 1;
}

function parseEntry(segment: string): [PerspectiveId, PaneLayout] | null {
  const split = segment.indexOf(":");
  if (split < 1) return null;

  const id = segment.slice(0, split);
  if (!VALID_ID.has(id)) return null;

  const parts = segment.slice(split + 1).split("_");
  if (parts.length !== ORDER.length) return null;

  const values: number[] = [];
  for (const part of parts) {
    // Number("") is 0 and Number("1e5") is 100000; both would slip past a
    // bare isFinite check, so the shape is asserted before the value.
    if (!/^\d+(\.\d+)?$/.test(part)) return null;
    const value = Number(part);
    if (!Number.isFinite(value) || value > 100) return null;
    values.push(value);
  }

  if (!sums(values, 0, HORIZONTAL_PANELS.length) || !sums(values, HORIZONTAL_PANELS.length, ORDER.length)) return null;

  return [
    id as PerspectiveId,
    {
      h: { side: values[0], main: values[1], inspector: values[2] },
      v: { centre: values[3], dock: values[4] },
    },
  ];
}

export function decodeLayout(raw: string | undefined): StoredLayout {
  if (!raw) return {};
  const segments = raw.split("~");
  if (segments.shift() !== String(LAYOUT_VERSION)) return {};

  const out: StoredLayout = {};
  for (const segment of segments) {
    const entry = parseEntry(segment);
    if (entry) out[entry[0]] = entry[1];
  }
  return out;
}

/** One decimal place: the panels round anyway, and it halves the cookie. */
const trim = (n: number) => String(Math.round(n * 10) / 10);

export function encodeLayout(layout: StoredLayout): string {
  const parts = [String(LAYOUT_VERSION)];
  for (const [id, panes] of Object.entries(layout)) {
    if (!panes) continue;
    const sizes = [panes.h.side, panes.h.main, panes.h.inspector, panes.v.centre, panes.v.dock];
    if (sizes.some((n) => typeof n !== "number" || !Number.isFinite(n))) continue;
    parts.push(`${id}:${sizes.map(trim).join("_")}`);
  }
  return parts.join("~");
}

export function layoutFor(stored: StoredLayout, id: PerspectiveId): PaneLayout {
  return stored[id] ?? defaultLayoutFor(id);
}

/** `document.cookie` payload. Not httpOnly: the client is what writes it. */
export function cookieValue(layout: StoredLayout): string {
  return `${LAYOUT_COOKIE}=${encodeLayout(layout)}; Path=/; Max-Age=${MAX_AGE}; SameSite=Lax`;
}
