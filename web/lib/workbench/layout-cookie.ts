import { PERSPECTIVES, type PerspectiveId } from "./perspectives";

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
/**
 * 7: the structure moved to the right column.
 *
 * So the right pane holds two things and wants width -- a vertical pipeline is as
 * wide as its widest rank, which is the five specialists side by side -- and the
 * bottom panel is a list again and wants less height.
 *
 * 6: the editor gets its share back.
 *
 * 5 gave the panel 55% so the structure could be large, and the result was three
 * regions stacked in one column with none of them big enough: eight lines of code
 * over a squeezed drawing over a squeezed list. Three things that all want height
 * cannot all have it, so the default favours the code -- which is what the other
 * two are about -- and the handle is how you borrow from it.
 *
 * `StepGraph` refits whenever its pane resizes, so that drag actually works; it
 * did nothing at all before this round, when `fitView` only ran on mount.
 *
 * 5: the bottom panel holds the agent's structure above its record.
 *
 * 4: the bottom panel holds the call record and the pipeline too.
 *
 * A stored layout is five numbers in a fixed order, so it cannot say which pane a
 * number belongs to, nor that a pane now holds five times as much. A v3 cookie
 * dragged small -- when the dock was a findings list -- would leave the record and
 * the graph in a sliver, and a v2 one zeroed the dock and the inspector outright.
 * The version is the only thing that can refuse them, and dropping everyone's
 * dragged sizes is the cost of having moved what the panes contain.
 */
/**
 * Bumped to 8 when 검사 lost its dock.
 *
 * The wire format is positional and cannot describe a pane that is no longer
 * there, so a stored 7 would restore the dock at 35% -- a third of the editor
 * given to a panel with nothing in it. Everyone's pane sizes reset once; there
 * is no version of this that resets only the surface that changed.
 */
export const LAYOUT_VERSION = 8;
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

/** Where a surface differs from the four-pane default. */
const PER_PERSPECTIVE: Partial<Record<PerspectiveId, PaneLayout>> = {
  // Four regions, one job each: files left, code in the centre, the bottom panel
  // holding the run as one list, and a right column holding the agent's structure
  // above 상세 -- which shows whatever is picked anywhere else.
  //
  // The dock's share is larger than a problems list alone would need, because it
  // also holds the call record and the pipeline drawing -- everything that used
  // to be a full-window overlay over the top of the editor. It is draggable from
  // here; the point is that the editor is still there when you drag it.
  // No dock, and the side column is wider than it was: it lists the findings
  // now as well as the files, and a finding's title needs more than 15%.
  agent: { h: { side: 20, main: 55, inspector: 25 }, v: { centre: 100, dock: 0 } },
  // 스테이지 is a side list and one editor over its raw response: it has
  // neither a bottom panel nor an inspector, and was showing a staging
  // placeholder in each of them.
  stages: { h: { side: 16, main: 84, inspector: 0 }, v: { centre: 100, dock: 0 } },
  // 추출 has no bottom panel of its own: the graph and the node inspector are
  // the whole surface. Collapsed rather than filled with a placeholder, which
  // is what it showed before -- a "문제" tab reading 준비 중, on a screen that
  // does not look for problems.
  extract: { h: { side: 18, main: 60, inspector: 22 }, v: { centre: 100, dock: 0 } },
  // Same shape as 검사, and for the same reason: a list on the left whose rows
  // are prose -- an instance id and why it broke -- above nothing, beside a
  // detail column. No dock; there is no second list to put in one.
  bench: { h: { side: 24, main: 51, inspector: 25 }, v: { centre: 100, dock: 0 } },
};

export function defaultLayoutFor(id: PerspectiveId): PaneLayout {
  return PER_PERSPECTIVE[id] ?? DEFAULT_LAYOUT;
}

// Derived, not listed. This was a hand-written copy of the four ids, which is
// the second place that had to know the set -- and `perspectives.ts` says in
// its own docstring that a route added in one place and forgotten in another is
// the failure this design is trying to avoid. A fifth surface found it: a
// layout for `bench` would have been silently discarded on read, and the pane
// sizes would have reset on every load with nothing to say why.
const VALID_ID = new Set<string>(PERSPECTIVES.map((p) => p.id));

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
