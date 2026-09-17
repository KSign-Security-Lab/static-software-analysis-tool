import { QueryClient } from "@tanstack/react-query";

import { ApiError } from "@/lib/api/client";

export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: Infinity,

        refetchOnWindowFocus: false,
        refetchOnReconnect: false,

        retry: (attempt, error) => {
          if (error instanceof ApiError && error.status >= 400 && error.status < 500) return false;
          return attempt < 2;
        },
      },
    },
  });
}
