import { cookies, headers } from "next/headers";
import type { ReactNode } from "react";

import Workbench from "@/components/workbench/Workbench";
import { LAYOUT_COOKIE, decodeLayout, layoutFor } from "@/lib/workbench/layout-cookie";
import { perspectiveFor } from "@/lib/workbench/perspectives";
import { WorkbenchStoreProvider } from "@/lib/workbench/store-provider";

export default async function WorkbenchLayout({
  children,
  side,
  dock,
  inspector,
}: {
  children: ReactNode;
  side: ReactNode;
  dock: ReactNode;
  inspector: ReactNode;
}) {
  const [cookieStore, headerStore] = await Promise.all([cookies(), headers()]);
  const stored = decodeLayout(cookieStore.get(LAYOUT_COOKIE)?.value);
  const perspective = perspectiveFor(headerStore.get("x-pathname") ?? "")?.id ?? "f2a";

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
      >
        {children}
      </Workbench>
    </WorkbenchStoreProvider>
  );
}
