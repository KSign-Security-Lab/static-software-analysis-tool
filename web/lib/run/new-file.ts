"use client";

import { useCreateRun, useWriteFile } from "@/lib/run/queries";
import { useOpenFile } from "@/lib/run/selection";
import { useRunId } from "@/lib/run/use-run-id";

/** The example the empty editor offers, so a first look costs one click. */
export const STARTER = `#include <stdlib.h>
#include <stdio.h>

void handle(const char *url) {
    char cmd[128];
    sprintf(cmd, "wget %s", url);
    system(cmd);
}
`;

/**
 * Put a file into the run, making the run if there is not one yet.
 *
 * Shared because two places offer it -- the file list, and the empty editor -- and
 * they used to reach each other through a command registry: one registered
 * `file.new`, the other called `registry.run("file.new")`. That registry existed to
 * feed a command palette, and with the palette gone it was an indirection between
 * two components that simply want the same three lines.
 *
 * Creating the run is lazy: pasting one snippet should not require uploading
 * something first.
 */
export function useCreateFile() {
  const [runId, setRunId] = useRunId();
  const [, setPath] = useOpenFile();
  const create = useCreateRun();
  const write = useWriteFile(runId);

  return {
    busy: create.isPending || write.isPending,
    create: async (name: string, content = "") => {
      let id = runId;
      if (!id) {
        const made = await create.mutateAsync();
        id = made.run_id;
        setRunId(id);
      }
      try {
        // `id`, not the hook's runId: on a cold start the run was made a moment
        // ago and this render still closes over `null`.
        await write.mutateAsync({ path: name, content, runId: id });
      } catch {
        // Reported by the mutation's own onError; swallowed only so an
        // opened-but-empty editor is not the next thing that happens.
        return;
      }
      void setPath(name);
    },
  };
}
