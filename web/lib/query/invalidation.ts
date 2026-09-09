import type { QueryClient, QueryKey } from "@tanstack/react-query";

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

  flush(): void {
    if (this.timer) {
      clearTimeout(this.timer);
      this.timer = null;
    }
    const keys = [...this.pending.values()];
    this.pending.clear();
    for (const key of keys) void this.client.invalidateQueries({ queryKey: key });
  }

  cancel(): void {
    if (this.timer) clearTimeout(this.timer);
    this.timer = null;
    this.pending.clear();
  }

  get size(): number {
    return this.pending.size;
  }
}
