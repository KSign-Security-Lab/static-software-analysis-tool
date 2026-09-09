"use client";

import { QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "next-themes";
import { NuqsAdapter } from "nuqs/adapters/next/app";
import { useState, type ReactNode } from "react";

import { installClipboardFallback } from "@/components/editor/clipboard-fallback";
import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { createQueryClient } from "@/lib/query/client";

installClipboardFallback();

export default function Providers({ children }: { children: ReactNode }) {
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
          <TooltipProvider delayDuration={400} skipDelayDuration={200}>
            {children}
            <Toaster position="bottom-right" closeButton richColors />
          </TooltipProvider>
        </NuqsAdapter>
      </QueryClientProvider>
    </ThemeProvider>
  );
}
