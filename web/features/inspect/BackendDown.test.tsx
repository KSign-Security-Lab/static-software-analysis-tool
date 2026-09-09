import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import BackendDown from "./BackendDown";

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
    expect(alert.textContent).toContain(":8001");
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
    await waitFor(() => expect(globalThis.fetch).toHaveBeenCalled());
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("stays quiet for a failure that is not a connectivity failure", async () => {
    answers({ detail: "unknown run: abc" }, 404);
    show();
    await waitFor(() => expect(globalThis.fetch).toHaveBeenCalled());
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("stays quiet for a malformed answer, which is a server bug and not a dead one", async () => {
    answers(undefined);
    show();
    await waitFor(() => expect(globalThis.fetch).toHaveBeenCalled());
    expect(screen.queryByRole("alert")).toBeNull();
  });
});
