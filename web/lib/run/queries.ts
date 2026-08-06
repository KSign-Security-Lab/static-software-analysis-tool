"use client";

import { useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { describeError } from "@/lib/api/client";
import { startRun, type StartOptions } from "@/lib/api/control";
import {
  createEmptyRun,
  deleteFile,
  fetchFile,
  fetchFiles,
  fetchFindings,
  fetchRun,
  health,
  uploadSource,
  writeFile,
} from "@/lib/api/runs";
import type { FileWriteResult, Report } from "@/lib/api/types";
import { keys } from "@/lib/query/keys";

/**
 * The queries and mutations the inspect surface runs on.
 *
 * Every mutation that changes the tree returns the new file list, so the cache
 * is written from the response rather than invalidated and re-read -- one
 * round trip instead of two, and no window where the explorer disagrees with
 * the editor.
 */

const enabled = (runId: string | null): runId is string => Boolean(runId);

export function useAgentHealth() {
  return useQuery({
    queryKey: keys.health(false),
    queryFn: ({ signal }) => health(false, { signal }),
    staleTime: 60_000,
  });
}

export function useRun(runId: string | null) {
  return useQuery({
    queryKey: keys.summary(runId ?? ""),
    queryFn: ({ signal }) => fetchRun(runId!, { signal }),
    enabled: enabled(runId),
  });
}

export function useFiles(runId: string | null) {
  return useQuery({
    queryKey: keys.files(runId ?? ""),
    queryFn: ({ signal }) => fetchFiles(runId!, { signal }).then((r) => r.files),
    enabled: enabled(runId),
  });
}

export function useFile(runId: string | null, path: string | null) {
  return useQuery({
    queryKey: keys.file(runId ?? "", path ?? ""),
    queryFn: ({ signal }) => fetchFile(runId!, path!, { signal }),
    enabled: enabled(runId) && Boolean(path),
  });
}

export function useFindings(runId: string | null) {
  return useQuery({
    queryKey: keys.findings(runId ?? ""),
    queryFn: ({ signal }) => fetchFindings(runId!, { signal }),
    enabled: enabled(runId),
  });
}

/** Both file mutations return the tree; write it straight in. */
function applyTree(client: QueryClient, runId: string, result: FileWriteResult) {
  client.setQueryData(keys.files(runId), result.files);
  client.setQueryData(keys.summary(runId), (previous: unknown) =>
    previous ? { ...previous, index: result.index, file_count: result.files.length } : previous,
  );
}

export function useCreateRun() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: createEmptyRun,
    onSuccess: (result) => {
      client.setQueryData(keys.files(result.run_id), result.files);
      void client.invalidateQueries({ queryKey: keys.runs() });
    },
    onError: (error) => toast.error("실행을 만들 수 없습니다", { description: describeError(error) }),
  });
}

export function useUpload() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (files: File[]) => uploadSource(files),
    onSuccess: (result) => {
      client.setQueryData(keys.files(result.run_id), result.files);
      void client.invalidateQueries({ queryKey: keys.runs() });
    },
    onError: (error) => toast.error("업로드 실패", { description: describeError(error) }),
  });
}

/**
 * Write one file.
 *
 * The run id may be passed per call, and has to be: creating a run and writing
 * the first file into it happens in one handler, and the hook was bound to the
 * run id from the render that is still executing -- which is `null`, because
 * the run did not exist when it started. That sent the first file of every
 * fresh session to `/agent/runs/null/file`, and the caller's `.catch` swallowed
 * the 404, so what you saw was an empty editor and no reason for it.
 */
export function useWriteFile(runId: string | null) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ path, content, runId: override }: { path: string; content: string; runId?: string }) =>
      writeFile(override ?? runId!, path, content),
    onSuccess: (result, { content, runId: override }) => {
      const id = override ?? runId!;
      applyTree(client, id, result);
      // The editor already holds this text; re-fetching it would be a round
      // trip to be told what we just sent.
      client.setQueryData(keys.file(id, result.path), (previous: unknown) =>
        previous ? { ...(previous as object), content } : previous,
      );
    },
    onError: (error) => toast.error("저장 실패", { description: describeError(error) }),
  });
}

export function useDeleteFile(runId: string | null) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (path: string) => deleteFile(runId!, path),
    onSuccess: (result) => {
      applyTree(client, runId!, result);
      client.removeQueries({ queryKey: keys.file(runId!, result.deleted) });
      // Its findings referenced a file that no longer exists.
      client.setQueryData<Report | undefined>(keys.findings(runId!), (previous) =>
        previous
          ? { ...previous, findings: (previous.findings ?? []).filter((f) => f.primary.file !== result.deleted) }
          : previous,
      );
    },
    onError: (error) => toast.error("삭제 실패", { description: describeError(error) }),
  });
}

/**
 * Start an inspection.
 *
 * Two things this has to get right, both of them non-obvious:
 *
 *  - attach the event stream *first*. The server ends the stream when a run
 *    finishes, so a second run would otherwise execute with nobody listening.
 *  - a 200 means accepted, not succeeded. The optimistic status below is what
 *    makes the button respond; the truth arrives on the stream, and the
 *    watchdog covers the case where the worker died before we heard anything.
 */
export function useStartRun(runId: string | null, ensureAttached: () => Promise<void>) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (options: StartOptions) => {
      await ensureAttached();
      return startRun(runId!, options);
    },
    onSuccess: () => {
      client.setQueryData(keys.summary(runId!), (previous: unknown) =>
        previous ? { ...previous, status: "inspecting", error: undefined } : previous,
      );
      window.setTimeout(() => {
        void client.invalidateQueries({ queryKey: keys.summary(runId!) });
      }, 5000);
    },
    onError: (error) => toast.error("검사를 시작할 수 없습니다", { description: describeError(error) }),
  });
}
