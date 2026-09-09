"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { parseAsString, useQueryState } from "nuqs";

import { del, get, post } from "@/lib/api/client";
import type { DatasetList, DatasetView, SweepOrder, SweepStatus } from "@/lib/bench/types";

const keys = {
  all: ["bench"] as const,
  datasets: () => ["bench", "datasets"] as const,
  dataset: (id: string) => ["bench", "dataset", id] as const,
  sweep: () => ["bench", "sweep"] as const,
};

export function useDatasets() {
  return useQuery({
    queryKey: keys.datasets(),
    queryFn: () => get<DatasetList>("/bench/datasets"),
    staleTime: 5 * 60_000,
  });
}

export function useDataset(id: string | null) {
  const sweep = useSweep();
  return useQuery({
    queryKey: keys.dataset(id ?? ""),
    queryFn: () => get<DatasetView>(`/bench/${id}`),
    enabled: Boolean(id),
    refetchInterval: sweep.data?.running ? 15_000 : false,
  });
}

export function useDatasetId() {
  return useQueryState("dataset", parseAsString.withDefault("corpus").withOptions({ history: "replace" }));
}

export function useInstanceId() {
  return useQueryState("instance", parseAsString.withOptions({ history: "replace" }));
}

export function useSweep() {
  return useQuery({
    queryKey: keys.sweep(),
    queryFn: () => get<SweepStatus>("/bench/sweep"),
    refetchInterval: (query) => (query.state.data?.running ? 5_000 : 30_000),
    refetchIntervalInBackground: true,
  });
}

export function useStartSweep() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (order: SweepOrder) => post<SweepStatus>("/bench/sweep", order),
    onSuccess: (status) => {
      client.setQueryData(keys.sweep(), status);
      client.invalidateQueries({ queryKey: keys.all });
    },
  });
}

export function useStopSweep() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => del<SweepStatus>("/bench/sweep"),
    onSuccess: (status) => {
      client.setQueryData(keys.sweep(), status);
      client.invalidateQueries({ queryKey: keys.all });
    },
  });
}
