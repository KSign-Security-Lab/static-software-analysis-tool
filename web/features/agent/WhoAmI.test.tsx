import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { OWNER_HEADER, WHOAMI_KEY, ownerHeaders, readOwner, writeOwner } from "@/lib/run/whoami";
import WhoAmI from "./WhoAmI";

/**
 * The typed name, and the one thing it must never be mistaken for.
 *
 * It labels runs so a shared server's history is legible. It is not a login,
 * and the tests below say so twice: an empty name is a legitimate answer, and
 * nothing about it is checked. What is worth pinning is the header spelling --
 * the API reads exactly `x-ssat-owner`, and a mismatch would silently make
 * every run anonymous rather than fail.
 */

afterEach(cleanup);
beforeEach(() => window.localStorage.clear());

function show() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <WhoAmI />
    </QueryClientProvider>,
  );
}

describe("the store", () => {
  it("sends the header the API reads, and nothing when there is no name", () => {
    expect(ownerHeaders()).toEqual({});
    writeOwner("keonoh");
    expect(ownerHeaders()).toEqual({ [OWNER_HEADER]: "keonoh" });
  });

  it("trims and bounds the name, because it lands in a column", () => {
    writeOwner("  keonoh  ");
    expect(readOwner()).toBe("keonoh");

    writeOwner("k".repeat(500));
    expect(readOwner()!.length).toBe(128);
  });

  it("treats an empty name as no name rather than as the empty string", () => {
    writeOwner("keonoh");
    writeOwner("   ");
    expect(readOwner()).toBeNull();
    expect(window.localStorage.getItem(WHOAMI_KEY)).toBeNull();
  });
});

describe("the dialog", () => {
  it("asks on a first visit, without being found", async () => {
    show();
    await waitFor(() => expect(screen.getByText("이름을 알려주세요")).toBeTruthy());
  });

  it("does not ask again once a name is known", async () => {
    writeOwner("keonoh");
    show();
    // The name is on the bar instead.
    await waitFor(() => expect(screen.getByRole("button", { name: /keonoh/ })).toBeTruthy());
    expect(screen.queryByText("이름을 알려주세요")).toBeNull();
  });

  it("keeps what was typed and closes", async () => {
    show();
    await waitFor(() => expect(screen.getByText("이름을 알려주세요")).toBeTruthy());

    await userEvent.type(screen.getByPlaceholderText("예: keonoh"), "keonoh");
    await userEvent.click(screen.getByRole("button", { name: "저장" }));

    expect(readOwner()).toBe("keonoh");
    await waitFor(() => expect(screen.queryByText("이름을 알려주세요")).toBeNull());
  });

  it("will not save an empty name", async () => {
    show();
    await waitFor(() => expect(screen.getByText("이름을 알려주세요")).toBeTruthy());
    expect(screen.getByRole("button", { name: "저장" }).hasAttribute("disabled")).toBe(true);
  });

  it("lets a reader stay anonymous, which is a state the API serves", async () => {
    show();
    await waitFor(() => expect(screen.getByText("이름을 알려주세요")).toBeTruthy());
    await userEvent.click(screen.getByRole("button", { name: "그만두기" }));

    await waitFor(() => expect(screen.queryByText("이름을 알려주세요")).toBeNull());
    expect(readOwner()).toBeNull();
    expect(screen.getByRole("button", { name: /이름 없음/ })).toBeTruthy();
  });

  it("can be reopened to change the name", async () => {
    writeOwner("keonoh");
    show();
    await userEvent.click(screen.getByRole("button", { name: /keonoh/ }));

    const field = screen.getByPlaceholderText("예: keonoh") as HTMLInputElement;
    expect(field.value).toBe("keonoh");

    await userEvent.clear(field);
    await userEvent.type(field, "somebody-else");
    await userEvent.click(screen.getByRole("button", { name: "저장" }));

    expect(readOwner()).toBe("somebody-else");
  });
});
