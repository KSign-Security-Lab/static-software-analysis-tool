"use client";

import { useQueryClient } from "@tanstack/react-query";

import { ApiError, apiBase } from "@/lib/api/client";
import { keys } from "@/lib/query/keys";
import { useRuns } from "@/lib/run/queries";

/**
 * Whether the backend is answering at all, and how to ask again.
 *
 * `ApiError.offline` -- status 0, meaning no response rather than a response
 * that said no -- has existed since the client was written and nothing read it.
 * So a dead backend reached the screen as an absence: 지난 검사 said "아직 검사한
 * 것이 없습니다", which is a statement about the reader's history and was instead
 * a statement about the network. Every other surface said nothing at all.
 *
 * Driven off the runs query rather than a probe of its own. It is the one request
 * this surface makes unconditionally, on every stage, so it is already the
 * canary -- and adding a health poll to find out what a failing request has
 * already told us would be a second source of truth about the same fact.
 */
export interface Backend {
  down: boolean;
  /** The client's own sentence, which names the URL it tried. */
  message: string;
  base: string;
  retry: () => void;
}

export function useBackend(): Backend {
  const runs = useRuns();
  const client = useQueryClient();
  const error = runs.error;
  const down = error instanceof ApiError && error.offline;

  return {
    down,
    message: down && error instanceof ApiError ? error.message : "",
    base: apiBase(),
    // Everything, not just the runs list: if the server was down then every
    // query against it failed, and retrying one of them would leave the rest
    // showing an empty state that is still a lie.
    retry: () => void client.invalidateQueries({ queryKey: keys.agent }),
  };
}
