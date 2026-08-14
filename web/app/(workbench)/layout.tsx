import { cookies, headers } from "next/headers";
import type { ReactNode } from "react";

import Workbench from "@/components/workbench/Workbench";
import { LAYOUT_COOKIE, decodeLayout, layoutFor } from "@/lib/workbench/layout-cookie";
import { perspectiveFor } from "@/lib/workbench/perspectives";
import { WorkbenchStoreProvider } from "@/lib/workbench/store-provider";

/**
 * One shell for every surface.
 *
 * A server component on purpose: it reads the pane sizes out of a cookie and hands
 * them down as props, so the server's HTML and the client's first render agree and
 * nothing rearranges after paint.
 *
 * Reading cookies opts this route out of static rendering. That is the whole cost
 * and it buys the thing above; the app is client-driven against a localhost backend
 * and has nothing worth prerendering. Do not "optimise" it.
 */
export default async function WorkbenchLayout({
  children,
  side,
  dock,
  inspector,
  status,
}: {
  children: ReactNode;
  side: ReactNode;
  dock: ReactNode;
  inspector: ReactNode;
  /** A strip under the title bar, for surfaces with run-wide state to report. */
  status: ReactNode;
}) {
  const [cookieStore, headerStore] = await Promise.all([cookies(), headers()]);
  const stored = decodeLayout(cookieStore.get(LAYOUT_COOKIE)?.value);
  const perspective = perspectiveFor(headerStore.get("x-pathname") ?? "")?.id ?? "agent";

  // Seed the fold mirror from the same layout the panels are sized with. It used
  // to be read off the panel handles as they attached, which threw during commit
  // and took the whole client tree down; the cookie already says it, on the
  // server, before anything renders.
  const layout = layoutFor(stored, perspective);
  const collapsed = {
    side: layout.h.side === 0,
    inspector: layout.h.inspector === 0,
    dock: layout.v.dock === 0,
  };

  return (
    <WorkbenchStoreProvider init={{ collapsed }}>
      <Workbench
        perspective={perspective}
        stored={stored}
        side={side}
        dock={dock}
        inspector={inspector}
        status={status}
      >
        {children}
      </Workbench>
    </WorkbenchStoreProvider>
  );
}
