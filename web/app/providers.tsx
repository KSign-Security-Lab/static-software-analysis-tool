"use client";

import { QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "next-themes";
import { NuqsAdapter } from "nuqs/adapters/next/app";
import { useState, type ReactNode } from "react";

import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { CommandProvider } from "@/lib/commands/provider";
import { createQueryClient } from "@/lib/query/client";

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
  // Lazily, and per tab: a module-level QueryClient is shared across requests
  // on the Node server, which would leak one user's cache into another's HTML.
  const [queryClient] = useState(createQueryClient);

  return (
    <ThemeProvider
      attribute="data-theme"
      defaultTheme="dark"
      enableSystem={false}
      disableTransitionOnChange
      storageKey="ssat-theme"
    >
      <QueryClientProvider client={queryClient}>
        <NuqsAdapter>
          <CommandProvider>
            {/* One provider for the whole app: Radix tooltips share a delay
                timer through it, so moving between adjacent activity-bar items
                shows the next tooltip immediately rather than waiting out the
                delay again. */}
            <TooltipProvider delayDuration={400} skipDelayDuration={200}>
              {children}
              <Toaster position="bottom-right" closeButton richColors />
            </TooltipProvider>
          </CommandProvider>
        </NuqsAdapter>
      </QueryClientProvider>
    </ThemeProvider>
  );
}
