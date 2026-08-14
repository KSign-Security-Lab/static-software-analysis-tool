"use client";

import { useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";
import { useMemo } from "react";
import { toast } from "sonner";

import { describeError } from "@/lib/api/client";
import { startRun, type StartOptions } from "@/lib/api/control";
import {
  applyFix,
  proposeFix,
  createEmptyRun,
  deleteFile,
  deleteRun,
  diffRuns,
  fetchFile,
  fetchFiles,
  fetchFindings,
  fetchRun,
  health,
  listRuns,
  uploadSource,
  writeFile,
} from "@/lib/api/runs";
import type { FileWriteResult, Report } from "@/lib/api/types";
import { fromAgent, type UiFinding } from "@/lib/model/finding";
import { keys } from "@/lib/query/keys";
import { useSelectedFinding } from "@/lib/run/selection";

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

/**
 * The finding `?finding=` names, as the view model.
 *
 * Four components resolved this by hand -- the editor to mark it, the detail to
 * render it, the transcript to scope to it, the list to open its row -- and each
 * had to remember that the id in the address bar is the *view model's*, which
 * `fromAgent` prefixes with the engine. Matching against the wire id matches
 * nothing, silently, and that is exactly how it read the one time it was got
 * wrong.
 *
 * The query is shared, so this costs nothing beyond the lookup.
 */
export function useOpenFinding(runId: string | null): UiFinding | undefined {
  const [findingId] = useSelectedFinding();
  const findings = useFindings(runId);
  return useMemo(() => {
    if (!findingId) return undefined;
    const all = fromAgent(findings.data?.findings);
    // Or under an id one of its merged copies had: duplicate claims collapse
    // into one row, and a link made before that still names a real finding.
    return all.find((each) => each.id === findingId) ?? all.find((each) => each.mergedIds.includes(findingId));
  }, [findings.data, findingId]);
}

/**
 * Apply a finding's proposed fix to the file it points at.
 *
 * The server does the splicing, and the arithmetic is why: the span is 1-based
 * and inclusive, and an off-by-one here corrupts somebody's source rather than
 * failing. It refuses when the file has changed since the run.
 *
 * The finding cannot survive its own fix -- its id is derived from the anchor
 * text -- which is the honest signal that it worked: re-run, and it moves to
 * 해결됨 under 비교.
 */
export function useApplyFix(runId: string | null) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (findingId: string) => applyFix(runId!, findingId),
    onSuccess: (result) => {
      toast.success("고침을 적용했습니다", {
        description: `${result.path} ${result.lines[0]}번 줄. 다시 검사하면 해결됐는지 확인할 수 있습니다.`,
      });
      // The file and the index both moved under us.
      void client.invalidateQueries({ queryKey: keys.run(result.run_id) });
    },
    onError: (error) => toast.error("고침을 적용할 수 없습니다", { description: describeError(error) }),
  });
}

/**
 * Ask the model for code to fix a finding that arrived without any.
 *
 * The counterpart to `useApplyFix` and never folded into it. A finding that came
 * with a patch is one click; a finding that came with only advice is now two --
 * make it, then approve it -- rather than the nothing it used to be. The middle
 * step is the diff, and it is not ceremony: this ends in a write to somebody's
 * source file.
 */
export function useProposeFix(runId: string | null) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (findingId: string) => proposeFix(runId!, findingId),
    onSuccess: (result) => {
      toast.success("고칠 코드를 만들었습니다", { description: "바뀔 내용을 확인하고 적용하세요." });
      // The report holds it now, so the finding list has to re-read it.
      void client.invalidateQueries({ queryKey: keys.run(result.run_id) });
    },
    onError: (error) => toast.error("고칠 코드를 만들 수 없습니다", { description: describeError(error) }),
  });
}

/** Every run on this server, newest first: what a comparison can be made against. */
export function useRuns() {
  return useQuery({
    queryKey: keys.runs(),
    queryFn: ({ signal }) => listRuns({ signal }).then((r) => r.runs),
    staleTime: 30_000,
  });
}

/**
 * This run's findings against another's.
 *
 * A read, so a query rather than a mutation, even though the endpoint takes a
 * POST -- the pair of run ids is the whole of the input, and asking twice for
 * the same pair should not go to the server twice.
 *
 * The point of content-derived finding ids: fix something, run again, and the
 * ones that closed are nameable rather than merely absent.
 */
export function useDiff(runId: string | null, against: string | null) {
  return useQuery({
    queryKey: keys.diff(runId ?? "", against ?? ""),
    queryFn: () => diffRuns(runId!, against!),
    enabled: enabled(runId) && Boolean(against) && runId !== against,
    retry: false,
  });
}

/** Both file mutations return the tree; write it straight in. */
function applyTree(client: QueryClient, runId: string, result: FileWriteResult) {
  client.setQueryData(keys.files(runId), result.files);
  client.setQueryData(keys.summary(runId), (previous: unknown) =>
    previous ? { ...previous, index: result.index, file_count: result.files.length } : previous,
  );
}

/**
 * Delete a run: its sources, its index, its trace and its report.
 *
 * `deleteRun` has had a client and no caller since it was written, so 70 runs
 * accumulated in `artifacts/agent-runs` with nothing on the page able to remove
 * one. The server refuses with a 409 while a run is in flight rather than
 * deleting the tree out from under its own worker, and that is worth reporting
 * as itself rather than as "삭제 실패".
 */
export function useDeleteRun() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: deleteRun,
    onSuccess: () => {
      // Only the list. Removing the run's own queries would make the components
      // still mounted against it re-fetch immediately -- from a server that has
      // just deleted it -- and the 404 would arrive before the caller had
      // finished clearing the id. They are disabled the moment it does, and
      // garbage collected after.
      void client.invalidateQueries({ queryKey: keys.runs() });
    },
    onError: (error) =>
      toast.error("실행을 지울 수 없습니다", {
        description: describeError(error),
      }),
  });
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
    mutationFn: (files: (File | { file: File; path: string })[]) => uploadSource(files),
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
    onSuccess: (result, options) => {
      // Declined, and nothing has changed: say so rather than let a button
      // that did nothing look like a button that is broken. The only way to
      // make it do work is to ask for the work, so offer that.
      if (result.nothing_to_do) {
        toast.info("다시 검사할 것이 없습니다", {
          description: "코드가 지난 검사 이후 그대로입니다. 결과와 호출 기록은 그대로 두었습니다.",
          duration: 8000,
          action: {
            label: "전체 다시 검사",
            onClick: () => {
              void ensureAttached().then(() => startRun(runId!, { ...options, force: true }));
              client.setQueryData(keys.summary(runId!), (previous: unknown) =>
                previous ? { ...previous, status: "inspecting", error: undefined } : previous,
              );
            },
          },
        });
        return;
      }
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
