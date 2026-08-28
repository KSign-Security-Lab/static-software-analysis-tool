"use client";

import { useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";
import { useMemo } from "react";
import { toast } from "sonner";

import { describeError } from "@/lib/api/client";
import { startRun, type StartOptions } from "@/lib/api/control";
import {
  cloneRepo,
  deleteRun,
  fetchFile,
  fetchFiles,
  fetchFindings,
  fetchRun,
  health,
  listRuns,
  proposeFix,
  uploadArchive,
  uploadSource,
} from "@/lib/api/runs";
import type { CloneRequest, UploadResult } from "@/lib/api/types";
import { fromAgent, type UiFinding } from "@/lib/model/finding";
import { keys } from "@/lib/query/keys";
import { useSelectedFinding } from "@/lib/run/selection";

/**
 * The queries and mutations 검사 runs on.
 *
 * Nothing here writes to a run's tree. Intake creates a run and fills it once;
 * after that the tree is what the report was made from, and a fix leaves as a
 * patch rather than as an edit -- so the cache-coherence problem that used to
 * live in this file (three mutations, one file list, one index) is gone with the
 * editor that caused it.
 */

const enabled = (runId: string | null): runId is string => Boolean(runId);

/**
 * Whether the agent can run at all, and what the endpoint serves.
 *
 * Probed, which costs a request to the model endpoint, and it is worth it: that
 * request is the only way to answer "then what *should* `AGENT_MODEL` be", and
 * knowing an id is unset without knowing the alternatives is a dead end.
 *
 * There is deliberately no default model -- a wrong one silently produces
 * plausible nonsense -- so an unconfigured deployment is a normal state that the
 * intake screen has to be able to describe.
 */
export function useAgentHealth() {
  return useQuery({
    queryKey: keys.health(true),
    queryFn: ({ signal }) => health(true, { signal }),
    staleTime: 60_000,
    retry: false,
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
 * Ask the model for code to fix a finding that arrived without any.
 *
 * What makes an advice-only finding patchable at all. The specialist proposes a
 * fix only when it happens to fit the lines the anchor resolved to, and often it
 * does not -- so without this, ticking such a finding produces a `no_replacement`
 * skip and nothing a reader can do about it.
 *
 * Writes the proposal into the report and stops. Nothing is applied anywhere:
 * the patch is still built from the report when the bucket is exported.
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

/** Every run this owner has, newest first: the 지난 검사 list. */
export function useRuns() {
  return useQuery({
    queryKey: keys.runs(),
    queryFn: ({ signal }) => listRuns({ signal }).then((r) => r.runs),
    staleTime: 30_000,
  });
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

/**
 * What every intake path does once the run exists.
 *
 * The file list comes back with the response, so it is written straight into the
 * cache -- the screen that follows needs it immediately and asking again would
 * be a round trip to be told what we were just told.
 */
function seedRun(client: QueryClient, result: UploadResult) {
  client.setQueryData(keys.files(result.run_id), result.files);
  void client.invalidateQueries({ queryKey: keys.runs() });
}

/** A folder, or a set of loose files, with the path each had. */
export function useUpload() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (files: (File | { file: File; path: string })[]) => uploadSource(files),
    onSuccess: (result) => seedRun(client, result),
    onError: (error) => toast.error("업로드 실패", { description: describeError(error) }),
  });
}

/** A zip. The server has always taken one; nothing used to say so. */
export function useUploadArchive() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (file: File) => uploadArchive(file),
    onSuccess: (result) => seedRun(client, result),
    onError: (error) => toast.error("압축 파일을 읽을 수 없습니다", { description: describeError(error) }),
  });
}

/**
 * A git remote.
 *
 * Slower than the other two, because the server is fetching somebody else's
 * repository. Both failure modes are worth distinguishing and the API already
 * does: a URL it may not fetch is a 400 with the reason, an unreachable remote
 * is a 502.
 */
export function useCloneRepo() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (request: CloneRequest) => cloneRepo(request),
    onSuccess: (result) => seedRun(client, result),
    onError: (error) => toast.error("저장소를 가져올 수 없습니다", { description: describeError(error) }),
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
