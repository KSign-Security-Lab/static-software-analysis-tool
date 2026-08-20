import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, DEFAULT_TIMEOUT_MS, get, post } from "./client";

/**
 * A backend that is gone, and a backend that is merely quiet.
 *
 * The second is the one that had no error at all. A socket that is open while
 * nothing serves it -- uvicorn's reloader parent outliving its worker is the
 * everyday way to get there -- accepts the connection and never answers, so the
 * fetch neither resolved nor rejected. Every query sat pending, the screen showed
 * skeletons for ever, and nothing said the server was unreachable.
 *
 * Real timers and small deadlines. `AbortSignal.timeout` does not step with
 * vitest's fake clock, and a test that has to advance thirty seconds of fake time
 * to assert a constant is testing the constant rather than the behaviour.
 */

const original = globalThis.fetch;
afterEach(() => {
  globalThis.fetch = original;
});

/** A fetch that respects the signal it is handed and otherwise never settles. */
function hangs(): ReturnType<typeof vi.fn> {
  const spy = vi.fn(
    (_url: unknown, init?: RequestInit) =>
      new Promise((_resolve, reject) => {
        init?.signal?.addEventListener("abort", () => reject(init.signal!.reason));
      }) as Promise<Response>,
  );
  globalThis.fetch = spy as unknown as typeof fetch;
  return spy;
}

const settles = (promise: Promise<unknown>) => {
  let done = false;
  void promise.then(
    () => (done = true),
    () => (done = true),
  );
  return () => done;
};

const tick = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

describe("a backend that never answers", () => {
  it("becomes an offline error rather than a promise that never settles", async () => {
    hangs();
    const error = (await get("/agent/runs", { timeoutMs: 30 }).catch((err: unknown) => err)) as ApiError;

    expect(error).toBeInstanceOf(ApiError);
    expect(error.offline).toBe(true);
    expect(error.message).toContain("응답하지 않습니다");
  });

  it("attaches a deadline even when the caller asks for nothing", async () => {
    // The default is the whole point: no call site had to remember anything for
    // the hang to stop being silent.
    const spy = hangs();
    void get("/agent/runs").catch(() => undefined);
    await tick(0);

    const signal = (spy.mock.calls[0][1] as RequestInit).signal;
    expect(signal).toBeInstanceOf(AbortSignal);
    expect(DEFAULT_TIMEOUT_MS).toBeGreaterThan(1_000);
  });

  it("says something different from a refused connection", async () => {
    // Both are "check the server", but one has an address in it and the other a
    // reason, and conflating them costs the reader the difference.
    globalThis.fetch = vi.fn(() => Promise.reject(new TypeError("Load failed"))) as unknown as typeof fetch;

    const error = (await get("/agent/runs").catch((err: unknown) => err)) as ApiError;
    expect(error.offline).toBe(true);
    expect(error.message).toContain("연결할 수 없습니다");
    expect(error.message).toContain("Load failed");
  });

  it("waits longer when the caller says the call is honestly slow", async () => {
    hangs();
    const pending = post("/agent/runs/git", {}, { timeoutMs: 400 });
    const done = settles(pending);

    await tick(80);
    // A clone that takes a while must not be cancelled by the deadline that
    // exists to catch a dead server.
    expect(done()).toBe(false);

    await tick(500);
    expect(((await pending.catch((err: unknown) => err)) as ApiError).offline).toBe(true);
  });

  it("waits for ever when asked to", async () => {
    hangs();
    const done = settles(get("/agent/runs", { timeoutMs: null }).catch(() => undefined));
    await tick(120);
    expect(done()).toBe(false);
  });
});

describe("a cancellation is not a failure", () => {
  it("rethrows the caller's own abort untouched", async () => {
    // React Query cancels superseded queries, and wrapping that as an offline
    // error would make an ordinary navigation look like a dead backend.
    hangs();
    const controller = new AbortController();
    const pending = get("/agent/runs", { signal: controller.signal, timeoutMs: 5_000 });
    controller.abort();

    const error = await pending.catch((err: unknown) => err);
    expect(error).not.toBeInstanceOf(ApiError);
    expect((error as DOMException).name).toBe("AbortError");
  });
});
