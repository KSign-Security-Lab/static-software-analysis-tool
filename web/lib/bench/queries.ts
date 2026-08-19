"use client";

import { useQuery } from "@tanstack/react-query";
import { parseAsString, useQueryState } from "nuqs";

import { get } from "@/lib/api/client";
import type { DatasetList, DatasetView } from "@/lib/bench/types";

/**
 * Reading the benchmark. Reads only -- there is no mutation here on purpose.
 *
 * The sweep runs offline and this shows what it recorded. A start button would
 * put iterating against a held-out benchmark one click away, and the moment we
 * tune against it, it stops measuring us.
 */

const keys = {
  all: ["bench"] as const,
  datasets: () => ["bench", "datasets"] as const,
  dataset: (id: string) => ["bench", "dataset", id] as const,
};

export function useDatasets() {
  return useQuery({
    queryKey: keys.datasets(),
    queryFn: () => get<DatasetList>("/bench/datasets"),
    staleTime: 5 * 60_000,
  });
}

export function useDataset(id: string | null) {
  return useQuery({
    queryKey: keys.dataset(id ?? ""),
    queryFn: () => get<DatasetView>(`/bench/${id}`),
    enabled: Boolean(id),
  });
}

/**
 * Which dataset and instance the surface is looking at.
 *
 * In the URL for the reason 검사's selection is: a failing instance is worth
 * being able to send someone. `replace`, so clicking down a list of a hundred
 * does not fill the back stack with a hundred entries.
 */
export function useDatasetId() {
  return useQueryState("dataset", parseAsString.withDefault("corpus").withOptions({ history: "replace" }));
}

export function useInstanceId() {
  return useQueryState("instance", parseAsString.withOptions({ history: "replace" }));
}
