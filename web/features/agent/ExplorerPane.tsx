"use client";

import { useEffect, useMemo } from "react";
import { FilePlus } from "lucide-react";

import { useCommands } from "@/lib/commands/provider";
import { fromAgent } from "@/lib/model/finding";
import { useCreateRun, useDeleteFile, useFiles, useFindings, useUpload, useWriteFile } from "@/lib/run/queries";
import { useRunId } from "@/lib/run/use-run-id";
import FileExplorer from "./FileExplorer";
import { useOpenFile } from "./state";

const STARTER = `#include <stdlib.h>
#include <stdio.h>

void handle(const char *url) {
    char cmd[128];
    sprintf(cmd, "wget %s", url);
    system(cmd);
}
`;

/**
 * The explorer, and the run it belongs to.
 *
 * Creating a run is lazy: pasting one snippet should not require uploading
 * something first, so the first write makes the run if there is not one yet.
 */
export default function ExplorerPane() {
  const [runId, setRunId] = useRunId();
  const [path, setPath] = useOpenFile();

  const files = useFiles(runId);
  const findings = useFindings(runId);
  const create = useCreateRun();
  const upload = useUpload();
  const write = useWriteFile(runId);
  const remove = useDeleteFile(runId);

  const list = useMemo(() => files.data ?? [], [files.data]);
  const ui = useMemo(() => fromAgent(findings.data?.findings ?? []), [findings.data]);

  // Open something rather than nothing: an explorer with files and an empty
  // editor beside it looks broken.
  useEffect(() => {
    if (path || list.length === 0) return;
    const first = list.find((each) => /\.(c|h|cpp|cc|hpp|java|py|ts|go|rs)$/i.test(each)) ?? list[0];
    void setPath(first);
  }, [path, list, setPath]);

  const withRun = async (): Promise<string | null> => {
    if (runId) return runId;
    const run = await create.mutateAsync();
    setRunId(run.run_id);
    return run.run_id;
  };

  const onCreate = async (name: string, content = "") => {
    const id = await withRun();
    if (!id) return;
    // `id`, not the hook's runId: on a cold start the run was created a moment
    // ago and this render still closes over `null`.
    try {
      await write.mutateAsync({ path: name, content, runId: id });
    } catch {
      // Reported by the mutation's own onError. Swallowed here only so an
      // opened-but-empty editor is not the next thing that happens.
      return;
    }
    void setPath(name);
  };

  useCommands(
    () => [
      {
        id: "file.new",
        title: "새 파일",
        group: "파일",
        keybinding: "mod+n",
        icon: FilePlus,
        run: () => void onCreate("new.c"),
      },
      {
        id: "file.starter",
        title: "예제로 시작",
        group: "파일",
        when: () => list.length === 0,
        run: () => void onCreate("main.c", STARTER),
      },
    ],
    [runId, list.length],
  );

  return (
    <FileExplorer
      files={list}
      active={path}
      findings={ui}
      busy={create.isPending || upload.isPending}
      onOpen={(next) => void setPath(next)}
      onCreate={(name) => void onCreate(name)}
      onDelete={(target) => {
        remove.mutate(target, {
          onSuccess: (result) => {
            if (path === target) void setPath(result.files[0] ?? null);
          },
        });
      }}
      onUpload={(picked) =>
        upload.mutate(picked, {
          onSuccess: (result) => {
            setRunId(result.run_id);
            void setPath(null);
          },
        })
      }
    />
  );
}
