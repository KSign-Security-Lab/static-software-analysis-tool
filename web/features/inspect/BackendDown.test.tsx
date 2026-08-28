import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import BackendDown from "./BackendDown";

/**
 * A dead backend has to look different from an empty one.
 *
 * Everything on this surface is the server's, so when it cannot be reached every
 * part of the page renders as an absence -- no scans, no findings, nothing to
 * patch -- and an absence is indistinguishable from an answer. 지난 검사 was
 * literally saying "아직 검사한 것이 없습니다" to somebody whose server was down.
 *
 * Driven through a stubbed `fetch` rather than a seeded cache, so the whole path
 * is under test: the failure, the `ApiError` the client wraps it in, the hook
 * that reads `offline`, and the strip.
 */

const original = globalThis.fetch;
afterEach(() => {
  globalThis.fetch = original;
  cleanup();
});

function answers(body: unknown, status = 200) {
  globalThis.fetch = vi.fn(() =>
    Promise.resolve({
      ok: status < 400,
      status,
      statusText: "",
      text: () => Promise.resolve(body === undefined ? "" : JSON.stringify(body)),
    } as Response),
  ) as unknown as typeof fetch;
}

function refuses(message = "Load failed") {
  globalThis.fetch = vi.fn(() => Promise.reject(new TypeError(message))) as unknown as typeof fetch;
}

function show() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <BackendDown />
    </QueryClientProvider>,
  );
}

describe("when the backend cannot be reached", () => {
  it("says so, with the address it tried", async () => {
    refuses();
    show();

    const alert = await waitFor(() => screen.getByRole("alert"));
    // The address matters: the API host is derived from the page's hostname, so
    // the usual cause is a URL that is right for the machine serving the page
    // and wrong for the one reading it.
    expect(alert.textContent).toContain(":8000");
    expect(alert.textContent).toContain("연결할 수 없습니다");
  });

  it("names the escape hatch, because the derived host is often the problem", async () => {
    refuses();
    show();
    const alert = await waitFor(() => screen.getByRole("alert"));
    expect(alert.textContent).toContain("NEXT_PUBLIC_API_URL");
  });

  it("offers a retry rather than making the reader reload", async () => {
    refuses();
    show();
    await waitFor(() => screen.getByRole("alert"));

    const before = (globalThis.fetch as unknown as ReturnType<typeof vi.fn>).mock.calls.length;
    await userEvent.click(screen.getByRole("button", { name: /다시 시도/ }));

    await waitFor(() =>
      expect((globalThis.fetch as unknown as ReturnType<typeof vi.fn>).mock.calls.length).toBeGreaterThan(before),
    );
  });
});

describe("when the backend is answering", () => {
  it("says nothing at all", async () => {
    answers({ runs: [] });
    show();
    // Give the query a chance to settle before asserting an absence.
    await waitFor(() => expect(globalThis.fetch).toHaveBeenCalled());
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("stays quiet for a failure that is not a connectivity failure", async () => {
    // A 404 for one run is not the server being gone, and a banner across the
    // top saying it is would send the reader after the wrong thing.
    answers({ detail: "unknown run: abc" }, 404);
    show();
    await waitFor(() => expect(globalThis.fetch).toHaveBeenCalled());
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("stays quiet for a malformed answer, which is a server bug and not a dead one", async () => {
    // An empty 200 makes `r.runs` throw a plain TypeError rather than an
    // `ApiError`, and the strip is deliberately only about reachability.
    answers(undefined);
    show();
    await waitFor(() => expect(globalThis.fetch).toHaveBeenCalled());
    expect(screen.queryByRole("alert")).toBeNull();
  });
});
