import type { ReactNode } from "react";

import Shell from "@/components/workbench/Shell";

/**
 * One shell for every surface.
 *
 * It used to be a server component so it could read a pane layout out of a cookie
 * before the first paint. There is no layout to read any more -- the regions are
 * fixed in CSS -- so this is a plain passthrough.
 */

/**
 * Rendered per request, as it always was.
 *
 * Reading the layout cookie used to opt these routes out of static rendering as a
 * side effect. Without it they became static, and `useSearchParams` -- which nuqs
 * calls at the root, for the `?run=` every surface is keyed by -- refuses to be
 * prerendered without a Suspense boundary above the adapter.
 *
 * Wrapping the whole app in one to satisfy that would buy an empty shell in the
 * static HTML and a client bail-out immediately after. There is nothing here worth
 * prerendering: it is a local tool that renders from a localhost API on the client.
 */
export const dynamic = "force-dynamic";
export default function WorkbenchLayout({
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
  return (
    <Shell side={side} dock={dock} inspector={inspector}>
      {children}
    </Shell>
  );
}
