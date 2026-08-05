import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { InvalidationQueue } from "./invalidation";

function spyClient() {
  const calls: unknown[][] = [];
  return {
    calls,
    invalidateQueries: (args: unknown) => {
      calls.push([args]);
      return Promise.resolve();
    },
  };
}

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

describe("InvalidationQueue", () => {
  it("waits for the window before invalidating", () => {
    const client = spyClient();
    new InvalidationQueue(client, 250).add(["a"]);

    expect(client.calls).toHaveLength(0);
    vi.advanceTimersByTime(249);
    expect(client.calls).toHaveLength(0);
    vi.advanceTimersByTime(1);
    expect(client.calls).toHaveLength(1);
  });

  it("collapses a burst into one invalidation per key", () => {
    // A wave of four lens tasks lands four checkpoints in about 100ms. Without
    // this, that is sixteen requests for a single super-step.
    const client = spyClient();
    const queue = new InvalidationQueue(client, 250);

    for (let i = 0; i < 4; i += 1) {
      queue.add(["spans"], ["threads"], ["checkpoints"], ["state"]);
      vi.advanceTimersByTime(25);
    }
    expect(client.calls).toHaveLength(0);

    vi.advanceTimersByTime(250);
    expect(client.calls).toHaveLength(4);
  });

  it("is a trailing edge, so it reads after the burst settles", () => {
    const client = spyClient();
    const queue = new InvalidationQueue(client, 100);

    queue.add(["a"]);
    vi.advanceTimersByTime(90);
    queue.add(["b"]);
    // The window is not extended by later additions; it fires 100ms after the
    // first, having accumulated both.
    vi.advanceTimersByTime(10);
    expect(client.calls).toHaveLength(2);
  });

  it("deduplicates identical keys", () => {
    const client = spyClient();
    const queue = new InvalidationQueue(client, 50);
    queue.add(["agent", "run", "r1"], ["agent", "run", "r1"]);
    expect(queue.size).toBe(1);
    vi.advanceTimersByTime(50);
    expect(client.calls).toHaveLength(1);
  });

  it("treats structurally different keys as different", () => {
    const client = spyClient();
    const queue = new InvalidationQueue(client, 50);
    queue.add(["run", { full: true }], ["run", { full: false }]);
    expect(queue.size).toBe(2);
  });

  it("flushes immediately when asked", () => {
    // run_finished does this: the report is on disk now and waiting a further
    // quarter second to read it is just latency.
    const client = spyClient();
    const queue = new InvalidationQueue(client, 250);
    queue.add(["a"]);
    queue.flush();
    expect(client.calls).toHaveLength(1);

    vi.advanceTimersByTime(500);
    expect(client.calls).toHaveLength(1);
  });

  it("does nothing on an empty flush", () => {
    const client = spyClient();
    new InvalidationQueue(client, 250).flush();
    expect(client.calls).toHaveLength(0);
  });

  it("drops everything on cancel, for unmount", () => {
    const client = spyClient();
    const queue = new InvalidationQueue(client, 250);
    queue.add(["a"]);
    queue.cancel();
    vi.advanceTimersByTime(500);
    expect(client.calls).toHaveLength(0);
    expect(queue.size).toBe(0);
  });

  it("can be reused after a flush", () => {
    const client = spyClient();
    const queue = new InvalidationQueue(client, 50);
    queue.add(["a"]);
    vi.advanceTimersByTime(50);
    queue.add(["b"]);
    vi.advanceTimersByTime(50);
    expect(client.calls).toHaveLength(2);
  });
});
