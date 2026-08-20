import type { ReactNode } from "react";

import InspectShell from "@/features/inspect/InspectShell";

/**
 * 검사's own shell.
 *
 * A separate route group from `(workbench)` rather than a branch inside it,
 * because the two shells share nothing but the rail: no parallel slots, no
 * panel group, no layout cookie. Trying to express both in one layout is what
 * produced a surface whose own perspective entry had to say `chrome: false` and
 * `panes: []` to opt out of most of what the shell did.
 */
export default function InspectLayout({ children }: { children: ReactNode }) {
  return <InspectShell>{children}</InspectShell>;
}

/**
 * Never prerendered, and not for want of trying.
 *
 * Everything on this surface hangs off `?run=`, which is `useSearchParams` under
 * nuqs -- so prerendering bails out to the client at the first component that
 * reads it, which is the shell itself. The documented alternative is a `Suspense`
 * boundary, and it buys nothing here: there is no component *above* the one that
 * reads the run, so the boundary would prerender a fallback and then replace the
 * whole page with it.
 *
 * `(workbench)` reaches the same state by reading a cookie, and says the same
 * thing in its own docstring: the app is client-driven against a localhost
 * backend and has nothing worth prerendering. Declaring it is more honest than
 * arriving at it as a side effect. Do not "optimise" this.
 */
export const dynamic = "force-dynamic";
