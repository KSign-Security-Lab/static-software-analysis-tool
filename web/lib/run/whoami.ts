export const WHOAMI_KEY = "ssat.owner";

export const OWNER_HEADER = "x-ssat-owner";

export const MAX_NAME = 128;

export function normalise(raw: string): string {
  return raw.trim().slice(0, MAX_NAME);
}

export function readOwner(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(WHOAMI_KEY) || null;
  } catch {
    return null;
  }
}

export function writeOwner(name: string | null): void {
  if (typeof window === "undefined") return;
  try {
    const value = name ? normalise(name) : "";
    if (value) window.localStorage.setItem(WHOAMI_KEY, value);
    else window.localStorage.removeItem(WHOAMI_KEY);
  } catch {
  }
  notify();
}

type Listener = () => void;
const listeners = new Set<Listener>();

function notify(): void {
  for (const listener of listeners) listener();
}

export function subscribe(listener: Listener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function ownerHeaders(): Record<string, string> {
  const name = readOwner();
  return name ? { [OWNER_HEADER]: name } : {};
}
