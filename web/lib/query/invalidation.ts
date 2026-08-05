import type { QueryClient, QueryKey } from "@tanstack/react-query";

/**
 * Collapse a burst of invalidations into one.
 *
 * A wave of four lens tasks lands four `checkpoint` events inside about a
 * hundred milliseconds, and each of them means "the recorded history moved".
 * Invalidating on every one is sixteen requests for a single super-step, all
 * but the last of them already superseded when they arrive.
 *
 * Trailing edge, not leading: the point is to read *after* the burst settles.
 * Extracted rather than left as a setTimeout inside the stream hook so the
 * window is testable without a browser.
 */
export class InvalidationQueue {
  private readonly pending = new Map<string, QueryKey>();
  private timer: ReturnType<typeof setTimeout> | null = null;

  constructor(
    private readonly client: Pick<QueryClient, "invalidateQueries">,
    private readonly windowMs = 250,
  ) {}

  add(...queryKeys: QueryKey[]): void {
    for (const key of queryKeys) this.pending.set(JSON.stringify(key), key);
    this.schedule();
  }

  private schedule(): void {
    if (this.timer) return;
    this.timer = setTimeout(() => {
      this.timer = null;
      this.flush();
    }, this.windowMs);
  }

  /** Invalidate everything queued now, cancelling the pending window. */
  flush(): void {
    if (this.timer) {
      clearTimeout(this.timer);
      this.timer = null;
    }
    const keys = [...this.pending.values()];
    this.pending.clear();
    for (const key of keys) void this.client.invalidateQueries({ queryKey: key });
  }

  /** Drop anything queued without invalidating; for unmount. */
  cancel(): void {
    if (this.timer) clearTimeout(this.timer);
    this.timer = null;
    this.pending.clear();
  }

  get size(): number {
    return this.pending.size;
  }
}
