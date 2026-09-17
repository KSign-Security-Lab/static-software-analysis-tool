"use client";

import { useQueryClient } from "@tanstack/react-query";

import { ApiError, apiBase } from "@/lib/api/client";
import { keys } from "@/lib/query/keys";
import { useRuns } from "@/lib/run/queries";

export interface Backend {
  down: boolean;
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
    retry: () => void client.invalidateQueries({ queryKey: keys.agent }),
  };
}
