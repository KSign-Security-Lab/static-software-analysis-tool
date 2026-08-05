"use client";

import { ThemeProvider } from "next-themes";
import type { ReactNode } from "react";

/**
 * Client providers, mounted once at the root.
 *
 * `attribute="data-theme"` keeps the contract the stylesheet has always used,
 * and `storageKey` matches what the old hand-rolled toggle wrote, so anyone
 * who had picked light keeps it across the rewrite.
 *
 * `enableSystem` is off deliberately: dark is a choice here, not a default to
 * be overridden by the OS. Turning it on later means `data-theme` can also be
 * "system", and the light block in theme.css would need a
 * `prefers-color-scheme` clause guarded to it.
 */
export default function Providers({ children }: { children: ReactNode }) {
  return (
    <ThemeProvider
      attribute="data-theme"
      defaultTheme="dark"
      enableSystem={false}
      disableTransitionOnChange
      storageKey="ssat-theme"
    >
      {children}
    </ThemeProvider>
  );
}
