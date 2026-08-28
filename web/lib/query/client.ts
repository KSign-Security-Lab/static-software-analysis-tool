import { QueryClient } from "@tanstack/react-query";

import { ApiError } from "@/lib/api/client";

/**
 * One QueryClient per browser tab, created in the provider.
 *
 * The defaults here are deliberately unusual, because most of this data is
 * pushed rather than polled.
 */
export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        /**
         * Nothing goes stale on a timer.
         *
         * Spans, threads, checkpoints and findings all change exactly when the
         * run emits an event, and the stream tells us when that is. A time-based
         * staleTime is wrong in both directions: too eager for a finished run
         * that will never change again, hopelessly lazy for a live one.
         */
        staleTime: Infinity,

        /**
         * Refocusing a tab must not re-read a 500-row span table and yank the
         * reader's scroll position out from under them.
         */
        refetchOnWindowFocus: false,
        refetchOnReconnect: false,

        /**
         * Retrying a 4xx just asks the same wrong question again. A 404 from
         * the knowledge graph means "never indexed", which is an answer.
         */
        retry: (attempt, error) => {
          if (error instanceof ApiError && error.status >= 400 && error.status < 500) return false;
          return attempt < 2;
        },
      },
    },
  });
}
