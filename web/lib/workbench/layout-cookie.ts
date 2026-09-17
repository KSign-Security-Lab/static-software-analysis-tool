import { PERSPECTIVES, type PerspectiveId } from "./perspectives";

export const LAYOUT_COOKIE = "ssat.layout";
export const LAYOUT_VERSION = 8;
const MAX_AGE = 60 * 60 * 24 * 365;

export type Sizes = Record<string, number>;

export interface PaneLayout {
  h: Sizes;
  v: Sizes;
}

export type StoredLayout = Partial<Record<PerspectiveId, PaneLayout>>;

export const HORIZONTAL_PANELS = ["side", "main", "inspector"] as const;
export const VERTICAL_PANELS = ["centre", "dock"] as const;

const ORDER = [...HORIZONTAL_PANELS, ...VERTICAL_PANELS] as const;

export const DEFAULT_LAYOUT: PaneLayout = {
  h: { side: 18, main: 60, inspector: 22 },
  v: { centre: 68, dock: 32 },
};

const PER_PERSPECTIVE: Partial<Record<PerspectiveId, PaneLayout>> = {
  stages: { h: { side: 16, main: 84, inspector: 0 }, v: { centre: 100, dock: 0 } },
  extract: { h: { side: 18, main: 60, inspector: 22 }, v: { centre: 100, dock: 0 } },
  bench: { h: { side: 24, main: 51, inspector: 25 }, v: { centre: 100, dock: 0 } },
};

export function defaultLayoutFor(id: PerspectiveId): PaneLayout {
  return PER_PERSPECTIVE[id] ?? DEFAULT_LAYOUT;
}

const VALID_ID = new Set<string>(PERSPECTIVES.map((p) => p.id));

function sums(values: number[], from: number, to: number): boolean {
  let total = 0;
  for (let i = from; i < to; i += 1) total += values[i];
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

export function cookieValue(layout: StoredLayout): string {
  return `${LAYOUT_COOKIE}=${encodeLayout(layout)}; Path=/; Max-Age=${MAX_AGE}; SameSite=Lax`;
}
