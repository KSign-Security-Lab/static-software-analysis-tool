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
import type { CloneRequest, RunSummary, UploadResult } from "@/lib/api/types";
import { fromAgent, type UiFinding } from "@/lib/model/finding";
import { keys } from "@/lib/query/keys";
import { useSelectedFinding } from "@/lib/run/selection";

const enabled = (runId: string | null): runId is string => Boolean(runId);

export function useAgentHealth() {
  return useQuery({
    queryKey: keys.health(true),
    queryFn: ({ signal }) => health(true, { signal }),
    staleTime: 60_000,
    retry: false,
  });
}

export function useRun(
  runId: string | null,
  pollMs?: number | ((row: RunSummary | undefined) => number | false),
) {
  return useQuery({
    queryKey: keys.summary(runId ?? ""),
    queryFn: ({ signal }) => fetchRun(runId!, { signal }),
    enabled: enabled(runId),
    refetchInterval:
      typeof pollMs === "function" ? (query) => pollMs(query.state.data) : (pollMs ?? false),
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

export function useOpenFinding(runId: string | null): UiFinding | undefined {
  const [findingId] = useSelectedFinding();
  const findings = useFindings(runId);
  return useMemo(() => {
    if (!findingId) return undefined;
    const all = fromAgent(findings.data?.findings);
    return all.find((each) => each.id === findingId) ?? all.find((each) => each.mergedIds.includes(findingId));
  }, [findings.data, findingId]);
}

export function useProposeFix(runId: string | null) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (findingId: string) => proposeFix(runId!, findingId),
    onSuccess: (result) => {
      toast.success("고칠 코드를 만들었습니다", { description: "바뀔 내용을 확인하고 적용하세요." });
      void client.invalidateQueries({ queryKey: keys.run(result.run_id) });
    },
    onError: (error) => toast.error("고칠 코드를 만들 수 없습니다", { description: describeError(error) }),
  });
}

export function useRuns() {
  return useQuery({
    queryKey: keys.runs(),
    queryFn: ({ signal }) => listRuns({ signal }).then((r) => r.runs),
    staleTime: 30_000,
  });
}

export function useDeleteRun() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: deleteRun,
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: keys.runs() });
    },
    onError: (error) =>
      toast.error("실행을 지울 수 없습니다", {
        description: describeError(error),
      }),
  });
}

function seedRun(client: QueryClient, result: UploadResult) {
  client.setQueryData(keys.files(result.run_id), result.files);
  void client.invalidateQueries({ queryKey: keys.runs() });
}

export function useUpload() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (files: (File | { file: File; path: string })[]) => uploadSource(files),
    onSuccess: (result) => seedRun(client, result),
    onError: (error) => toast.error("업로드 실패", { description: describeError(error) }),
  });
}

export function useUploadArchive() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (file: File) => uploadArchive(file),
    onSuccess: (result) => seedRun(client, result),
    onError: (error) => toast.error("압축 파일을 읽을 수 없습니다", { description: describeError(error) }),
  });
}

export function useCloneRepo() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (request: CloneRequest) => cloneRepo(request),
    onSuccess: (result) => seedRun(client, result),
    onError: (error) => toast.error("저장소를 가져올 수 없습니다", { description: describeError(error) }),
  });
}

export function useStartRun(runId: string | null, ensureAttached: () => Promise<void>) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (options: StartOptions) => {
      await ensureAttached();
      return startRun(runId!, options);
    },
    onSuccess: (result, options) => {
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
      if (result.already_running) {
        toast.info("이미 검사가 진행 중입니다", { description: "진행 상황을 다시 불러옵니다." });
        void client.invalidateQueries({ queryKey: keys.summary(runId!) });
        return;
      }
      client.setQueryData(keys.summary(runId!), (previous: unknown) =>
        previous ? { ...previous, status: "inspecting", error: undefined } : previous,
      );
    },
    onError: (error) => toast.error("검사를 시작할 수 없습니다", { description: describeError(error) }),
  });
}
