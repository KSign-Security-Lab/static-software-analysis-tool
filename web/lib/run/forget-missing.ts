"use client";

import { useEffect } from "react";
import { toast } from "sonner";

import { ApiError } from "@/lib/api/client";
import { useRun } from "@/lib/run/queries";
import { useRunId } from "@/lib/run/use-run-id";

export function useForgetMissingRun(): void {
  const [runId, setRunId] = useRunId();
  const { error } = useRun(runId);
  const missing = error instanceof ApiError && error.status === 404;

  useEffect(() => {
    if (!runId || !missing) return;
    toast.info("그 검사는 더 이상 없습니다", {
      description: `${runId} 은(는) 지워졌거나 다른 서버의 실행입니다. 새로 시작할 수 있습니다.`,
    });
    setRunId(null);
  }, [runId, missing, setRunId]);
}
