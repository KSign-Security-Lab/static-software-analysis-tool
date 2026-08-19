"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { parseAsString, useQueryState } from "nuqs";

import { del, get, post } from "@/lib/api/client";
import type { DatasetList, DatasetView, SweepStatus } from "@/lib/bench/types";

/**
 * Reading the benchmark, and running it.
 *
 * The results are still read-only: nothing here edits an outcome, and the
 * score is whatever the sweep left on disk. What the start button does is
 * spawn the same script you would run in tmux, detached, so a two-day job does
 * not require a terminal.
 *
 * The original argument against a button was that a held-out benchmark you can
 * re-run at a click is one you will end up tuning against. What makes it safe
 * is the other half of that rule, which is enforced by a test: the agent's own
 * graph cannot import the benchmark at all, so re-running it never feeds back
 * into the thing being measured.
 */

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
  // While a sweep is writing, this list is a live view of it: results appear as
  // instances finish rather than when the run does.
  const sweep = useSweep();
  return useQuery({
    queryKey: keys.dataset(id ?? ""),
    queryFn: () => get<DatasetView>(`/bench/${id}`),
    enabled: Boolean(id),
    refetchInterval: sweep.data?.running ? 15_000 : false,
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

/**
 * The running sweep, polled.
 *
 * Fast while it is running because the log is the only sign of life, slow
 * otherwise because a stopped sweep will not start itself. `refetchInterval`
 * takes the previous result, so the rate follows the state without a effect.
 */
export function useSweep() {
  return useQuery({
    queryKey: keys.sweep(),
    queryFn: () => get<SweepStatus>("/bench/sweep"),
    refetchInterval: (query) => (query.state.data?.running ? 5_000 : 30_000),
    // It keeps running when the tab is in the background, which is where a
    // two-day job spends its life.
    refetchIntervalInBackground: true,
  });
}

export function useStartSweep() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => post<SweepStatus>("/bench/sweep"),
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
