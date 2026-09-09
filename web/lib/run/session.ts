export const RUN_KEY = "ssat.run";

export function readSessionRun(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.sessionStorage.getItem(RUN_KEY);
  } catch {
    return null;
  }
}

export function writeSessionRun(runId: string | null): void {
  if (typeof window === "undefined") return;
  try {
    if (runId) window.sessionStorage.setItem(RUN_KEY, runId);
    else window.sessionStorage.removeItem(RUN_KEY);
  } catch {
  }
}

let restoredHere = false;

export function markRestored(): void {
  restoredHere = true;
}

export function clearRestored(): void {
  restoredHere = false;
}

export function wasRestored(): boolean {
  return restoredHere;
}
