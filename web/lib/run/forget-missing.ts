"use client";

import { useEffect } from "react";
import { toast } from "sonner";

import { ApiError } from "@/lib/api/client";
import { useRun } from "@/lib/run/queries";
import { useRunId } from "@/lib/run/use-run-id";

/**
 * Let go of a run the server does not have.
 *
 * A run id outlives the run it names. It sits in a link somebody sent, in the
 * address bar of a tab left open, and in that tab's own memory -- and nothing
 * ever checked that it still resolved. So a deleted run left the page looking
 * perfectly usable: an empty explorer, no findings, no complaint. Then every
 * action against it failed with `찾을 수 없습니다. unknown run: …` and no
 * indication of why, because the id was the problem and the id was invisible.
 *
 * Worse, it spread. `useRunId` remembers whatever run is in the URL so a bare
 * `/agent` reopens it, and it remembered dead ones too -- so the id outlived
 * being cleared from the address bar as well.
 *
 * The summary query decides. A 4xx is never retried (see lib/query/client.ts),
 * so its 404 arrives once, immediately, and means the run is gone rather than
 * the network being slow.
 */
export function useForgetMissingRun(): void {
  const [runId, setRunId] = useRunId();
  const { error } = useRun(runId);
  const missing = error instanceof ApiError && error.status === 404;

  useEffect(() => {
    if (!runId || !missing) return;
    // Said, not done quietly. A URL that empties itself with no explanation is
    // the same surprise in the other direction, and this is the one moment when
    // naming the run is useful rather than noise.
    toast.info("그 검사는 더 이상 없습니다", {
      description: `${runId} 은(는) 지워졌거나 다른 서버의 실행입니다. 새로 시작할 수 있습니다.`,
    });
    // Clears the tab's memory of it too -- see useRunId, which forgets on null.
    setRunId(null);
  }, [runId, missing, setRunId]);
}
